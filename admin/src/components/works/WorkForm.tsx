import { useEffect, useRef, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { TAG_NAME_MAX, workSchema, type WorkInput } from '../../lib/validation';
import { WORK_STATUS_OPTIONS } from '../../lib/workStatus';
import type { WorkStatus } from '../../types';
import { TagInput } from './TagInput';
import { CoverCropModal } from './CoverCropModal';

// Chrome은 기본 select 화살표에 padding-right를 적용하지 않아 화살표가 테두리에 딱 붙는다.
// 기본 화살표를 끄고(appearance-none) 직접 그려 위치를 잡는다. select가 둘이라 마크업을 뺐다.
// ⚠️ absolute 배치라 **부모에 relative가 있어야** 한다 - 없으면 에러 없이 폼 전체 기준으로 날아간다.
function SelectArrow() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      // pointer-events-none이라야 화살표를 클릭해도 select가 열린다.
      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500"
    >
      <path d="M6 8l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const SELECT_CLASS = 'w-full appearance-none rounded border border-gray-300 py-2 pl-3 pr-10';

// aria-describedby와 도움말 span의 id를 한 곳에서 잡는다 - 문자열을 양쪽에 따로 쓰면
// 한쪽만 고쳤을 때 연결이 조용히 끊긴다(화면상 차이가 없어 눈으로는 못 잡는다).
const IS_PUBLISHED_HELP_ID = 'work-is-published-help';

interface WorkFormProps {
  defaultValues?: Partial<WorkInput>;
  hasExistingCover?: boolean;
  onSubmit: (data: WorkInput, coverFile: File | null) => void;
  isPending: boolean;
  error: string | null;
  submitLabel: string;
}

export function WorkForm({
  defaultValues,
  hasExistingCover,
  onSubmit,
  isPending,
  error,
  submitLabel,
}: WorkFormProps) {
  const [coverFile, setCoverFile] = useState<File | null>(null);
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [isCropModalOpen, setCropModalOpen] = useState(false);

  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors },
  } = useForm<WorkInput>({
    resolver: zodResolver(workSchema),
    defaultValues: {
      title: '',
      synopsis: '',
      episode_base_price: 500,
      // 전편 묶음 할인은 1차 미노출(사용자 결정, 2026-07-14) - 폼에 입력 필드를 두지 않고
      // 항상 0으로 고정 전송한다. 값 자체는 M3 결제 로직이 참조하므로 스키마엔 남겨둔다.
      bundle_discount_rate: 0,
      status: 'ongoing',
      // 백엔드 기본값(WorkCreate.is_published=False)과 동일 - admin에서 새로 만드는 작품은
      // 명시적으로 켜기 전까지 공개 카탈로그에 노출되지 않는다.
      is_published: false,
      tag_names: [],
      ...defaultValues,
    },
  });

  // CoverCropModal과 같은 이유로 ref에 들고 명시적으로 revoke한다(교체·해제·언마운트).
  // useEffect([coverPreview])로 걸면 StrictMode의 mount→cleanup→mount에서 화면이 아직
  // 쓰는 URL을 revoke해 미리보기가 깨진다.
  const previewUrlRef = useRef<string | null>(null);
  useEffect(
    () => () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    },
    [],
  );

  const setCover = (file: File | null) => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = file ? URL.createObjectURL(file) : null;
    setCoverFile(file);
    setCoverPreview(previewUrlRef.current);
  };

  const handleCropComplete = (file: File) => {
    setCover(file);
    setCropModalOpen(false);
  };

  const clearCover = () => setCover(null);

  const submit = (data: WorkInput) => onSubmit(data, coverFile);

  // 준비중을 고르면 공개 상태의 "기본값"도 비공개로 내린다(#84 - 강제 아님, 이후 수동으로
  // 공개로 되돌리면 그 값이 유지된다). 나머지 상태는 공개 상태를 건드리지 않는다.
  //
  // 자동으로 공개를 켜는 방향(ongoing->공개)은 의도적으로 두지 않는다. 이 폼의 기본값이
  // status=ongoing + is_published=false라 그 규칙과 모순되고, 등록 화면에서 상태를 골랐다
  // 되돌리기만 해도 회차 없는 새 작품이 공개로 생성됐다(위 defaultValues 주석의 계약 위반).
  // 노출은 한 번 일어나면 되돌릴 수 없으니 자동 연동은 안전한 방향(숨김)에만 건다.
  //
  // 수정 폼의 초기 로드(서버 값 주입)에서는 절대 발화하면 안 되는 규칙이다.
  const syncPublishDefault = (next: WorkStatus) => {
    if (next === 'preparing') setValue('is_published', false, { shouldDirty: true });
  };

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">
          제목<span className="text-red-500"> *</span>
        </span>
        <input
          type="text"
          {...register('title')}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {errors.title && <span className="text-sm text-red-600">{errors.title.message}</span>}
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">시놉시스</span>
        <textarea
          {...register('synopsis')}
          rows={4}
          className="rounded border border-gray-300 px-3 py-2"
        />
      </label>

      <div className="flex gap-6">
        <div className="flex flex-col items-start gap-2">
          <span className="text-sm font-medium">표지 이미지</span>
          <div className="relative">
            <div className="flex aspect-[3/4] w-36 items-center justify-center overflow-hidden rounded border border-dashed border-gray-300 bg-gray-100 text-sm text-gray-400">
              {coverPreview ? (
                <img
                  src={coverPreview}
                  alt="표지 미리보기"
                  className="h-full w-full object-cover"
                />
              ) : (
                <span>표지 미리보기</span>
              )}
            </div>
            {/* 새로 고른(크롭된) 표지만 지울 수 있다 - 이미 R2에 저장된 기존 표지를
                삭제하는 API는 아직 없다(백엔드는 업로드/덮어쓰기만 제공). */}
            {coverPreview && (
              <button
                type="button"
                onClick={clearCover}
                className="absolute -right-2 -top-2 flex h-6 w-6 cursor-pointer items-center justify-center rounded-full bg-gray-900 text-xs text-white"
                aria-label="선택한 표지 지우기"
              >
                ×
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => setCropModalOpen(true)}
            className="w-36 rounded border border-gray-300 px-3 py-1.5 text-center text-sm hover:bg-gray-50"
          >
            표지 선택
          </button>
          {!coverPreview && hasExistingCover && (
            <p className="text-sm text-gray-500">표지가 등록되어 있습니다.</p>
          )}
        </div>

        <div className="flex flex-1 flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">회차 기본가 (원)</span>
            <input
              type="number"
              min={0}
              // 스피너(위/아래 버튼)를 10원 단위로. 직접 타이핑하는 값은 제한하지 않는다
              // (form에 noValidate가 걸려 브라우저 step 검사는 안 돌고, 검증은 zod 담당).
              step={10}
              {...register('episode_base_price', { valueAsNumber: true })}
              className="rounded border border-gray-300 px-3 py-2"
            />
            {errors.episode_base_price && (
              <span className="text-sm text-red-600">{errors.episode_base_price.message}</span>
            )}
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-sm font-medium">연재 상태</span>
            <div className="relative">
              <select
                {...register('status', {
                  onChange: (e) => syncPublishDefault(e.target.value as WorkStatus),
                })}
                className={SELECT_CLASS}
              >
                {WORK_STATUS_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <SelectArrow />
            </div>
          </label>

          {/* 도움말은 label 밖에 둔다 - 안에 넣으면 label 텍스트가 통째로 select의 접근성
              이름이 돼서 스크린리더가 "공개 상태 공개로 두면 독자 사이트..."로 읽는다.
              이름은 label, 설명은 aria-describedby로 분리한다. */}
          <div className="flex flex-col gap-1">
            <label className="flex flex-col gap-1">
              <span className="text-sm font-medium">공개 상태</span>
              <div className="relative">
                {/* select 값은 문자열, 스키마·백엔드 계약은 boolean이라 양방향 변환이 필요하다.
                    register+setValueAs는 입력(문자열->boolean)만 메꿔서, 수정 폼이 서버의
                    is_published=true를 못 반영하고 늘 "비공개"로 뜬다(테스트로 실측). */}
                <Controller
                  name="is_published"
                  control={control}
                  render={({ field }) => (
                    <select
                      className={SELECT_CLASS}
                      aria-describedby={IS_PUBLISHED_HELP_ID}
                      name={field.name}
                      ref={field.ref}
                      value={field.value ? 'true' : 'false'}
                      onChange={(e) => field.onChange(e.target.value === 'true')}
                      onBlur={field.onBlur}
                    >
                      <option value="true">공개</option>
                      <option value="false">비공개</option>
                    </select>
                  )}
                />
                <SelectArrow />
              </div>
            </label>
            <span id={IS_PUBLISHED_HELP_ID} className="text-xs text-gray-500">
              공개로 두면 독자 사이트 작품 목록에 노출됩니다.
            </span>
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium">태그</span>
        <Controller
          name="tag_names"
          control={control}
          render={({ field }) => <TagInput value={field.value} onChange={field.onChange} />}
        />
        {/* 안 그리면 무효한 태그가 들어왔을 때 제출이 아무 안내 없이 막힌다
            (RHF는 onValid를 호출하지 않을 뿐 화면엔 변화가 없다). */}
        {errors.tag_names && (
          <span className="text-sm text-red-600">태그는 1~{TAG_NAME_MAX}자여야 합니다.</span>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
      >
        {isPending ? '저장 중...' : submitLabel}
      </button>

      {isCropModalOpen && (
        <CoverCropModal onClose={() => setCropModalOpen(false)} onComplete={handleCropComplete} />
      )}
    </form>
  );
}
