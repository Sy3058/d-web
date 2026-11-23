import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiError, extractDetail } from '@/lib/api';
import { getMe, type User } from '@/lib/auth';
import { signupSchema } from '@/lib/validation';
import { FormError, PasswordField } from '@/components/ui/forms';
import { controlBase, ghostControl } from '@/components/ui/controlStyles';

export const passwordChangeSchema = z.object({
  current_password: z.string().min(1, '현재 비밀번호를 입력해 주세요.').max(128),
  new_password: signupSchema.shape.password,
  confirm_password: z.string().min(1, '새 비밀번호를 다시 입력해 주세요.').max(128),
}).refine((value) => value.new_password === value.confirm_password, {
  message: '새 비밀번호 확인이 일치하지 않습니다.',
  path: ['confirm_password'],
});
type PasswordInput = z.infer<typeof passwordChangeSchema>;

export default function PasswordEditor({ initialUser }: { initialUser: User }) {
  const [user, setUser] = useState(initialUser);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [needsLogin, setNeedsLogin] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const lock = useRef(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const pendingRequest = useRef<Promise<unknown> | null>(null);
  const form = useForm<PasswordInput>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });
  const { reset } = form;
  const disabled = busy || needsLogin || restoreFailed;
  const canChangePassword = user.has_password && user.role !== 'owner';

  useEffect(() => {
    mounted.current = true;
    function resetDraft() {
      generation.current += 1;
      lock.current = false;
      setBusy(false);
      setRestoring(false);
      setRestoreFailed(false);
      reset();
      setError('');
      setNotice('');
    }
    function pageHide() {
      mounted.current = false;
      resetDraft();
    }
    async function restoreAccount() {
      const pending = pendingRequest.current;
      resetDraft();
      mounted.current = true;
      const restoreGeneration = generation.current;
      lock.current = true;
      setBusy(true);
      setRestoring(true);
      try {
        // Wait for the password change's new session cookies before checking the account.
        if (pending) await pending.catch(() => undefined);
        if (!mounted.current || restoreGeneration !== generation.current) return;
        const currentUser = await getMe();
        if (!mounted.current || restoreGeneration !== generation.current) return;
        if (!currentUser) {
          setNeedsLogin(true);
          setError('로그인이 만료됐어요. 다시 로그인해 주세요.');
          return;
        }
        setUser(currentUser);
        setNeedsLogin(false);
        window.dispatchEvent(new Event('dweb:account-updated'));
      } catch {
        if (!mounted.current || restoreGeneration !== generation.current) return;
        setRestoreFailed(true);
        setError('서버의 최신 계정 정보를 확인하지 못했어요. 페이지를 새로 열어 변경 여부를 확인해 주세요.');
      } finally {
        if (mounted.current && restoreGeneration === generation.current) {
          lock.current = false;
          setBusy(false);
          setRestoring(false);
        }
      }
    }
    function pageShow(event: PageTransitionEvent) {
      if (event.persisted) void restoreAccount();
    }
    window.addEventListener('pagehide', pageHide);
    window.addEventListener('pageshow', pageShow);
    return () => {
      mounted.current = false;
      generation.current += 1;
      window.removeEventListener('pagehide', pageHide);
      window.removeEventListener('pageshow', pageShow);
    };
  }, [reset]);

  async function savePassword(values: PasswordInput) {
    if (!mounted.current || lock.current || needsLogin || restoreFailed || !canChangePassword) return;
    const requestGeneration = generation.current;
    lock.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    let request: Promise<unknown> | undefined;
    try {
      request = api.post('/auth/me/password', values);
      pendingRequest.current = request;
      await request;
      if (!mounted.current || requestGeneration !== generation.current) return;
      form.reset();
      setNeedsLogin(false);
      setNotice('비밀번호를 변경했어요.');
      window.dispatchEvent(new Event('dweb:account-updated'));
    } catch (cause) {
      if (!mounted.current || requestGeneration !== generation.current) return;
      if (cause instanceof ApiError) {
        if (cause.status === 401) {
          form.reset();
          setNeedsLogin(true);
          setError('로그인이 만료됐어요. 다시 로그인해 주세요.');
        } else {
          setError(extractDetail(cause) ?? '변경하지 못했어요. 잠시 후 다시 시도해 주세요.');
        }
      } else {
        setError('통신 오류로 변경 결과를 확인하지 못했어요. 계정 상태를 확인한 뒤 다시 시도해 주세요.');
      }
    } finally {
      if (pendingRequest.current === request) pendingRequest.current = null;
      if (mounted.current && requestGeneration === generation.current) {
        lock.current = false;
        setBusy(false);
      }
    }
  }

  if (!canChangePassword && !needsLogin) return <div className="space-y-4">{error && <FormError message={error} />}{restoring && <p role="status" className="text-sm text-muted">정보 확인 중...</p>}<p className="text-sm text-muted">{user.role === 'owner' ? '관리자 계정은 이 화면에서 비밀번호를 변경할 수 없어요.' : '소셜 로그인 계정은 로그인한 서비스에서 비밀번호를 관리해 주세요.'}</p><a href="/my" className={ghostControl} data-astro-reload>계정으로 돌아가기</a></div>;

  return (
    <form method="post" noValidate onSubmit={(event) => { void form.handleSubmit(savePassword)(event); }} className="space-y-6">
      {error && <FormError message={error} />}
      {notice && <p role="status" className="text-sm text-ink">{notice}</p>}
      {needsLogin && <a href="/auth/login" className={ghostControl} data-astro-reload>다시 로그인</a>}
      <fieldset disabled={disabled} className="space-y-5">
        <PasswordField id="current-password" label="현재 비밀번호" autoComplete="current-password" maxLength={128} error={form.formState.errors.current_password?.message} {...form.register('current_password')} />
        <PasswordField id="new-password" label="새 비밀번호" autoComplete="new-password" maxLength={128} helper="8~128자, 영문, 숫자, 특수문자를 각각 포함하세요." error={form.formState.errors.new_password?.message} {...form.register('new_password')} />
        <PasswordField id="confirm-password" label="새 비밀번호 확인" autoComplete="new-password" maxLength={128} helper="다른 기기에서는 로그아웃됩니다." error={form.formState.errors.confirm_password?.message} {...form.register('confirm_password')} />
        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-6">
          <button type="submit" disabled={disabled} className={`${controlBase} bg-ink px-5 py-2.5 text-paper hover:bg-ink-strong`}>{restoring ? '정보 확인 중...' : busy ? '변경 중...' : '비밀번호 변경'}</button>
          <a href="/my" className={ghostControl} aria-disabled={busy || undefined} onClick={(event) => { if (lock.current) event.preventDefault(); }} data-astro-reload>취소</a>
        </div>
      </fieldset>
    </form>
  );
}
