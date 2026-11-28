import { useEffect, useRef, useState, type ChangeEvent, type SyntheticEvent } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiError } from '@/lib/api';
import { FormError, SubmitButton, TextField } from '@/components/ui/forms';

const forgotPasswordSchema = z.object({
  email: z.email('올바른 이메일 주소를 입력해 주세요.'),
});

type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>;

const GENERIC_SUCCESS =
  '입력한 이메일로 비밀번호 재설정 링크를 전송했습니다.';

export default function ForgotPasswordForm() {
  const form = useForm<ForgotPasswordInput>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });
  const [sent, setSent] = useState(false);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const requestOwner = useRef<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const invalidate = () => {
      mounted.current = false;
      generation.current += 1;
      requestOwner.current = null;
      setBusy(false);
      setSent(false);
      setFormError('');
    };
    const restore = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      mounted.current = true;
      generation.current += 1;
      requestOwner.current = null;
      setBusy(false);
    };
    window.addEventListener('pagehide', invalidate);
    window.addEventListener('pageshow', restore);
    return () => {
      mounted.current = false;
      generation.current += 1;
      requestOwner.current = null;
      window.removeEventListener('pagehide', invalidate);
      window.removeEventListener('pageshow', restore);
    };
  }, []);

  async function sendRequest(data: ForgotPasswordInput, submittedEmail: string, requestGeneration: number) {
    if (data.email.trim().toLowerCase() !== submittedEmail
      || form.getValues('email').trim().toLowerCase() !== submittedEmail
      || generation.current !== requestGeneration) return;
    try {
      await api.post('/auth/forgot-password', { email: submittedEmail });
      if (!mounted.current || generation.current !== requestGeneration
        || form.getValues('email').trim().toLowerCase() !== submittedEmail) return;
      setSent(true);
    } catch (cause) {
      if (!mounted.current || generation.current !== requestGeneration
        || form.getValues('email').trim().toLowerCase() !== submittedEmail) return;
      setFormError(
        cause instanceof ApiError && cause.status === 429
          ? '요청이 너무 많아요. 잠시 후 다시 시도해 주세요.'
          : '재설정 링크를 보내지 못했어요. 잠시 후 다시 시도해 주세요.',
      );
    }
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement, SubmitEvent>) {
    event.preventDefault();
    if (requestOwner.current !== null) return;
    const submittedEmail = form.getValues('email').trim().toLowerCase();
    const requestGeneration = generation.current;
    requestOwner.current = requestGeneration;
    setBusy(true);
    setSent(false);
    setFormError('');
    void form.handleSubmit((data) => sendRequest(data, submittedEmail, requestGeneration))(event)
      .finally(() => {
        if (requestOwner.current === requestGeneration && generation.current === requestGeneration) {
          requestOwner.current = null;
          setBusy(false);
        }
      });
  }

  const { onChange: registerEmailChange, ...emailRegistration } = form.register('email');

  function handleEmailChange(event: ChangeEvent<HTMLInputElement>) {
    void registerEmailChange(event);
    generation.current += 1;
    requestOwner.current = null;
    setBusy(false);
    setSent(false);
    setFormError('');
  }

  return (
    <>
      <p className="mb-5 text-sm text-muted">
        가입한 이메일을 입력해 주세요. 링크는 발급 후 1시간 동안 사용할 수 있어요.
      </p>
      <form method="post" onSubmit={handleSubmit} noValidate className="space-y-5">
        <TextField
          id="email"
          label="이메일"
          type="email"
          autoComplete="email"
          disabled={busy}
          error={form.formState.errors.email?.message}
          onChange={handleEmailChange}
          {...emailRegistration}
        />
        {sent && <div role="status" className="rounded-control border border-line px-4 py-3 text-sm text-ink">{GENERIC_SUCCESS}</div>}
        {formError && <FormError message={formError} />}
        <SubmitButton disabled={busy}>
          {busy ? '보내는 중...' : sent ? '재설정 링크 다시 받기' : '재설정 링크 받기'}
        </SubmitButton>
      </form>
      <p className="mt-6 text-sm text-muted">
        Google로 가입했다면 비밀번호 대신 로그인 화면의 Google 로그인을 이용해 주세요.
      </p>
      <p className="mt-8 text-center text-sm text-muted">
        <a href="/auth/login" className="text-ink underline underline-offset-4">로그인으로 돌아가기</a>
      </p>
    </>
  );
}
