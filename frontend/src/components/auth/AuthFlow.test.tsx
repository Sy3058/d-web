// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('@/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api')>();
  return { ...original, api: { ...original.api, post } };
});

import { redirectToMyPage } from './LoginForm';
import LoginForm from './LoginForm';
import VerifyEmail from './VerifyEmail';
import { ApiError } from '@/lib/api';

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  post.mockReset();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  window.history.replaceState({}, '', '/');
});

describe('인증 화면 이동', () => {
  it('로그인 성공 뒤 내 페이지로 이동한다', () => {
    const assign = vi.fn();

    redirectToMyPage({ assign });

    expect(assign).toHaveBeenCalledWith('/my');
  });

  it('쿼리의 이메일 인증 토큰을 API에 전달한다', async () => {
    window.history.replaceState({}, '', '/auth/verify-email?token=token%20value');
    post.mockResolvedValue(undefined);

    await act(async () => root.render(<VerifyEmail />));
    const verifyButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('이메일 인증 완료하기'),
    );
    expect(verifyButton).toBeDefined();

    await act(async () => verifyButton?.click());

    expect(post).toHaveBeenCalledWith('/auth/verify-email', { token: 'token value' });
    expect(container.textContent).toContain('이메일 인증이 완료됐어요.');
  });
});

async function input(id: string, value: string) {
  await act(async () => {
    const field = container.querySelector<HTMLInputElement>(`#${id}`)!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

describe('로그인 이메일 인증 안내', () => {
  it('401은 이동하지 않고 일반 오류와 인증 메일 재발송 링크를 보여 준다', async () => {
    const redirect = vi.fn();
    post.mockRejectedValueOnce(new ApiError(401, 'unauthorized'));
    await act(async () => root.render(<LoginForm redirect={redirect} />));
    await input('email', 'reader@example.com');
    await input('password', 'Password!234');
    await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
    expect(redirect).not.toHaveBeenCalled();
    expect(container.textContent).toContain('이메일 또는 비밀번호가 올바르지 않습니다.');
    expect(container.querySelector('a[href="/auth/verify-email"]')?.textContent).toContain('이메일 인증 메일 다시 받기');
  });

  it('성공한 로그인은 이동하고 재발송 링크를 보이지 않는다', async () => {
    const redirect = vi.fn();
    post.mockResolvedValueOnce({});
    await act(async () => root.render(<LoginForm redirect={redirect} />));
    await input('email', 'reader@example.com');
    await input('password', 'Password!234');
    await act(async () => container.querySelector<HTMLButtonElement>('button[type="submit"]')!.click());
    expect(redirect).toHaveBeenCalledOnce();
    expect(container.querySelector('a[href="/auth/verify-email"]')).toBeNull();
  });
});
