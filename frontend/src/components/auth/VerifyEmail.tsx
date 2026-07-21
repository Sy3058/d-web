import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema } from '../../lib/validation';
import { api, ApiError } from '../../lib/api';
import { TextField, SubmitButton, FormError, FormNotice } from '../ui/forms';

// 재발송 폼은 이메일만 필요 - 공용 loginSchema에서 email 규칙만 재사용.
const resendSchema = loginSchema.pick({ email: true });

export default function VerifyEmail() {
  const [token, setToken] = useState<string | null>(null);
  const [verifyState, setVerifyState] = useState<'idle' | 'verifying' | 'success' | 'error'>('idle');
  const [resendDone, setResendDone] = useState(false);
  const [resendError, setResendError] = useState('');

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<{ email: string }>({ resolver: zodResolver(resendSchema) });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setToken(params.get('token'));
  }, []);

  async function handleVerify() {
    if (!token || verifyState === 'verifying') return;
    setVerifyState('verifying');
    try {
      await api.post('/auth/verify-email', { token });
      setVerifyState('success');
    } catch {
      setVerifyState('error');
    }
  }

  async function onResend(data: { email: string }) {
    setResendError('');
    try {
      await api.post('/auth/resend-verification', { email: data.email });
      setResendDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setResendError('잠시 후 다시 시도해 주세요.');
      } else {
        setResendError('오류가 발생했어요. 잠시 후 다시 시도해 주세요.');
      }
    }
  }

  if (verifyState === 'success') {
    return (
      <div className="space-y-4">
        <FormNotice message="이메일 인증이 완료됐어요." />
        <p className="text-sm text-center">
          <a href="/auth/login" className="text-ink underline underline-offset-4">
            로그인하러 가기
          </a>
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {token !== null && (
        <div className="space-y-4">
          <p className="text-sm text-muted">아래 버튼을 눌러 이메일 인증을 완료하세요.</p>
          {verifyState === 'error' && (
            <FormError message="유효하지 않거나 만료된 인증 링크예요. 아래에서 인증 메일을 다시 받으세요." />
          )}
          {token && (
            <button
              type="button"
              onClick={handleVerify}
              disabled={verifyState === 'verifying'}
              className="w-full bg-ink text-paper text-sm font-medium tracking-wide py-2.5 px-4 rounded-control hover:bg-ink-strong disabled:opacity-50"
            >
              {verifyState === 'verifying' ? '인증 중...' : '이메일 인증 완료하기'}
            </button>
          )}
        </div>
      )}

      {token === null && (
        <p className="text-sm text-muted">
          인증 링크가 만료됐거나 링크를 찾을 수 없어요. 아래에서 인증 메일을 다시 받으세요.
        </p>
      )}

      <div className="border-t border-line pt-8 space-y-4">
        <p className="text-sm font-medium text-ink">인증 메일 재발송</p>
        {resendDone ? (
          <FormNotice message="입력하신 주소로 인증 메일을 보냈어요." />
        ) : (
          <form onSubmit={handleSubmit(onResend)} noValidate className="space-y-4">
            <TextField
              id="resend-email"
              label="이메일"
              type="email"
              autoComplete="email"
              error={errors.email?.message}
              {...register('email')}
            />
            {resendError && <FormError message={resendError} />}
            <SubmitButton disabled={isSubmitting}>
              {isSubmitting ? '발송 중...' : '인증 메일 다시 받기'}
            </SubmitButton>
          </form>
        )}
      </div>
    </div>
  );
}
