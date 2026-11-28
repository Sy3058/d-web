// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import ForgotPasswordForm from './ForgotPasswordForm';
import ResetPasswordForm from './ResetPasswordForm';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api', async (original) => {
  const module = await original<typeof import('@/lib/api')>();
  return { ...module, api: { ...module.api, post } };
});

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  post.mockReset();
  window.history.replaceState({}, '', '/auth/reset-password');
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

async function render(component: React.ReactNode) {
  await act(async () => root.render(component));
}

async function input(id: string, value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>(`#${id}`)!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

async function submit() {
  await act(async () => {
    container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });
}

async function setTokenHash(token: string) {
  await act(async () => {
    window.location.hash = `token=${encodeURIComponent(token)}`;
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
}

describe('비밀번호 찾기', () => {
  it('계정 존재 여부와 무관한 성공 문구를 보여 주고 같은 폼에서 다시 보낸다', async () => {
    post.mockResolvedValue({ message: '서버 문구' });
    await render(<ForgotPasswordForm />);
    expect(container.querySelector('form')?.method).toBe('post');
    await input('email', 'Reader@Example.com');
    await submit();
    expect(post).toHaveBeenCalledWith('/auth/forgot-password', { email: 'reader@example.com' });
    expect(container.textContent).toContain('입력한 이메일로 비밀번호 재설정 링크를 전송했습니다.');
    expect(container.textContent).not.toContain('서버 문구');
    expect(container.textContent).toContain('재설정 링크 다시 받기');
    await submit();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('요청 제한과 그 밖의 실패를 구분하되 서버 detail은 노출하지 않는다', async () => {
    await render(<ForgotPasswordForm />);
    await input('email', 'reader@example.com');
    post.mockRejectedValueOnce(new ApiError(429, '{"detail":"secret"}'));
    await submit();
    expect(container.textContent).toContain('요청이 너무 많아요');
    expect(container.textContent).not.toContain('secret');
    post.mockRejectedValueOnce(new ApiError(500, '{"detail":"internal"}'));
    await submit();
    expect(container.textContent).toContain('재설정 링크를 보내지 못했어요');
    expect(container.textContent).not.toContain('internal');
  });

  it.each(['resolve', 'reject'])('요청 중 강제로 바뀐 이메일은 이전 %s 응답을 무시하고 새 요청을 완료한다', async (result) => {
    await render(<ForgotPasswordForm />);
    await input('email', 'a@example.com');
    let settleOld!: () => void;
    post.mockReturnValueOnce(new Promise((resolve, reject) => {
      settleOld = () => result === 'resolve'
        ? resolve({ message: 'old' })
        : reject(new ApiError(429, 'old'));
    }));
    await submit();
    const email = container.querySelector<HTMLInputElement>('#email')!;
    expect(email.disabled).toBe(true);
    email.disabled = false;
    await input('email', 'b@example.com');
    post.mockResolvedValueOnce({ message: 'new' });
    await submit();
    await act(async () => settleOld());
    expect(container.textContent).not.toContain('요청이 너무 많아요');
    await act(async () => {});
    expect(post).toHaveBeenLastCalledWith('/auth/forgot-password', { email: 'b@example.com' });
    expect(container.textContent).toContain('입력한 이메일로 비밀번호 재설정 링크를 전송했습니다.');
  });

  it('성공 뒤 이메일을 바꾸면 이전 전송 상태를 지운다', async () => {
    post.mockResolvedValueOnce({ message: 'sent' });
    await render(<ForgotPasswordForm />);
    await input('email', 'a@example.com');
    await submit();
    expect(container.textContent).toContain('입력한 이메일로 비밀번호 재설정 링크를 전송했습니다.');
    await input('email', 'b@example.com');
    expect(container.textContent).not.toContain('입력한 이메일로 비밀번호 재설정 링크를 전송했습니다.');
    expect(container.textContent).toContain('재설정 링크 받기');
  });
});

describe('비밀번호 재설정', () => {
  it('fragment 토큰을 즉시 지우고 사용자가 제출하기 전에는 요청하지 않는다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    expect(window.location.hash).toBe('');
    expect(window.location.pathname).toBe('/auth/reset-password');
    expect(post).not.toHaveBeenCalled();
    expect(container.querySelector('form')?.method).toBe('post');
  });

  it('마운트 뒤 새 hash 토큰을 채택하고 이전 입력을 지운 뒤 새 토큰만 제출한다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=old-token');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    await setTokenHash('new-token');
    expect(window.location.hash).toBe('');
    expect(container.querySelector<HTMLInputElement>('#password')?.value).toBe('');
    expect(container.querySelector<HTMLInputElement>('#password-confirm')?.value).toBe('');
    await input('password', 'NewPassword!234');
    await input('password-confirm', 'NewPassword!234');
    post.mockResolvedValueOnce({ message: '완료' });
    await submit();
    expect(post).toHaveBeenCalledWith('/auth/reset-password', {
      token: 'new-token', new_password: 'NewPassword!234',
    });
  });

  it.each(['resolve', 'reject'])('새 hash는 진행 중인 이전 요청의 늦은 %s를 무시하고 독립적으로 완료한다', async (result) => {
    window.history.replaceState({}, '', '/auth/reset-password#token=old-token');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    let settleOld!: () => void;
    post.mockReturnValueOnce(new Promise((resolve, reject) => {
      settleOld = () => result === 'resolve'
        ? resolve({ message: 'old' })
        : reject(new ApiError(400, 'old'));
    }));
    await submit();
    await setTokenHash('new-token');
    await input('password', 'NewPassword!234');
    await input('password-confirm', 'NewPassword!234');
    let resolveNew!: () => void;
    post.mockReturnValueOnce(new Promise((resolve) => {
      resolveNew = () => resolve({ message: 'new' });
    }));
    await submit();
    await act(async () => settleOld());
    expect(container.querySelector('form')).not.toBeNull();
    expect(container.textContent).not.toContain('유효하지 않거나 만료되었어요');
    await act(async () => resolveNew());
    expect(post).toHaveBeenLastCalledWith('/auth/reset-password', {
      token: 'new-token', new_password: 'NewPassword!234',
    });
    expect(container.textContent).toContain('비밀번호가 변경됐어요');
  });

  it('missing, 완료, BFCache 폐기 상태에서 새 hash가 폼을 다시 연다', async () => {
    await render(<ResetPasswordForm />);
    expect(container.querySelector('form')).toBeNull();
    await setTokenHash('first-token');
    expect(container.querySelector('form')).not.toBeNull();
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({ message: 'done' });
    await submit();
    expect(container.textContent).toContain('비밀번호가 변경됐어요');
    await setTokenHash('second-token');
    expect(container.querySelector('form')).not.toBeNull();
    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true }));
      window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
    });
    expect(container.querySelector('form')).toBeNull();
    await setTokenHash('third-token');
    expect(container.querySelector('form')).not.toBeNull();
  });

  it('비밀번호 확인과 정책을 검사하고 확인값 없이 명시 제출한다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Mismatch!234');
    await submit();
    expect(container.textContent).toContain('일치하지 않습니다');
    expect(post).not.toHaveBeenCalled();
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({ message: '완료' });
    await submit();
    expect(post).toHaveBeenCalledWith('/auth/reset-password', {
      token: 'token-value', new_password: 'Password!234',
    });
    expect(container.textContent).toContain('비밀번호가 변경됐어요');
    expect(container.textContent).toContain('로그인하기');
  });

  it.each([
    ['/auth/login'],
    ['https://admin.example.com/login'],
  ])('성공 응답의 login_url이 %s여도 독자 로그인 링크를 유지하고 자동 이동하지 않는다', async (loginUrl) => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({ message: '완료', login_url: loginUrl });
    await submit();
    const loginLink = container.querySelector<HTMLAnchorElement>('a');
    expect(loginLink?.getAttribute('href')).toBe('/auth/login');
    expect(loginLink?.hasAttribute('data-astro-reload')).toBe(true);
    expect(window.location.pathname).toBe('/auth/reset-password');
  });

  it('운영자 응답 뒤 BFCache 복원에서도 독자 로그인 링크를 유지하고 비밀번호는 되살리지 않는다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=owner-token');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({
      message: '완료',
      login_url: 'https://admin.example.com/login',
    });
    await submit();
    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true }));
      window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
    });
    expect(container.querySelector<HTMLAnchorElement>('a')?.getAttribute('href'))
      .toBe('/auth/login');
    expect(container.querySelector('#password')).toBeNull();
    expect(container.querySelector('form')).toBeNull();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('토큰 없음과 무효 응답은 새 링크 요청으로 안내한다', async () => {
    await render(<ResetPasswordForm />);
    expect(container.textContent).toContain('재설정 정보가 없어요');
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/auth/forgot-password');

    await act(async () => root.unmount());
    root = createRoot(container);
    window.history.replaceState({}, '', '/auth/reset-password#token=bad-token');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockRejectedValueOnce(new ApiError(400, '{"detail":"통합 오류"}'));
    await submit();
    expect(container.textContent).toContain('유효하지 않거나 만료되었어요');
    expect(container.textContent).not.toContain('통합 오류');
  });

  it('정책 위반, 요청 제한, 불확실한 결과를 각각 안내한다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');

    post.mockRejectedValueOnce(new ApiError(422, '{"detail":"유출된 비밀번호는 사용할 수 없습니다."}'));
    await submit();
    expect(container.textContent).toContain('유출된 비밀번호는 사용할 수 없습니다.');

    post.mockRejectedValueOnce(new ApiError(429, '{"detail":"server detail"}'));
    await submit();
    expect(container.textContent).toContain('요청이 너무 많아요');
    expect(container.textContent).not.toContain('server detail');

    post.mockRejectedValueOnce(new TypeError('network failed'));
    await submit();
    expect(container.textContent).toContain('변경 결과를 확인하지 못했어요');
    expect(container.textContent).toContain('새 비밀번호로 로그인하거나 새 링크를 요청');
  });

  it('BFCache에서 복원되어도 폐기한 비밀번호와 토큰을 되살리지 않는다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    await act(async () => {
      window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: true }));
      window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
    });
    expect(container.querySelector('#password')).toBeNull();
    expect(container.textContent).toContain('새 링크');
    expect(post).not.toHaveBeenCalled();
  });

  it('pagehide에서 입력과 토큰을 폐기하고 늦은 응답을 무시한다', async () => {
    window.history.replaceState({}, '', '/auth/reset-password#token=token-value');
    await render(<ResetPasswordForm />);
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    let resolve!: (value: unknown) => void;
    post.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    await submit();
    await act(async () => window.dispatchEvent(new PageTransitionEvent('pagehide')));
    expect(container.querySelector('form')).toBeNull();
    expect(container.textContent).toContain('새 링크');
    await act(async () => resolve({ message: '완료' }));
    expect(container.textContent).not.toContain('비밀번호가 변경됐어요');
  });

});
