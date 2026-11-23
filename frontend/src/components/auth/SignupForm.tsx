import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { signupSchema, type SignupInput } from '@/lib/validation';
import { api, ApiError, extractDetail } from '@/lib/api';
import { FormError, PasswordField, SubmitButton, TextField } from '@/components/ui/forms';
import { primaryControl } from '@/components/ui/controlStyles';

interface SendResponse { challenge_id: string; message: string; }
interface VerificationResponse { email: string | null; message?: string; }
type Phase = 'email' | 'code' | 'verified';
type Busy = 'restore' | 'send' | 'verify' | 'signup' | null;
const FALLBACK_ERROR = '처리 중 문제가 발생했어요. 잠시 후 다시 시도해 주세요.';

export default function SignupForm() {
  const form = useForm<SignupInput>({
    resolver: zodResolver(signupSchema),
    defaultValues: { email: '', nickname: '', password: '', passwordConfirm: '' },
  });
  const [phase, setPhase] = useState<Phase>('email');
  const [challengeId, setChallengeId] = useState('');
  const [code, setCode] = useState('');
  const [codeError, setCodeError] = useState('');
  const [verifiedEmail, setVerifiedEmail] = useState('');
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState<Busy>('restore');
  const [cooldown, setCooldown] = useState(0);
  const [done, setDone] = useState(false);
  const generation = useRef(0);
  const mounted = useRef(true);
  const lock = useRef(false);
  const canRestoreAnyEmail = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const requestGeneration = generation.current;
    const expectedEmail = form.getValues('email').trim().toLowerCase();
    lock.current = true;
    void api.get<VerificationResponse>('/auth/signup/verification').then((response) => {
      if (!mounted.current || requestGeneration !== generation.current || !response.email) return;
      if (expectedEmail ? response.email.toLowerCase() !== expectedEmail : !canRestoreAnyEmail.current) return;
      form.setValue('email', response.email);
      setVerifiedEmail(response.email);
      setPhase('verified');
      setFormError('');
    }).catch((cause) => {
      if (!mounted.current || requestGeneration !== generation.current) return;
      setFormError(cause instanceof ApiError
        ? extractDetail(cause) ?? FALLBACK_ERROR
        : '네트워크 오류로 이메일 인증 상태를 확인하지 못했어요.');
    }).finally(() => {
      if (mounted.current && requestGeneration === generation.current) {
        lock.current = false;
        setBusy(null);
      }
    });
    return () => {
      mounted.current = false;
      generation.current += 1;
      lock.current = false;
    };
  }, [form]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  function beginRequest(kind: Exclude<Busy, 'restore' | null>) {
    if (lock.current) return false;
    lock.current = true;
    setBusy(kind);
    setFormError('');
    if (kind === 'verify') setCodeError('');
    return true;
  }

  function finishRequest(requestGeneration: number) {
    if (mounted.current && requestGeneration === generation.current) {
      lock.current = false;
      setBusy(null);
    }
  }

  async function sendVerification() {
    if (!(await form.trigger('email')) || cooldown > 0 || !beginRequest('send')) return;
    const email = form.getValues('email').trim().toLowerCase();
    const requestGeneration = generation.current;
    try {
      const response = await api.post<SendResponse>('/auth/signup/send-verification', { email });
      if (!mounted.current || requestGeneration !== generation.current) return;
      if (form.getValues('email').trim().toLowerCase() !== email) return;
      setChallengeId(response.challenge_id);
      setCode('');
      setCodeError('');
      setPhase('code');
      setCooldown(60);
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      setFormError(cause instanceof ApiError
        ? extractDetail(cause) ?? FALLBACK_ERROR
        : '네트워크 오류로 인증 코드를 보내지 못했어요.');
    } finally { finishRequest(requestGeneration); }
  }

  async function verifyCode() {
    if (!/^\d{6}$/.test(code)) {
      setCodeError('인증 코드 6자리를 입력해 주세요.');
      return;
    }
    if (!challengeId || !beginRequest('verify')) return;
    const requestGeneration = generation.current;
    const expectedEmail = form.getValues('email').trim().toLowerCase();
    try {
      const response = await api.post<VerificationResponse>('/auth/signup/verify-email', {
        challenge_id: challengeId,
        code,
      });
      if (!mounted.current || requestGeneration !== generation.current) return;
      if (!response.email || response.email.toLowerCase() !== expectedEmail) {
        setFormError('인증한 이메일이 일치하지 않아요. 이메일을 다시 인증해 주세요.');
        return;
      }
      form.setValue('email', response.email);
      setVerifiedEmail(response.email);
      setPhase('verified');
      setFormError('');
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      setCodeError(cause instanceof ApiError
        ? extractDetail(cause) ?? FALLBACK_ERROR
        : '네트워크 오류로 인증 코드를 확인하지 못했어요.');
    } finally { finishRequest(requestGeneration); }
  }

  function changeEmail() {
    generation.current += 1;
    canRestoreAnyEmail.current = false;
    lock.current = false;
    setBusy(null);
    setPhase('email');
    setChallengeId('');
    setCode('');
    setCodeError('');
    setVerifiedEmail('');
    setCooldown(0);
    setFormError('');
    form.reset({ email: '', nickname: '', password: '', passwordConfirm: '' });
  }

  async function onSubmit(data: SignupInput) {
    if (phase !== 'verified' || !verifiedEmail || data.email !== verifiedEmail || !beginRequest('signup')) return;
    const requestGeneration = generation.current;
    try {
      await api.post('/auth/signup', { email: verifiedEmail, password: data.password, nickname: data.nickname });
      if (mounted.current && requestGeneration === generation.current) setDone(true);
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      const detail = cause instanceof ApiError ? extractDetail(cause) : undefined;
      if (cause instanceof ApiError && cause.status === 400) {
        changeEmail();
        setFormError(detail ?? '이메일 인증이 만료됐어요. 다시 인증해 주세요.');
      } else {
        setFormError(detail ?? FALLBACK_ERROR);
      }
    } finally { finishRequest(requestGeneration); }
  }

  function handleEmailChange() {
    if (phase !== 'email') return;
    generation.current += 1;
    canRestoreAnyEmail.current = false;
    lock.current = false;
    setBusy(null);
    setFormError('');
  }

  function handleFormSubmit(event: SyntheticEvent<HTMLFormElement, SubmitEvent>) {
    if (phase === 'verified') {
      void form.handleSubmit(onSubmit)(event);
      return;
    }
    event.preventDefault();
    if (phase === 'email') void sendVerification();
    else void verifyCode();
  }

  if (done) return (
    <div className="rounded-control border border-line px-6 py-8 text-center">
      <p className="mb-2 text-sm font-medium text-ink">회원가입이 완료됐어요.</p>
      <a href="/auth/login" className={`${primaryControl} w-full`}>로그인하기</a>
    </div>
  );

  const { onChange: registerEmailChange, ...emailRegistration } = form.register('email');
  const locked = busy !== null;
  return (
    <>
      <form onSubmit={handleFormSubmit} noValidate className="space-y-5">
        {phase === 'verified' ? (
          <div className="rounded-control border border-line px-4 py-3">
            <p className="text-sm font-medium text-ink">{verifiedEmail}</p>
            <p role="status" className="mt-1 text-sm text-ink">이메일이 인증되었습니다.</p>
            <button type="button" onClick={changeEmail} disabled={locked} className="mt-2 text-sm text-muted underline hover:text-ink">이메일 변경</button>
          </div>
        ) : (
          <>
          <TextField id="email" label="이메일" type="email" autoComplete="email"
            disabled={locked || phase === 'code'} error={form.formState.errors.email?.message}
            onChange={(event) => { void registerEmailChange(event); handleEmailChange(); }} {...emailRegistration} />
          {phase === 'email' && (
            <button type="button" onClick={() => void sendVerification()} disabled={locked}
              className={`${primaryControl} w-full`}>
              {busy === 'send' ? '보내는 중...' : '인증 코드 받기'}
            </button>
          )}
          {phase === 'code' && (
            <div className="space-y-3">
              <TextField id="verification-code" label="인증 코드" type="text" inputMode="numeric"
                autoComplete="one-time-code" maxLength={6} value={code} disabled={locked}
                error={codeError || undefined} onChange={(event) => {
                  setCode(event.target.value.replace(/\D/g, '').slice(0, 6));
                  setCodeError('');
                }} />
              <button type="button" onClick={() => void verifyCode()} disabled={locked}
                className={`${primaryControl} w-full`}>
                {busy === 'verify' ? '확인 중...' : '인증 코드 확인'}
              </button>
              <div className="flex gap-4 text-sm">
                <button type="button" onClick={() => void sendVerification()} disabled={locked || cooldown > 0} className="text-ink underline disabled:opacity-50 cursor-pointer">
                  {cooldown > 0 ? `${cooldown}초 후 다시 보내기` : '인증 코드 다시 받기'}
                </button>
                <button type="button" disabled={locked} onClick={changeEmail} className="text-muted underline cursor-pointer">이메일 변경</button>
              </div>
            </div>
          )}
          </>
        )}
        {phase === 'verified' && (
          <fieldset disabled={locked} className="space-y-5">
            <TextField id="nickname" label="닉네임" type="text" autoComplete="nickname" error={form.formState.errors.nickname?.message} {...form.register('nickname')} />
            <PasswordField id="password" label="비밀번호" autoComplete="new-password" error={form.formState.errors.password?.message} helper="8자 이상, 영문·숫자·특수문자를 각각 포함하세요." {...form.register('password')} />
            <PasswordField id="password-confirm" label="비밀번호 확인" autoComplete="new-password" error={form.formState.errors.passwordConfirm?.message} {...form.register('passwordConfirm')} />
          </fieldset>
        )}
        {formError && <FormError message={formError} />}
        {phase === 'verified' && <SubmitButton disabled={locked}>{busy === 'signup' ? '처리 중...' : '회원가입'}</SubmitButton>}
      </form>
      <p className="mt-8 text-sm text-muted text-center">
        이미 계정이 있나요?{' '}
        <a href="/auth/login" className="text-ink underline underline-offset-4">로그인</a>
      </p>
    </>
  );
}
