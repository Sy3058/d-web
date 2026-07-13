import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { totpSchema, type TotpInput as TotpInputValue } from '../../lib/validation';

interface TotpInputProps {
  onSubmit: (data: TotpInputValue) => void;
  isPending: boolean;
  error: string | null;
}

export function TotpInput({ onSubmit, isPending, error }: TotpInputProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<TotpInputValue>({
    resolver: zodResolver(totpSchema),
    defaultValues: { code: '', remember_device: false },
  });

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex w-full max-w-xs flex-col gap-3"
    >
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">인증 코드</span>
        <input
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={6}
          placeholder="123456"
          {...register('code')}
          className="rounded border border-gray-300 px-3 py-2 tracking-widest"
        />
        {errors.code && <span className="text-sm text-red-600">{errors.code.message}</span>}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...register('remember_device')} />
        이 기기에서 30일간 2단계 인증 생략
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
      >
        {isPending ? '확인 중...' : '확인'}
      </button>
    </form>
  );
}
