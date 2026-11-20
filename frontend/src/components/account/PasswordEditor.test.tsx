// @vitest-environment jsdom
import { act, StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import type { User } from '@/lib/auth';
import PasswordEditor, { passwordChangeSchema } from './PasswordEditor';

const { post, getMe } = vi.hoisted(() => ({ post: vi.fn(), getMe: vi.fn() }));
vi.mock('@/lib/api', async (original) => {
  const module = await original<typeof import('@/lib/api')>();
  return { ...module, api: { ...module.api, post } };
});
vi.mock('@/lib/auth', () => ({ getMe }));
const user: User = {
  id: 'reader-1', email: 'reader@example.com', nickname: '독자', profile_image: null,
  role: 'reader', has_password: true, is_email_verified: true, created_at: '2026-11-16T00:00:00Z',
};
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  getMe.mockReset(); getMe.mockResolvedValue(user);
  post.mockReset(); container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); });
async function render(initialUser = user) { await act(async () => root.render(<PasswordEditor initialUser={initialUser} />)); }
async function input(id: string, value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>(`#${id}`)!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
async function fill(confirm = 'NewPassword!234') {
  await input('current-password', 'OldPassword!234'); await input('new-password', 'NewPassword!234'); await input('confirm-password', confirm);
}
async function save() { await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click()); }

async function transition(type: 'pagehide' | 'pageshow', persisted = true) {
  await act(async () => window.dispatchEvent(new PageTransitionEvent(type, { persisted })));
}

