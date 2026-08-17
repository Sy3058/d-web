// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('../../lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/api')>();
  return { ...original, api: { ...original.api, post } };
});

import { redirectToMyPage } from './LoginForm';
import VerifyEmail from './VerifyEmail';

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
