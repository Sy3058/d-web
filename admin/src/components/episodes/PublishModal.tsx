import { useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { episodePublishSchema, type EpisodePublishInput } from '../../lib/validation';
import type { EpisodeImageUrl } from '../../types';

interface PublishModalProps {
  /** 발행 대상 작품(시리즈) 이름 - 선택은 에디터 상단에서 하고 여기선 확인만. */
  workName: string;
  /** 대표 이미지 후보(업로드된 본문 이미지). */
  images: EpisodeImageUrl[];
  defaultThumbnail: string | null;
  defaultPrice: number | null;
  /** 유료 경계 뒤에 내용이 있는가 - 있을 때만 판매가 입력을 노출한다. */
  hasPaidContent: boolean;
  /** 본문에 유의미 내용(글/이미지)이 있는가 - 없으면 발행 불가(서버도 거부). */
  canPublish: boolean;
  saving: boolean;
  error: string | null;
  onCancel: () => void;
  onPublish: (values: {
    thumbnail: string | null;
    price: number | null;
    /** null = 지금 공개(is_published), ISO+offset 문자열 = 예약 공개(published_at). */
    publishedAt: string | null;
  }) => void;
}

/** 현재 시각을 datetime-local 입력용 로컬 문자열(YYYY-MM-DDThh:mm)로 변환. min/기본값에 쓴다. */
function nowLocalInput(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 발행하기 모달: 대표 이미지(단일)·판매가(유료일 때만)·공개 시점(지금/예약) 확정 후 발행. */
export function PublishModal({
  workName,
  images,
  defaultThumbnail,
  defaultPrice,
  hasPaidContent,
  canPublish,
  saving,
  error,
  onCancel,
  onPublish,
}: PublishModalProps) {
  const [thumbnail, setThumbnail] = useState<string | null>(defaultThumbnail);
  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors },
  } = useForm<EpisodePublishInput>({
    resolver: zodResolver(episodePublishSchema),
    defaultValues: { mode: 'now', price: defaultPrice, publishedAt: null },
  });
  const mode = useWatch({ control, name: 'mode' });

  // 무료 회차면 가격은 항상 null(입력칸 자체를 안 띄운다).
  // 예약이면 로컬 datetime을 offset 포함 ISO로 변환해 published_at으로 넘긴다(지금이면 null).
  const submit = (values: EpisodePublishInput) => {
    const publishedAt =
      values.mode === 'schedule' && values.publishedAt
        ? new Date(values.publishedAt).toISOString()
        : null;
    onPublish({ thumbnail, price: hasPaidContent ? values.price : null, publishedAt });
  };

  const thumbButton = (selected: boolean) =>
    `h-16 w-16 shrink-0 overflow-hidden rounded border ${
      selected ? 'ring-2 ring-gray-900' : 'border-gray-200'
    }`;

  const segButton = (selected: boolean) =>
    `flex-1 rounded border px-3 py-2 text-sm ${
      selected ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-300 text-gray-700'
    }`;

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-white p-5 shadow-lg">
        <h2 className="mb-4 text-lg font-bold">발행하기</h2>
        <form onSubmit={handleSubmit(submit)} noValidate className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">시리즈</span>
            <p className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
              {workName}
            </p>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">대표 이미지</span>
            {images.length === 0 ? (
              <p className="text-sm text-gray-500">
                본문에 이미지를 넣으면 대표 이미지를 고를 수 있어요.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setThumbnail(null)}
                  className={`flex h-16 w-16 shrink-0 items-center justify-center rounded border text-xs text-gray-500 ${
                    thumbnail === null ? 'ring-2 ring-gray-900' : 'border-gray-200'
                  }`}
                >
                  없음
                </button>
                {images.map((image) => (
                  <button
                    key={image.key}
                    type="button"
                    onClick={() => setThumbnail(image.key)}
                    className={thumbButton(thumbnail === image.key)}
                  >
                    <img src={image.url} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>

          {hasPaidContent && (
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">판매가 (원)</span>
              <input
                type="number"
                min={0}
                step={10}
                placeholder="비우면 작품 기본가"
                {...register('price', {
                  setValueAs: (v) => (v === '' || v == null ? null : Number(v)),
                })}
                className="rounded border border-gray-300 px-3 py-2"
              />
              {errors.price && <span className="text-sm text-red-600">{errors.price.message}</span>}
            </label>
          )}

          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">공개 시점</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setValue('mode', 'now')}
                className={segButton(mode === 'now')}
              >
                지금 공개
              </button>
              <button
                type="button"
                onClick={() => setValue('mode', 'schedule')}
                className={segButton(mode === 'schedule')}
              >
                예약 공개
              </button>
            </div>
            {mode === 'schedule' && (
              <div className="mt-1 flex flex-col gap-1">
                <input
                  type="datetime-local"
                  min={nowLocalInput()}
                  {...register('publishedAt', {
                    setValueAs: (v) => (v === '' || v == null ? null : v),
                  })}
                  className="rounded border border-gray-300 px-3 py-2"
                />
                {errors.publishedAt && (
                  <span className="text-sm text-red-600">{errors.publishedAt.message}</span>
                )}
                <span className="text-xs text-gray-500">
                  지정한 시각에 자동 공개돼요. 그 전까지는 예약 상태로 비공개예요.
                </span>
              </div>
            )}
          </div>

          {!canPublish && (
            <p className="text-sm text-amber-600">
              본문에 내용(글 또는 이미지)이 있어야 발행할 수 있어요.
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={saving}
              className="rounded border border-gray-300 px-4 py-2 text-sm disabled:opacity-50"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={saving || !canPublish}
              className="rounded bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {saving
                ? mode === 'schedule'
                  ? '예약 중...'
                  : '발행 중...'
                : mode === 'schedule'
                  ? '예약하기'
                  : '발행하기'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
