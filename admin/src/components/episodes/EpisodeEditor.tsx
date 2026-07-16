import { useEffect, useMemo, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import type { JSONContent } from '@tiptap/core';
import { useNavigate } from '@tanstack/react-router';
import { describeAuthError } from '../../lib/api';
import type { ContentDoc, Episode, EpisodeUpdate } from '../../types';
import {
  useCreateEpisode,
  useEpisodeImageUrls,
  useUpdateEpisode,
  useUploadEpisodeImage,
} from '../../hooks/useEpisodes';
import { useWorks } from '../../hooks/useWorks';
import { buildEditorExtensions } from './extensions';
import { createImageUrlStore } from './imageUrlStore';
import { summarizeContent } from './contentSummary';
import { MAX_IMAGES_PER_EPISODE, validateImageFile } from './imageUpload';
import { EditorToolbar } from './EditorToolbar';
import { PublishModal } from './PublishModal';

interface EpisodeEditorProps {
  /** 진입 시 확정된 작품. 작품 경로 진입이면 값이 있고, 글로벌 진입이면 없다(모달 전 선택). */
  initialWorkId?: string;
  /** 있으면 편집(재진입) 모드, 없으면 신규(캔버스 먼저) 모드. */
  episode?: Episode;
}

const TITLE_FALLBACK = '무제';
const EMPTY_DOC: ContentDoc = { type: 'doc', content: [] };

/** 로드된 본문에 유료 경계가 없으면 맨 끝에 넣는다(= 기본 전체 무료). 경계는 항상 1개 존재하고,
 * 편집 중 삭제돼도 paywall 확장의 플러그인이 되살린다. */
function ensurePaywall(doc: JSONContent | undefined): JSONContent {
  const base: JSONContent = doc && doc.type === 'doc' ? doc : { type: 'doc', content: [] };
  const content = base.content ?? [];
  if (content.some((node) => node.type === 'paywall')) return base;
  return { ...base, content: [...content, { type: 'paywall' }] };
}

export function EpisodeEditor({ initialWorkId, episode }: EpisodeEditorProps) {
  const navigate = useNavigate();
  const works = useWorks();

  // 작품(시리즈)은 draft 생성 전까지 바꿀 수 있고, 생성 후엔 고정된다(다른 작품으로 이동 =
  // 별도 BE 작업). 편집 모드는 episode.work_id로 고정.
  const [workId, setWorkId] = useState<string | null>(episode?.work_id ?? initialWorkId ?? null);
  const [episodeId, setEpisodeId] = useState<string | null>(episode?.id ?? null);
  const [title, setTitle] = useState(
    episode && episode.title !== TITLE_FALLBACK ? episode.title : '',
  );
  const [subtitle, setSubtitle] = useState(episode?.subtitle ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);

  const createEpisode = useCreateEpisode(workId ?? '');
  const uploadImage = useUploadEpisodeImage(workId ?? '');
  const updateEpisode = useUpdateEpisode(workId ?? '');

  const imageStore = useMemo(() => createImageUrlStore(), []);
  const blobUrlsRef = useRef<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const editor = useEditor({
    extensions: buildEditorExtensions(imageStore),
    content: ensurePaywall(episode?.content as JSONContent | undefined),
    immediatelyRender: false,
    editorProps: {
      attributes: { class: 'min-h-[300px] py-3 focus:outline-none' },
    },
  });

  // presigned URL 로드 → store 반영(업로드 직후 optimistic blob을 실 URL로 덮어씀).
  const imageUrls = useEpisodeImageUrls(workId ?? '', episodeId);
  useEffect(() => {
    if (imageUrls.data) imageStore.set(imageUrls.data.map((pair) => [pair.key, pair.url] as const));
  }, [imageUrls.data, imageStore]);

  // blob은 언마운트 시 일괄 revoke(실 URL로 교체된 뒤에도 남아있어 정리).
  useEffect(
    () => () => {
      for (const url of blobUrlsRef.current) URL.revokeObjectURL(url);
    },
    [],
  );

  // 작품 경로로 진입했거나(initialWorkId) 편집 모드거나 draft가 생기면 작품은 고정 표시.
  // 드롭다운 선택은 글로벌 진입(작품 미지정)일 때만 노출한다.
  const workLocked = episode !== undefined || episodeId !== null || initialWorkId !== undefined;
  const workName = works.data?.find((work) => work.id === workId)?.title ?? '';
  const canPersist = !!workId && !!editor;

  const summary = editor
    ? summarizeContent(editor.state.doc)
    : { free: { chars: 0, images: 0 }, paid: { chars: 0, images: 0 } };
  const hasPaidContent = summary.paid.chars > 0 || summary.paid.images > 0;
  const hasAnyContent =
    hasPaidContent || summary.free.chars > 0 || summary.free.images > 0;

  const countImages = (): number => {
    let count = 0;
    editor?.state.doc.forEach((child) => {
      if (child.type.name === 'image') count += 1;
      else child.descendants((node) => void (node.type.name === 'image' && (count += 1)));
    });
    return count;
  };

  const ensureDraft = async (): Promise<string> => {
    if (episodeId) return episodeId;
    const created = await createEpisode.mutateAsync({
      title: title.trim() || TITLE_FALLBACK,
      subtitle: subtitle.trim() || null,
    });
    setEpisodeId(created.id);
    return created.id;
  };

  const save = async (extra: Partial<EpisodeUpdate>): Promise<Episode> => {
    const id = await ensureDraft();
    const content = (editor?.getJSON() as ContentDoc | undefined) ?? EMPTY_DOC;
    const body: EpisodeUpdate = {
      title: title.trim() || TITLE_FALLBACK,
      subtitle: subtitle.trim() || null,
      content,
      ...extra,
    };
    return updateEpisode.mutateAsync({ episodeId: id, body });
  };

  const onSaveDraft = async () => {
    if (!canPersist) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await save({});
      // 신규(작품 경로/글로벌)에서 저장했으면 URL이 draft를 가리키게 편집 라우트로 이동.
      if (!episode) {
        navigate({
          to: '/works/$workId/episodes/$episodeId',
          params: { workId: saved.work_id, episodeId: saved.id },
        });
      }
    } catch (err) {
      setError(describeAuthError(err));
    } finally {
      setSaving(false);
    }
  };

  const onPublish = async (values: { thumbnail: string | null; price: number | null }) => {
    setSaving(true);
    setError(null);
    try {
      const saved = await save({
        is_published: true,
        thumbnail: values.thumbnail,
        price: values.price,
      });
      setPublishOpen(false);
      navigate({ to: '/works/$workId/episodes', params: { workId: saved.work_id } });
    } catch (err) {
      setError(describeAuthError(err));
    } finally {
      setSaving(false);
    }
  };

  const onInsertImage = () => {
    if (!workId) {
      setFileError('이미지를 넣으려면 먼저 시리즈(작품)를 선택하세요.');
      return;
    }
    fileInputRef.current?.click();
  };

  const onFilesSelected = async (files: File[]) => {
    setFileError(null);
    if (files.length === 0 || !editor || !workId) return;
    const room = MAX_IMAGES_PER_EPISODE - countImages();
    const problems: string[] = [];
    const accepted: File[] = [];
    for (const file of files) {
      const problem = validateImageFile(file);
      if (problem) {
        problems.push(problem);
        continue;
      }
      if (accepted.length >= room) {
        problems.push(`회차당 최대 ${MAX_IMAGES_PER_EPISODE}장까지 등록할 수 있습니다.`);
        break;
      }
      accepted.push(file);
    }
    if (problems.length > 0) setFileError(problems.join(' '));
    if (accepted.length === 0) return;

    setSaving(true);
    try {
      const id = await ensureDraft();
      setProgress({ done: 0, total: accepted.length });
      for (const [index, file] of accepted.entries()) {
        const blobUrl = URL.createObjectURL(file);
        try {
          const updated = await uploadImage.mutateAsync({ episodeId: id, file });
          const newKey = updated.image_keys[updated.image_keys.length - 1];
          blobUrlsRef.current.push(blobUrl);
          imageStore.set([[newKey, blobUrl]]); // optimistic: 응답엔 presigned URL이 없어 즉시 표시용 blob
          editor.chain().focus().insertContent({ type: 'image', attrs: { key: newKey } }).run();
        } catch (err) {
          URL.revokeObjectURL(blobUrl);
          setFileError(describeAuthError(err));
          break;
        }
        setProgress({ done: index + 1, total: accepted.length });
      }
      void imageUrls.refetch(); // optimistic blob → 실 presigned URL로 교체
    } finally {
      setSaving(false);
      setProgress(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* 시리즈(작품): draft 생성 전엔 선택 가능, 이후 고정. 이미지 업로드가 작품을 필요로 해 상단에 둔다. */}
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-500">시리즈</span>
        {workLocked ? (
          <span className="font-medium text-gray-700">{workName || '...'}</span>
        ) : (
          <select
            value={workId ?? ''}
            onChange={(event) => setWorkId(event.target.value || null)}
            className="rounded border border-gray-300 px-2 py-1"
          >
            <option value="">작품 선택...</option>
            {works.data?.map((work) => (
              <option key={work.id} value={work.id}>
                {work.title}
              </option>
            ))}
          </select>
        )}
      </div>

      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        maxLength={200}
        placeholder="제목 (비우면 무제)"
        className="border-b border-gray-200 pb-1 text-2xl font-bold focus:border-gray-400 focus:outline-none"
      />
      <input
        value={subtitle}
        onChange={(event) => setSubtitle(event.target.value)}
        maxLength={200}
        placeholder="부제 (선택)"
        className="border-b border-gray-100 pb-1 text-lg text-gray-600 focus:border-gray-300 focus:outline-none"
      />

      <div className="rounded border border-gray-300 px-4 py-2">
        {editor && <EditorToolbar editor={editor} onInsertImage={onInsertImage} disabled={saving} />}
        <EditorContent editor={editor} />
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        className="hidden"
        data-testid="image-input"
        onChange={(event) => {
          void onFilesSelected(Array.from(event.target.files ?? []));
          event.target.value = '';
        }}
      />

      {progress && (
        <div className="flex flex-col gap-1" role="status">
          <div className="h-2 overflow-hidden rounded bg-gray-200">
            <div
              className="h-2 rounded bg-gray-900 transition-all"
              style={{
                width: `${progress.total === 0 ? 0 : (progress.done / progress.total) * 100}%`,
              }}
            />
          </div>
          <span className="text-sm text-gray-600">
            {progress.done}/{progress.total}장 업로드 (서버에서 800px WebP로 변환됩니다)
          </span>
        </div>
      )}

      {fileError && <p className="text-sm text-red-600">{fileError}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex items-center justify-between border-t border-gray-200 pt-4">
        <button
          type="button"
          onClick={onSaveDraft}
          disabled={saving || !canPersist}
          className="rounded bg-gray-100 px-4 py-2 text-sm hover:bg-gray-200 disabled:opacity-50"
        >
          {saving ? '저장 중...' : '임시저장'}
        </button>
        <button
          type="button"
          onClick={() => setPublishOpen(true)}
          disabled={saving || !canPersist}
          className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          발행하기
        </button>
      </div>
      {!workId && (
        <p className="text-xs text-amber-600">저장·발행하려면 먼저 시리즈(작품)를 선택하세요.</p>
      )}
      <p className="text-xs text-gray-500">
        임시저장은 비공개로 남고, 발행하기는 즉시 공개됩니다. 예약 공개는 다음 단계에서 추가됩니다.
      </p>

      {publishOpen && (
        <PublishModal
          workName={workName}
          images={imageUrls.data ?? []}
          defaultThumbnail={episode?.thumbnail ?? null}
          defaultPrice={episode?.price ?? null}
          hasPaidContent={hasPaidContent}
          canPublish={hasAnyContent}
          saving={saving}
          error={error}
          onCancel={() => setPublishOpen(false)}
          onPublish={onPublish}
        />
      )}
    </div>
  );
}
