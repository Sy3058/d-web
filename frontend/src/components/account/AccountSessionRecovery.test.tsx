// @vitest-environment jsdom
import { act, StrictMode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../../lib/auth';
import AccountSessionRecovery from './AccountSessionRecovery';

const user: User = {
  id: 'reader-1',
  email: 'reader@example.com',
  nickname: '독자',
  profile_image: null,
  role: 'reader',
  has_password: true,
  is_email_verified: true,
  created_at: '2026-11-16T00:00:00Z',
};

const fetchMock = vi.fn<typeof fetch>();
let root: Root;
let container: HTMLDivElement;

function unauthorized() {
  return new Response('{}', { status: 401 });
}

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('fetch', fetchMock);
  fetchMock.mockReset();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe('계정 세션 복구', () => {
  it.each([
    ['overview', 'reader@example.com', 'a[href="/my/profile"]'],
    ['profile', '변경 내용 저장', '#profile-nickname'],
    ['password', '현재 비밀번호', '#current-password'],
    ['settings', '알림 설정 기능은 준비 중', 'h2'],
  ] as const)('access 401 뒤 갱신에 성공하면 %s 내용을 표시한다', async (page, copy, selector) => {
    let finishRefresh!: (response: Response) => void;
    fetchMock.mockResolvedValueOnce(unauthorized())
      .mockReturnValueOnce(new Promise((resolve) => { finishRefresh = resolve; }))
      .mockResolvedValueOnce(Response.json(user));

    await act(async () => root.render(<AccountSessionRecovery page={page} />));
    expect(container.querySelector('[role="status"]')?.textContent).toBe('로그인 확인 중...');
    expect(container.textContent).not.toContain(copy);
    expect(container.querySelector(selector)).toBeNull();

    await act(async () => finishRefresh(new Response(null, { status: 204 })));
    expect(container.textContent).toContain(copy);
    expect(container.querySelector(selector)).not.toBeNull();
    expect(fetchMock.mock.calls.map(([url, init]) => [
      new URL(String(url)).pathname, init?.method ?? 'GET', init?.credentials,
    ])).toEqual([
      ['/auth/me', 'GET', 'include'],
      ['/auth/refresh', 'POST', 'include'],
      ['/auth/me', 'GET', 'include'],
    ]);
  });

  it('갱신이 최종 401이면 로그인 진입을 표시한다', async () => {
    fetchMock.mockResolvedValueOnce(unauthorized()).mockResolvedValueOnce(unauthorized());

    await act(async () => root.render(<AccountSessionRecovery page="password" />));
    expect(container.querySelector('a[href="/auth/login"]')?.textContent).toBe('로그인');
    expect(container.querySelector('form')).toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each(['503', 'network'] as const)('갱신 %s 장애에서 재시도하면 세션 확인을 다시 수행한다', async (failure) => {
    fetchMock.mockResolvedValueOnce(unauthorized());
    if (failure === '503') fetchMock.mockResolvedValueOnce(new Response('{}', { status: 503 }));
    else fetchMock.mockRejectedValueOnce(new TypeError('network'));
    fetchMock.mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json(user));

    await act(async () => root.render(<AccountSessionRecovery page="overview" />));
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('일시적인 오류');
    expect(container.querySelector('a[href="/auth/login"]')).toBeNull();
    expect(container.textContent).not.toContain(user.email);

    await act(async () => container.querySelector('button')!.click());
    expect(container.textContent).toContain(user.email);
    expect(container.querySelector('[role="alert"]')).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it.each(['success', 'failure'] as const)('정리된 요청의 늦은 %s 응답이 현재 세션 상태를 바꾸지 않는다', async (outcome) => {
    let finish!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }))
      .mockResolvedValueOnce(Response.json(user));

    await act(async () => root.render(<StrictMode><AccountSessionRecovery page="overview" /></StrictMode>));
    expect(container.textContent).toContain(user.email);

    await act(async () => finish(outcome === 'success'
      ? Response.json({ ...user, email: 'previous@example.com' })
      : new Response('{}', { status: 503 })));
    expect(container.textContent).toContain(user.email);
    expect(container.textContent).not.toContain('previous@example.com');
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('계정 화면을 떠난 뒤 완료된 요청은 화면을 바꾸지 않는다', async () => {
    let finish!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));

    await act(async () => root.render(<AccountSessionRecovery page="overview" />));
    await act(async () => root.render(<p>다른 페이지</p>));
    await act(async () => finish(Response.json(user)));
    expect(container.textContent).toBe('다른 페이지');
  });
});
