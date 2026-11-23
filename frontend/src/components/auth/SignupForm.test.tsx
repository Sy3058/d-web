// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import SignupForm from './SignupForm';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api', async (original) => {
  const module = await original<typeof import('@/lib/api')>();
  return { ...module, api: { ...module.api, get, post } };
});

let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  get.mockReset().mockResolvedValue({ email: null });
  post.mockReset();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
});

async function render() { await act(async () => root.render(<SignupForm />)); }
async function input(id: string, value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>(`#${id}`)!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
function button(text: string) {
  return Array.from(container.querySelectorAll<HTMLButtonElement>('button')).find((item) => item.textContent?.includes(text));
}
async function click(text: string) { await act(async () => button(text)?.click()); }
async function send(email = 'reader@example.com') {
  await input('email', email);
  post.mockResolvedValueOnce({ challenge_id: 'challenge-1', message: '보냄' });
  await click('인증 코드 받기');
}
async function verify(email = 'reader@example.com', code = '012345') {
  await send(email);
  await input('verification-code', code);
  post.mockResolvedValueOnce({ email, message: '인증 완료' });
  await click('인증 코드 확인');
}

describe('회원가입 이메일 코드 사전 인증', () => {
  it('인증 전에는 가입 필드를 열지 않고 발송 뒤 이메일과 요청 계약을 고정한다', async () => {
    await render();
    expect(get).toHaveBeenCalledWith('/auth/signup/verification');
    expect(container.querySelector('#nickname')).toBeNull();
    expect(button('회원가입')).toBeUndefined();
    await send('reader@example.com');
    expect(post).toHaveBeenCalledWith('/auth/signup/send-verification', { email: 'reader@example.com' });
    expect(container.querySelector<HTMLInputElement>('#email')?.disabled).toBe(true);
    const code = container.querySelector<HTMLInputElement>('#verification-code')!;
    expect(code.inputMode).toBe('numeric');
    expect(code.autocomplete).toBe('one-time-code');
    expect(code.maxLength).toBe(6);
    expect(container.querySelector('#nickname')).toBeNull();
    expect(button('60초 후 다시 보내기')?.disabled).toBe(true);
  });

  it('앞자리 0을 보존한 6자리 코드와 challenge를 보내고 일치한 이메일만 인증한다', async () => {
    await render();
    await send();
    await input('verification-code', '012345');
    post.mockResolvedValueOnce({ email: 'reader@example.com', message: '완료' });
    await click('인증 코드 확인');
    expect(post).toHaveBeenLastCalledWith('/auth/signup/verify-email', { challenge_id: 'challenge-1', code: '012345' });
    expect(container.textContent).toContain('이메일이 인증되었습니다.');
    expect(container.querySelector('#nickname')).not.toBeNull();
  });

  it('혼합 대소문자 이메일을 서버 값으로 정규화해 최종 가입까지 제출한다', async () => {
    await render();
    await send('Reader@Example.com');
    expect(post).toHaveBeenLastCalledWith('/auth/signup/send-verification', { email: 'reader@example.com' });
    await input('verification-code', '012345');
    post.mockResolvedValueOnce({ email: 'reader@example.com', message: '완료' });
    await click('인증 코드 확인');
    await input('nickname', '독자');
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({ message: '가입 완료' });
    await click('회원가입');
    expect(post).toHaveBeenLastCalledWith('/auth/signup', {
      email: 'reader@example.com', password: 'Password!234', nickname: '독자',
    });
    expect(container.textContent).toContain('회원가입이 완료됐어요.');
  });

  it('Enter 폼 제출은 현재 단계의 발송과 코드 확인만 실행한다', async () => {
    await render();
    await input('email', 'reader@example.com');
    post.mockResolvedValueOnce({ challenge_id: 'challenge-enter', message: '보냄' });
    await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    expect(post).toHaveBeenLastCalledWith('/auth/signup/send-verification', { email: 'reader@example.com' });
    expect(container.querySelector('#nickname')).toBeNull();

    await input('verification-code', '123456');
    post.mockResolvedValueOnce({ email: 'reader@example.com', message: '인증 완료' });
    await act(async () => container.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
    expect(post).toHaveBeenLastCalledWith('/auth/signup/verify-email', {
      challenge_id: 'challenge-enter', code: '123456',
    });
    expect(container.querySelector('#nickname')).not.toBeNull();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('잘못된 길이와 서버 오류는 가입 필드를 열지 않는다', async () => {
    await render();
    await send();
    await input('verification-code', '12345');
    await click('인증 코드 확인');
    expect(container.textContent).toContain('인증 코드 6자리를 입력해 주세요.');
    expect(post).toHaveBeenCalledTimes(1);
    await input('verification-code', '123456');
    post.mockRejectedValueOnce(new ApiError(400, '{"detail":"인증 코드가 올바르지 않습니다"}'));
    await click('인증 코드 확인');
    expect(container.textContent).toContain('인증 코드가 올바르지 않습니다');
    expect(container.querySelector('#nickname')).toBeNull();
  });

  it('검증 응답 이메일이 다르면 인증하지 않고 최종 가입 POST도 보내지 않는다', async () => {
    await render();
    await send('expected@example.com');
    await input('verification-code', '123456');
    post.mockResolvedValueOnce({ email: 'other@example.com', message: '완료' });
    await click('인증 코드 확인');
    expect(container.textContent).toContain('인증한 이메일이 일치하지 않아요');
    expect(container.querySelector('#nickname')).toBeNull();
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('이메일 변경은 challenge를 폐기하고 늦게 도착한 발송 응답을 무시한다', async () => {
    await render();
    await send('old@example.com');
    await click('이메일 변경');
    expect(container.querySelector<HTMLInputElement>('#email')?.disabled).toBe(false);
    expect(container.querySelector('#verification-code')).toBeNull();

    await input('email', 'stale@example.com');
    let resolve!: (value: unknown) => void;
    post.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    await click('인증 코드 받기');
    await input('email', 'new@example.com');
    await act(async () => resolve({ challenge_id: 'stale', message: '보냄' }));
    expect(container.querySelector('#verification-code')).toBeNull();
  });

  it('서버 proof는 새로고침 때 복구하지만 입력한 이메일과 다른 proof는 거부한다', async () => {
    get.mockResolvedValueOnce({ email: 'restored@example.com' });
    await render();
    expect(container.textContent).toContain('restored@example.com');
    expect(container.querySelector('#nickname')).not.toBeNull();

    await click('이메일 변경');
    expect(container.querySelector('#nickname')).toBeNull();
    expect(container.querySelector('#email')).not.toBeNull();
  });

  it('비밀번호 확인 불일치는 막고 최종 payload에서 확인값과 코드를 제외한다', async () => {
    await render();
    await verify();
    post.mockClear();
    await input('nickname', '독자');
    await input('password', 'Password!234');
    await input('password-confirm', 'Mismatch!234');
    await click('회원가입');
    expect(container.querySelector('#password-confirm-error')?.textContent).toContain('일치하지 않습니다');
    expect(post).not.toHaveBeenCalled();
    await input('password-confirm', 'Password!234');
    post.mockResolvedValueOnce({ message: '완료' });
    await click('회원가입');
    expect(post).toHaveBeenCalledWith('/auth/signup', {
      email: 'reader@example.com', password: 'Password!234', nickname: '독자',
    });
    expect(container.textContent).toContain('회원가입이 완료됐어요.');
  });

  it('최종 가입에서 인증 만료를 받으면 인증을 초기화한다', async () => {
    await render();
    await verify();
    post.mockClear();
    await input('nickname', '독자');
    await input('password', 'Password!234');
    await input('password-confirm', 'Password!234');
    post.mockRejectedValueOnce(new ApiError(400, '{"detail":"이메일 인증이 만료되었습니다"}'));
    await click('회원가입');
    expect(container.textContent).toContain('이메일 인증이 만료되었습니다');
    expect(container.querySelector('#email')).not.toBeNull();
    expect(container.querySelector('#nickname')).toBeNull();
    expect(container.textContent).not.toContain('회원가입이 완료됐어요.');
  });

  it('비밀번호 보기 버튼은 type과 접근성 상태를 유지한다', async () => {
    await render();
    await verify();
    const toggle = container.querySelector<HTMLButtonElement>('button[aria-label="비밀번호 보기"]')!;
    const field = container.querySelector<HTMLInputElement>('#password')!;
    expect(toggle.type).toBe('button');
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    await act(async () => toggle.click());
    expect(field.type).toBe('text');
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    expect(toggle.getAttribute('aria-label')).toBe('비밀번호 숨기기');
  });
});
