import { afterEach, expect, it, vi } from 'vitest';
import { getMe } from './auth';

afterEach(() => vi.unstubAllGlobals());

it('브라우저의 만료 access는 쿠키를 포함한 refresh 후 본인 조회로 복구한다', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}'))
    .mockResolvedValueOnce(new Response(JSON.stringify({ nickname: '복구된 독자' })));
  vi.stubGlobal('fetch', fetcher);
  expect(await getMe()).toEqual({ nickname: '복구된 독자' });
  expect(fetcher.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
    '/auth/me', '/auth/refresh', '/auth/me',
  ]);
  expect(fetcher.mock.calls[1][1]).toMatchObject({ credentials: 'include', method: 'POST' });
});

it('최종 refresh 401만 비로그인으로 판단한다', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}', { status: 401 })));
  expect(await getMe()).toBeNull();
});

it('refresh 장애는 로그인 만료로 바꾸지 않는다', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response('{}', { status: 503 })));
  await expect(getMe()).rejects.toMatchObject({ status: 503 });
});
