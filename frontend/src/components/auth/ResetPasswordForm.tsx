import { useCallback, useEffect, useLayoutEffect, useRef, useState, type SyntheticEvent } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiError, extractDetail } from '@/lib/api';
import { signupSchema } from '@/lib/validation';
import { FormError, PasswordField, SubmitButton } from '@/components/ui/forms';
import { primaryControl } from '@/components/ui/controlStyles';

const resetPasswordSchema = z
  .object({
    password: signupSchema.shape.password,
    passwordConfirm: z.string(),
  })
  .refine((data) => data.password === data.passwordConfirm, {
    message: '비밀번호가 일치하지 않습니다.',
    path: ['passwordConfirm'],
  });

type ResetPasswordInput = z.infer<typeof resetPasswordSchema>;
type TokenState = 'loading' | 'ready' | 'missing' | 'discarded';

export default function ResetPasswordForm() {
  const form = useForm<ResetPasswordInput>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: '', passwordConfirm: '' },
  });
  const [tokenState, setTokenState] = useState<TokenState>('loading');
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const token = useRef('');
  const generation = useRef(0);
  const requestOwner = useRef<number | null>(null);
  const mounted = useRef(true);

  const discardSecrets = useCallback((state: TokenState = 'discarded') => {
    generation.current += 1;
    requestOwner.current = null;
    token.current = '';
    form.reset({ password: '', passwordConfirm: '' });
    setBusy(false);
    setFormError('');
    setTokenState(state);
  }, [form]);

  const adoptFragmentToken = useCallback(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const nextToken = fragment.get('token') ?? '';
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    mounted.current = true;
    generation.current += 1;
    requestOwner.current = null;
    token.current = nextToken;
    form.reset({ password: '', passwordConfirm: '' });
    setBusy(false);
    setFormError('');
    setDone(false);
    setTokenState(nextToken ? 'ready' : 'missing');
  }, [form]);

  useLayoutEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    token.current = fragment.get('token') ?? '';
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    generation.current += 1;
    mounted.current = true;
    setTokenState(token.current ? 'ready' : 'missing');
  }, []);

  useEffect(() => {
    mounted.current = true;
    const handlePageHide = () => {
      mounted.current = false;
      discardSecrets();
    };
    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        mounted.current = true;
        discardSecrets();
      }
    };
    const handleHashChange = () => adoptFragmentToken();
    window.addEventListener('pagehide', handlePageHide);
    window.addEventListener('pageshow', handlePageShow);
    window.addEventListener('hashchange', handleHashChange);
    return () => {
      mounted.current = false;
      generation.current += 1;
      requestOwner.current = null;
      token.current = '';
      form.reset({ password: '', passwordConfirm: '' });
      window.removeEventListener('pagehide', handlePageHide);
      window.removeEventListener('pageshow', handlePageShow);
      window.removeEventListener('hashchange', handleHashChange);
    };
  }, [adoptFragmentToken, discardSecrets, form]);

  async function submitRequest(
    data: ResetPasswordInput,
    requestToken: string,
    requestGeneration: number,
  ) {
    if (generation.current !== requestGeneration || token.current !== requestToken) return;
    try {
      await api.post('/auth/reset-password', {
        token: requestToken,
        new_password: data.password,
      });
      if (!mounted.current || requestGeneration !== generation.current) return;
      token.current = '';
      form.reset({ password: '', passwordConfirm: '' });
      setDone(true);
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      if (cause instanceof ApiError && cause.status === 400) {
        token.current = '';
        form.reset({ password: '', passwordConfirm: '' });
        setTokenState('missing');
        setFormError('재설정 링크가 유효하지 않거나 만료되었어요. 새 링크를 요청해 주세요.');
      } else if (cause instanceof ApiError && cause.status === 422) {
        setFormError(extractDetail(cause) ?? '다른 비밀번호를 사용해 주세요.');
      } else if (cause instanceof ApiError && cause.status === 429) {
        setFormError('요청이 너무 많아요. 잠시 후 다시 시도해 주세요.');
      } else {
        setFormError('변경 결과를 확인하지 못했어요. 새 비밀번호로 로그인하거나 새 링크를 요청해 주세요.');
      }
    }
  }

  function handleFormSubmit(event: SyntheticEvent<HTMLFormElement, SubmitEvent>) {
    event.preventDefault();
    if (tokenState !== 'ready' || !token.current || requestOwner.current !== null) return;
    const requestToken = token.current;
    const requestGeneration = generation.current;
    requestOwner.current = requestGeneration;
    setBusy(true);
    setFormError('');
    void form.handleSubmit((data) => submitRequest(data, requestToken, requestGeneration))(event)
      .finally(() => {
        if (requestOwner.current === requestGeneration && generation.current === requestGeneration) {
          requestOwner.current = null;
          setBusy(false);
        }
      });
  }

  if (done) return (
    <div className="rounded-control border border-line px-6 py-8 text-center">
      <p role="status" className="mb-2 text-sm font-medium text-ink">비밀번호가 변경됐어요.</p>
      <p className="mb-5 text-sm text-muted">새 비밀번호로 다시 로그인해 주세요.</p>
      <a href="/auth/login" data-astro-reload className={`${primaryControl} w-full`}>로그인하기</a>
    </div>
  );

  if (tokenState === 'loading') return <p role="status" className="text-sm text-muted">재설정 링크를 확인하고 있어요.</p>;

  if (tokenState !== 'ready') return (
    <div className="space-y-5">
      {formError && <FormError message={formError} />}
      {!formError && <FormError message="재설정 정보가 없어요. 이메일로 받은 새 링크를 열어 주세요." />}
      <a href="/auth/forgot-password" data-astro-reload className={`${primaryControl} w-full`}>재설정 링크 다시 받기</a>
    </div>
  );

  return (
    <form method="post" onSubmit={handleFormSubmit} noValidate className="space-y-5">
      <PasswordField id="password" label="새 비밀번호" autoComplete="new-password"
        maxLength={128}
        helper="8자 이상, 영문·숫자·특수문자를 각각 포함하세요."
        error={form.formState.errors.password?.message} {...form.register('password')} />
      <PasswordField id="password-confirm" label="새 비밀번호 확인" autoComplete="new-password"
        maxLength={128}
        error={form.formState.errors.passwordConfirm?.message} {...form.register('passwordConfirm')} />
      {formError && <FormError message={formError} />}
      <SubmitButton disabled={busy}>
        {busy ? '변경 중...' : '비밀번호 변경'}
      </SubmitButton>
    </form>
  );
}
