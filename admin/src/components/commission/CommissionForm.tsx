import { Controller, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  COMMISSION_DESCRIPTION_MAX,
  COMMISSION_SHORT_TEXT_MAX,
  COMMISSION_TITLE_MAX,
  commissionItemSchema,
  type CommissionItemInput,
} from '../../lib/validation';

const SELECT_CLASS = 'w-full appearance-none rounded border border-gray-300 py-2 pl-3 pr-10';

// WorkForm의 SelectArrow와 같은 이유(Chrome 기본 select 화살표에 padding-right 미적용).
function SelectArrow() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500"
    >
      <path d="M6 8l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const IS_OPEN_HELP_ID = 'commission-is-open-help';

interface CommissionFormProps {
  defaultValues?: Partial<CommissionItemInput>;
  onSubmit: (data: CommissionItemInput) => void;
  isPending: boolean;
  error: string | null;
  submitLabel: string;
}

export function CommissionForm({
  defaultValues,
  onSubmit,
  isPending,
  error,
  submitLabel,
}: CommissionFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<CommissionItemInput>({
    resolver: zodResolver(commissionItemSchema),
    defaultValues: {
      title: '',
      description: '',
      price_text: '',
      duration_text: '',
      is_open: true,
      ...defaultValues,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">
          제목<span className="text-red-500"> *</span>
        </span>
        <input
          type="text"
          {...register('title')}
          maxLength={COMMISSION_TITLE_MAX}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {errors.title && <span className="text-sm text-red-600">{errors.title.message}</span>}
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">소개</span>
        <textarea
          {...register('description')}
          maxLength={COMMISSION_DESCRIPTION_MAX}
          rows={4}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {errors.description && (
          <span className="text-sm text-red-600">{errors.description.message}</span>
        )}
      </label>

      <div className="flex gap-4">
        <label className="flex flex-1 flex-col gap-1">
          <span className="text-sm font-medium">
            가격 표기<span className="text-red-500"> *</span>
          </span>
          <input
            type="text"
            {...register('price_text')}
            placeholder="예: 50,000원~ / 오마카세"
            maxLength={COMMISSION_SHORT_TEXT_MAX}
            className="rounded border border-gray-300 px-3 py-2"
          />
          {errors.price_text && (
            <span className="text-sm text-red-600">{errors.price_text.message}</span>
          )}
        </label>

        <label className="flex flex-1 flex-col gap-1">
          <span className="text-sm font-medium">소요 기간</span>
          <input
            type="text"
            {...register('duration_text')}
            placeholder="예: 2~3주"
            maxLength={COMMISSION_SHORT_TEXT_MAX}
            className="rounded border border-gray-300 px-3 py-2"
          />
          {errors.duration_text && (
            <span className="text-sm text-red-600">{errors.duration_text.message}</span>
          )}
        </label>
      </div>

      <div className="flex flex-col gap-1">
        <label className="flex flex-col gap-1">
          <span className="text-sm font-medium">슬롯 상태</span>
          <div className="relative">
            {/* WorkForm is_published와 같은 이유: register+setValueAs는 입력(문자열->boolean)만
                메꿔서 수정 폼이 서버 값을 못 반영한다(MISTAKES 폼 함정) - Controller로 양방향 처리. */}
            <Controller
              name="is_open"
              control={control}
              render={({ field }) => (
                <select
                  className={SELECT_CLASS}
                  aria-describedby={IS_OPEN_HELP_ID}
                  name={field.name}
                  ref={field.ref}
                  value={field.value ? 'true' : 'false'}
                  onChange={(e) => field.onChange(e.target.value === 'true')}
                  onBlur={field.onBlur}
                >
                  <option value="true">접수 중</option>
                  <option value="false">마감</option>
                </select>
              )}
            />
            <SelectArrow />
          </div>
        </label>
        <span id={IS_OPEN_HELP_ID} className="text-xs text-gray-500">
          마감으로 두면 카드에 마감 배지가 표시됩니다(목록에서는 계속 보임).
        </span>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
      >
        {isPending ? '저장 중...' : submitLabel}
      </button>
    </form>
  );
}
