import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, type LoginInput } from '@d-web/shared';

interface LoginFormProps {
  onSubmit: (data: LoginInput) => void;
  isPending: boolean;
  error: string | null;
}

export function LoginForm({ onSubmit, isPending, error }: LoginFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="flex w-full max-w-xs flex-col gap-3"
    >
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">이메일</span>
        <input
          type="email"
          autoComplete="email"
          {...register('email')}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {errors.email && <span className="text-sm text-red-600">{errors.email.message}</span>}
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium">비밀번호</span>
        <input
          type="password"
          autoComplete="current-password"
          {...register('password')}
          className="rounded border border-gray-300 px-3 py-2"
        />
        {errors.password && (
          <span className="text-sm text-red-600">{errors.password.message}</span>
        )}
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        type="submit"
        disabled={isPending}
        className="rounded bg-gray-900 px-3 py-2 text-white disabled:opacity-50"
      >
        {isPending ? '로그인 중...' : '로그인'}
      </button>
    </form>
  );
}
