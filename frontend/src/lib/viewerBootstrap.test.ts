import { afterEach, describe, expect, it, vi } from 'vitest';
import { getViewerBootstrap } from './viewerBootstrap';

const bootstrap = {
  work_id: 'work-a',
  work_title: '작품',
  episode_id: 'episode-a',
  public_id: 12345678,
  episode_title: '구매 회차',
  episode_subtitle: null,
  previous_episode: null,
  next_episode: null,
};

afterEach(() => vi.unstubAllGlobals());

function response(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), { status });
}

it('힌트 없는 진입은 세션 요청 없이 credentials와 no-store로 bootstrap만 조회한다', async () => {
  const fetch = vi.fn().mockResolvedValue(response(200, bootstrap));
  vi.stubGlobal('fetch', fetch);
  await expect(getViewerBootstrap('work-a', 12345678, '')).resolves.toEqual(bootstrap);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('/works/work-a/episodes/12345678/viewer-bootstrap'),
    expect.objectContaining({ credentials: 'include', cache: 'no-store' }),
  );
});

it('힌트가 있으면 access 만료를 refresh하고 인증 재조회가 끝난 뒤 bootstrap을 호출한다', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(200))
    .mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, bootstrap));
  vi.stubGlobal('fetch', fetch);
  await expect(getViewerBootstrap('work-a', 12345678, 'login_hint=1')).resolves.toEqual(bootstrap);
  expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
    '/auth/me', '/auth/refresh', '/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap',
  ]);
  expect(fetch.mock.calls.every(([, init]) => init.credentials === 'include')).toBe(true);
});

it('refresh도 만료된 stale hint는 bootstrap의 익명 404로 수렴한다', async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(404));
  vi.stubGlobal('fetch', fetch);
  await expect(getViewerBootstrap('work-a', 12345678, 'login_hint=stale')).resolves.toBeNull();
  expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
    '/auth/me', '/auth/refresh', '/works/work-a/episodes/12345678/viewer-bootstrap',
  ]);
});

describe('오류 의미 보존', () => {
  it.each(['503', 'network'])('refresh %s 장애는 bootstrap 없이 원래 오류를 전파하고 다음 복구를 허용한다', async (failure) => {
    const error = new TypeError('offline');
    const fetch = vi.fn().mockResolvedValueOnce(response(401));
    if (failure === '503') fetch.mockResolvedValueOnce(response(503));
    else fetch.mockRejectedValueOnce(error);
    fetch.mockResolvedValue(response(404));
    vi.stubGlobal('fetch', fetch);

    const attempt = getViewerBootstrap('work-a', 12345678, 'login_hint=1');
    if (failure === '503') await expect(attempt).rejects.toMatchObject({ status: 503 });
    else await expect(attempt).rejects.toBe(error);
    expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
      '/auth/me', '/auth/refresh',
    ]);

    fetch.mockResolvedValueOnce(response(401))
      .mockResolvedValueOnce(response(200))
      .mockResolvedValueOnce(response(200, { id: 'reader' }))
      .mockResolvedValueOnce(response(200, bootstrap));
    await expect(getViewerBootstrap('work-a', 12345678, 'login_hint=1')).resolves.toEqual(bootstrap);
    expect(fetch.mock.calls.map(([url]) => new URL(url).pathname).slice(2)).toEqual([
      '/auth/me', '/auth/refresh', '/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap',
    ]);
  });

  it.each([404, 422])('%s는 메타 없는 찾을 수 없음으로 처리한다', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(status)));
    await expect(getViewerBootstrap('bad-id', 12345678, '')).resolves.toBeNull();
  });

  it.each(['auth', 'bootstrap', 'network'])('%s 장애는 찾을 수 없음으로 숨기지 않는다', async (stage) => {
    const fetch = vi.fn();
    fetch.mockRejectedValue(new Error('offline'));
    if (stage !== 'network') fetch.mockResolvedValue(response(503));
    vi.stubGlobal('fetch', fetch);
    await expect(getViewerBootstrap('work-a', 12345678, stage === 'auth' ? 'login_hint=1' : ''))
      .rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
