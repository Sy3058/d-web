import { useEffect, useMemo, useRef, useState } from 'react';
import { generateHTML, type Extensions } from '@tiptap/core';
import { buildViewerExtensions } from './extensions';
import {
  clampBlockIndex,
  getEpisodeContent,
  getProgress,
  imageFetchPriority,
  isLoggedIn,
  putProgress,
  type ContentDocNode,
  type EpisodeContentResponse,
} from '../../lib/viewer';

interface Props {
  episodeId: string;
}

interface Block {
  node: ContentDocNode;
  // 이 블록이 image면 전체 이미지 순번(fetchPriority 배정용), 아니면 null.
  imageOrdinal: number | null;
}

// 진행도 저장 debounce. 스크롤할 때마다 쏘지 않고 멈춘 뒤에만 저장(C1은 저장 실패를
// 조용히 무시하는 부가 기능이라 과도한 요청을 낼 이유가 없다).
const PROGRESS_SAVE_DEBOUNCE_MS = 800;

function buildBlocks(nodes: ContentDocNode[]): Block[] {
  let imageOrdinal = 0;
  return nodes.map((node) => {
    if (node.type === 'image') {
      const ordinal = imageOrdinal;
      imageOrdinal += 1;
      return { node, imageOrdinal: ordinal };
    }
    return { node, imageOrdinal: null };
  });
}

function renderNodeHtml(node: ContentDocNode, extensions: Extensions): string {
  try {
    return generateHTML({ type: 'doc', content: [node] }, extensions);
  } catch (e) {
    // 서버 lib/content_doc._validate_node는 최상위 노드 타입을 블록으로 제한하지 않아
    // (예: 최상위 text도 통과) TipTap 스키마가 거부하는 문서가 이론상 가능하다 - 조각
    // 하나의 렌더 실패로 뷰어 전체가 죽지 않게 그 블록만 비워서 넘긴다(B2의 "노드 폐기+
    // 로그"와 같은 원칙 - 공개 읽기 경로가 데이터 상태로 죽지 않게).
    console.warn('뷰어 블록 렌더 실패', e);
    return '';
  }
}

