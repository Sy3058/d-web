import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, type LoginInput } from '@/lib/validation';
import { api, ApiError, extractDetail } from '@/lib/api';
import { TextField, PasswordField, SubmitButton, FormError } from '@/components/ui/forms';

export function redirectToMyPage(location: Pick<Location, 'assign'> = window.location) {
  location.assign('/my');
}

interface LoginFormProps {
  redirect?: () => void;
}

export default function LoginForm({ redirect = redirectToMyPage }: LoginFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });
  const [formError, setFormError] = useState('');
  const [showVerificationHelp, setShowVerificationHelp] = useState(false);

  async function onSubmit(data: LoginInput) {
    setFormError('');
    setShowVerificationHelp(false);
    try {
      await api.post('/auth/login', data);
      redirect();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setFormError('잠시 후 다시 시도해 주세요.');
        } else if (err.status === 401) {
          setFormError('이메일 또는 비밀번호가 올바르지 않습니다.');
          setShowVerificationHelp(true);
        } else {
          setFormError(
            extractDetail(err) ?? '로그인 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.',
          );
        }
      } else {
        setFormError('네트워크 오류가 발생했어요. 잠시 후 다시 시도해 주세요.');
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
      <TextField
        id="email"
        label="이메일"
        type="email"
        autoComplete="email"
        error={errors.email?.message}
        {...register('email')}
      />
      <PasswordField
        id="password"
        label="비밀번호"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register('password')}
      />
      <div className="text-right">
        <a href="/auth/forgot-password" className="text-sm text-ink underline underline-offset-4">
          비밀번호를 잊으셨나요?
        </a>
      </div>
      {formError && <FormError message={formError} />}
      {showVerificationHelp && (
        <p className="text-sm text-muted">
          이메일 인증을 완료하지 않았다면{' '}
          <a href="/auth/verify-email" className="text-ink underline hover:text-ink-strong">
            이메일 인증 메일 다시 받기
          </a>
          를 이용해 주세요.
        </p>
      )}
      <SubmitButton disabled={isSubmitting}>
        {isSubmitting ? '처리 중...' : '로그인'}
      </SubmitButton>
    </form>
  );
}