describe('비밀번호 편집', () => {
  it('확인 비밀번호 오류를 확인 입력에 연결하고 서버를 호출하지 않는다', async () => {
    await render(); await fill('Mismatch!234'); await save();
    expect(container.querySelector('#confirm-password')?.getAttribute('aria-invalid')).toBe('true');
    expect(container.querySelector('#confirm-password-error')?.textContent).toContain('일치하지 않습니다'); expect(post).not.toHaveBeenCalled();
  });
  it('현재 비밀번호 오류를 표시하고 성공하면 입력을 비우고 현재 로그인을 유지한다', async () => {
    post.mockRejectedValueOnce(new ApiError(400, '{"detail":"현재 비밀번호가 올바르지 않습니다"}'));
    await render(); await fill(); await save(); expect(container.textContent).toContain('현재 비밀번호가 올바르지 않습니다');
    post.mockResolvedValueOnce({ message: '변경됨' }); await save();
    expect(post).toHaveBeenLastCalledWith('/auth/me/password', { current_password: 'OldPassword!234', new_password: 'NewPassword!234', confirm_password: 'NewPassword!234' });
    expect(container.querySelector<HTMLInputElement>('#current-password')!.value).toBe(''); expect(container.querySelector<HTMLInputElement>('#new-password')!.value).toBe('');
    expect(container.querySelector('a[href="/auth/login"]')).toBeNull(); expect(container.querySelector('fieldset')?.disabled).toBe(false);
    expect(container.querySelector('[role="status"]')?.textContent).toBe('비밀번호를 변경했어요.');
    expect(container.textContent).toContain('다른 기기에서는 로그아웃됩니다.');
    expect(container.textContent).not.toContain('순차');
  });
  it('변경 성공 뒤 BFCache에서 최신 로그인 계정을 복원하고 다시 편집할 수 있다', async () => {
    post.mockResolvedValueOnce({ message: '변경됨' });
    await render(); await fill(); await save();
    await transition('pagehide'); await transition('pageshow');
    expect(getMe).toHaveBeenCalledOnce();
    expect(container.querySelector('a[href="/auth/login"]')).toBeNull();
    expect(container.querySelector('fieldset')?.disabled).toBe(false);
    post.mockResolvedValueOnce({ message: '다시 변경됨' });
    await fill(); await save();
    expect(post).toHaveBeenCalledTimes(2);
    expect(container.querySelector('fieldset')?.disabled).toBe(false);
  });
  it('소셜 전용 계정에는 비밀번호 입력을 제공하지 않는다', async () => {
    await render({ ...user, has_password: false }); expect(container.querySelector('input[type="password"]')).toBeNull(); expect(container.textContent).toContain('소셜 로그인 계정');
  });
  it('관리자 계정에는 로컬 비밀번호가 있어도 변경 입력을 제공하지 않는다', async () => {
    await render({ ...user, role: 'owner' });
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent).toContain('관리자 계정은 이 화면에서 비밀번호를 변경할 수 없어요.');
    expect(post).not.toHaveBeenCalled();
  });
  it('서버 409와 422 오류를 표시한다', async () => {
    await render(); await fill(); post.mockRejectedValueOnce(new ApiError(409, '{"detail":"소셜 계정은 변경할 수 없습니다"}')); await save();
    expect(container.textContent).toContain('소셜 계정은 변경할 수 없습니다');
    post.mockRejectedValueOnce(new ApiError(422, '{"detail":"유출 이력이 있는 비밀번호입니다"}')); await save(); expect(container.textContent).toContain('유출 이력이 있는 비밀번호입니다');
  });
  it('통신 실패는 변경 여부를 단정하지 않고 최종401은 입력을 지운다', async () => {
    await render(); await fill(); post.mockRejectedValueOnce(new TypeError('network')); await save(); expect(container.textContent).toContain('변경 결과를 확인하지 못했어요');
    post.mockRejectedValueOnce(new ApiError(401, 'unauthenticated')); await save(); expect(container.textContent).toContain('로그인이 만료됐어요');
    expect(container.querySelector<HTMLInputElement>('#current-password')!.value).toBe(''); expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull();
  });
  it('일반 pageshow는 입력을 유지하고 pagehide 및 BFCache 복귀는 세 비밀번호와 오류를 지운다', async () => {
    await render(); await fill('Mismatch!234'); await save();
    await transition('pageshow', false);
    expect(container.querySelector<HTMLInputElement>('#current-password')!.value).toBe('OldPassword!234');
    expect(container.querySelector('#confirm-password-error')).not.toBeNull();
    expect(getMe).not.toHaveBeenCalled();
    await transition('pagehide');
    for (const field of container.querySelectorAll<HTMLInputElement>('input[type="password"]')) expect(field.value).toBe('');
    expect(container.querySelector('#confirm-password-error')).toBeNull();
    await transition('pageshow');
    for (const field of container.querySelectorAll<HTMLInputElement>('input[type="password"]')) expect(field.value).toBe('');
    expect(post).not.toHaveBeenCalled();
  });
  it('persisted pageshow 자체도 초안을 비우고 최신 세션이 익명이면 재로그인을 요구한다', async () => {
    await render(); await fill();
    await transition('pageshow');
    for (const field of container.querySelectorAll<HTMLInputElement>('input[type="password"]')) expect(field.value).toBe('');
    await fill(); post.mockRejectedValueOnce(new ApiError(401, 'unauthenticated')); await save();
    getMe.mockResolvedValueOnce(null);
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull();
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    expect(container.textContent).toContain('로그인이 만료됐어요');
  });
  it.each(['resolve', 'reject'] as const)('복원은 비밀번호 요청 %s를 기다리고 최신 세션을 확인할 때까지 제출을 막는다', async (outcome) => {
    let resolveOld!: () => void; let rejectOld!: (cause: unknown) => void; let resolveGet!: (value: User | null) => void;
    post.mockReturnValueOnce(new Promise<void>((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }));
    getMe.mockReturnValueOnce(new Promise<User | null>((resolve) => { resolveGet = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render(); await fill(); await save();
      await transition('pagehide'); await transition('pageshow');
      expect(container.querySelector('button[type="submit"]')!.textContent).toBe('정보 확인 중...');
      expect(container.querySelector('fieldset')!.disabled).toBe(true);
      expect(getMe).not.toHaveBeenCalled();
      await save(); expect(post).toHaveBeenCalledOnce();
      await act(async () => { if (outcome === 'resolve') resolveOld(); else rejectOld(new ApiError(401, 'unauthenticated')); });
      expect(getMe).toHaveBeenCalledOnce();
      expect(container.querySelector('fieldset')!.disabled).toBe(true);
      expect(container.querySelector('a[href="/auth/login"]')).toBeNull();
      expect(container.querySelector('[role="status"]')).toBeNull();
      expect(container.querySelector('[role="alert"]')).toBeNull();
      expect(updated).not.toHaveBeenCalled();
      const cancel = new MouseEvent('click', { bubbles: true, cancelable: true });
      await act(async () => container.querySelector('a[href="/my"]')!.dispatchEvent(cancel));
      expect(cancel.defaultPrevented).toBe(true);
      await act(async () => resolveGet(outcome === 'resolve' ? null : user));
      expect(container.querySelector('fieldset')!.disabled).toBe(outcome === 'resolve');
      if (outcome === 'resolve') expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull();
      else {
        expect(updated).toHaveBeenCalledOnce();
        await fill(); post.mockResolvedValueOnce({}); await save();
        expect(post).toHaveBeenCalledTimes(2);
      }
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });

  it('복원 조회 실패는 입력을 비우고 저장을 잠근 채 새 페이지 확인을 안내한다', async () => {
    getMe.mockRejectedValueOnce(new TypeError('network'));
    await render(); await fill(); await transition('pagehide'); await transition('pageshow');
    expect(container.textContent).toContain('페이지를 새로 열어 변경 여부를 확인');
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    for (const field of container.querySelectorAll<HTMLInputElement>('input[type="password"]')) expect(field.value).toBe('');
    await save(); expect(post).not.toHaveBeenCalled();
  });

  it('복원 조회는 소셜 계정의 최신 비밀번호 유무를 반영하고 재로그인 안내를 가리지 않는다', async () => {
    await render(); getMe.mockResolvedValueOnce({ ...user, has_password: false });
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent).toContain('소셜 로그인 계정');
    getMe.mockResolvedValueOnce(null);
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector('a[href="/auth/login"]')).not.toBeNull();
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    getMe.mockResolvedValueOnce(user);
    await transition('pagehide'); await transition('pageshow');
    expect(container.querySelector('a[href="/auth/login"]')).toBeNull();
    expect(container.querySelector('fieldset')!.disabled).toBe(false);
  });

  it.each(['resolve', 'reject'] as const)('이전 복원 조회의 %s는 현재 복원의 상태를 바꾸지 않는다', async (outcome) => {
    let resolveOld!: (value: User | null) => void; let rejectOld!: (cause: unknown) => void; let resolveNew!: (value: User) => void;
    getMe.mockReturnValueOnce(new Promise<User | null>((resolve, reject) => { resolveOld = resolve; rejectOld = reject; }))
      .mockReturnValueOnce(new Promise<User>((resolve) => { resolveNew = resolve; }));
    await render(); await transition('pageshow');
    await transition('pagehide'); await transition('pageshow');
    await act(async () => { if (outcome === 'resolve') resolveOld(null); else rejectOld(new TypeError('network')); });
    expect(container.querySelector('fieldset')!.disabled).toBe(true);
    expect(container.querySelector('a[href="/auth/login"]')).toBeNull();
    expect(container.textContent).not.toContain('페이지를 새로 열어');
    await act(async () => resolveNew(user));
    expect(container.querySelector('fieldset')!.disabled).toBe(false);
  });

  it('언마운트 뒤 복원 조회 완료를 무시한다', async () => {
    let finish!: (value: User) => void; getMe.mockReturnValueOnce(new Promise<User>((resolve) => { finish = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    try {
      await render(); await transition('pageshow'); await act(async () => root.render(<div />));
      await act(async () => finish(user)); expect(updated).not.toHaveBeenCalled();
    } finally { window.removeEventListener('dweb:account-updated', updated); }
  });
  it('StrictMode에서 제출이 가능하고 언마운트하면 리스너와 늦은 응답을 정리한다', async () => {
    let finish!: () => void; post.mockReturnValueOnce(new Promise<void>((resolve) => { finish = resolve; }));
    const updated = vi.fn(); window.addEventListener('dweb:account-updated', updated);
    const remove = vi.spyOn(window, 'removeEventListener');
    try {
      await act(async () => root.render(<StrictMode><PasswordEditor initialUser={user} /></StrictMode>));
      await fill(); await save(); expect(post).toHaveBeenCalledOnce();
      await act(async () => root.render(<div />));
      expect(remove).toHaveBeenCalledWith('pagehide', expect.any(Function));
      expect(remove).toHaveBeenCalledWith('pageshow', expect.any(Function));
      await act(async () => finish()); expect(updated).not.toHaveBeenCalled();
    } finally { remove.mockRestore(); window.removeEventListener('dweb:account-updated', updated); }
  });
  it('동시 제출은 하나의 요청만 보낸다', async () => {
    let finish!: () => void; post.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    await render(); await fill();
    await act(async () => { const save = container.querySelector<HTMLButtonElement>('button[type="submit"]')!; save.click(); save.click(); });
    expect(post).toHaveBeenCalledOnce(); await act(async () => finish());
  });
});
it('새 비밀번호는 가입 정책을 재사용하고 확인 오류 위치를 지정한다', () => {
  expect(passwordChangeSchema.safeParse({ current_password: 'old', new_password: 'weak', confirm_password: 'weak' }).success).toBe(false);
  const result = passwordChangeSchema.safeParse({ current_password: 'old', new_password: 'NewPassword!234', confirm_password: 'different' });
  expect(result.success).toBe(false); if (!result.success) expect(result.error.issues.some((issue) => issue.path[0] === 'confirm_password')).toBe(true);
});