export default function Viewer({ episodeId }: Props) {
  const extensions = useMemo(() => buildViewerExtensions(), []);
  // undefined=로딩 중, null=404(회차 없음), 그 외=정상 응답.
  const [content, setContent] = useState<EpisodeContentResponse | null | undefined>(undefined);
  const [restoredIndex, setRestoredIndex] = useState<number | null>(null);
  const retriedRef = useRef(false);
  const blockRefs = useRef(new Map<number, HTMLDivElement>());
  const topVisibleRef = useRef(0);
  const hasObservedRef = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEpisodeContent(episodeId).then((res) => {
      if (!cancelled) setContent(res);
    });
    return () => {
      cancelled = true;
    };
  }, [episodeId]);

  const blocks = useMemo(() => (content ? buildBlocks(content.content.content) : []), [content]);

  // 진행도 복원 - 로그인 상태에서만 GET을 쏜다(비로그인 401 자체를 만들지 않는다).
  useEffect(() => {
    if (blocks.length === 0 || !isLoggedIn(document.cookie)) return;
    let cancelled = false;
    getProgress(episodeId).then((progress) => {
      if (cancelled || !progress) return;
      setRestoredIndex(clampBlockIndex(progress.page_no, blocks.length));
    });
    return () => {
      cancelled = true;
    };
  }, [episodeId, blocks.length]);

  useEffect(() => {
    if (restoredIndex === null) return;
    // 알려진 한계: 이미지 로딩으로 레이아웃이 이 시점 이후에도 자라 정확한 위치가 아닐 수
    // 있다(이미지 전량 즉시 요청이라 대부분 빠르게 안정되지만 완벽한 보장은 아님).
    blockRefs.current.get(restoredIndex)?.scrollIntoView({ block: 'start' });
  }, [restoredIndex]);

  // 뷰포트에 여러 블록이 걸쳐 있으면 "보이는 인덱스 중 최솟값"을 진행 위치로 삼는다 - 최댓값이나
  // 최다-노출 블록을 쓰면 아직 안 읽은 블록이 뷰포트에 살짝 걸치자마자 진행도가 그리로 넘어가,
  // 다음 방문 때 안 읽은 내용을 건너뛰게 된다. debounce로 저장한다.
  useEffect(() => {
    if (blocks.length === 0 || !isLoggedIn(document.cookie)) return;

    const visible = new Set<number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const index = Number((entry.target as HTMLElement).dataset.blockIndex);
          if (entry.isIntersecting) visible.add(index);
          else visible.delete(index);
        }
        if (visible.size === 0) return;
        hasObservedRef.current = true;
        topVisibleRef.current = Math.min(...visible);
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(() => {
          void putProgress(episodeId, topVisibleRef.current);
        }, PROGRESS_SAVE_DEBOUNCE_MS);
      },
      { threshold: 0 },
    );
    for (const el of blockRefs.current.values()) observer.observe(el);

    // 페이지 이탈 직전(탭 전환·닫기) 대기 중인 저장을 즉시 시도한다. keepalive는 보장되지
    // 않아 유실 가능 - C1 결정(저장 실패는 조용히 무시)상 허용 범위, 최선 노력일 뿐이다.
    function flushOnHide() {
      // 관측이 한 번도 없었으면(예: 진입 직후 바로 이탈) 저장할 위치가 없다 - page_no=0을
      // 실제 위치로 오인해 쏘지 않는다.
      if (document.visibilityState !== 'hidden' || !hasObservedRef.current) return;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      void putProgress(episodeId, topVisibleRef.current);
    }
    document.addEventListener('visibilitychange', flushOnHide);

    return () => {
      observer.disconnect();
      document.removeEventListener('visibilitychange', flushOnHide);
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [blocks.length, episodeId]);

  function handleImageError() {
    // presigned 만료 등 예외적 실패의 폴백(정상 경로 - 결정 6 즉시 전량 요청 - 에선 타지
    // 않아야 정상). 1회만 재요청해 새로 발급된 presigned 세트로 교체한다.
    if (retriedRef.current) return;
    retriedRef.current = true;
    getEpisodeContent(episodeId).then(setContent);
  }

  if (content === undefined) {
    return <p className="text-sm text-muted py-12 text-center">불러오는 중...</p>;
  }
  if (content === null) {
    return <p className="text-sm text-muted py-12 text-center">회차를 찾을 수 없어요.</p>;
  }

  return (
    <div
      className="select-none [-webkit-touch-callout:none]"
      onContextMenu={(e) => e.preventDefault()}
      // 컨테이너에도 드래그 차단을 둔다 - 최상위 image는 자체 onDragStart로 이미 막히지만,
      // paragraph 자식으로 내려온(비-최상위) image는 generateHTML 렌더 경로라 개별 핸들러를
      // 못 붙인다 - 두 경로의 보호 수준을 여기서 맞춘다.
      onDragStart={(e) => e.preventDefault()}
    >
      {blocks.map((block, i) => (
        <div
          key={i}
          data-block-index={i}
          ref={(el) => {
            if (el) blockRefs.current.set(i, el);
            else blockRefs.current.delete(i);
          }}
        >
          {block.node.type === 'image' ? (
            typeof block.node.attrs?.src !== 'string' ? null : (
              <img
                src={block.node.attrs.src}
                alt=""
                draggable={false}
                fetchPriority={imageFetchPriority(block.imageOrdinal ?? 0)}
                onDragStart={(e) => e.preventDefault()}
                onError={handleImageError}
                className="w-full h-auto"
              />
            )
          ) : (
            // 서버 lib/content_doc이 검증한 노드만 렌더 대상이라 XSS 면적이 없다(#76 -
            // 화이트리스트 밖 태그·속성은 애초에 저장될 수 없다).
            <div dangerouslySetInnerHTML={{ __html: renderNodeHtml(block.node, extensions) }} />
          )}
        </div>
      ))}

      {content.has_paid_part && (
        <div className="mt-8 py-12 text-center border-t border-line">
          <p className="text-sm text-muted">여기부터는 유료 구간이에요.</p>
        </div>
      )}
    </div>
  );
}
