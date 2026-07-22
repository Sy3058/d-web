import { QueryClient } from '@tanstack/react-query';
import { isRedirect } from '@tanstack/react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@d-web/shared';
import { ME_QUERY_KEY } from '../hooks/useAuth';
import type { UserRead } from '../types';

vi.mock('../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../lib/api');
const { Route } = await import('./_auth');
const mockGet = vi.mocked(api.get);

const user = (role: UserRead['role']): UserRead => ({
  id: 'u1',
  email: 'x@example.com',
  nickname: '아무개',
  profile_image: null,
  is_email_verified: true,
  role,
  created_at: '2026-07-14T00:00:00Z',
});

/** redirect()는 Response 객체에 옵션을 .options로 실어 던진다(router-core redirect.js). */
function redirectTarget(err: unknown): string | undefined {
  return (err as { options?: { to?: string } }).options?.to;
}

/** 라우터를 띄우지 않고 가드만 직접 호출한다. 반환=통과, throw=리다이렉트. */
async function runGuard(queryClient: QueryClient) {
  const beforeLoad = Route.options.beforeLoad as (args: {
    context: { queryClient: QueryClient };
  }) => Promise<void>;
  return beforeLoad({ context: { queryClient } });
}

describe('_auth 라우트 가드', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient();
  });

  it('owner 세션이면 통과한다', async () => {
    mockGet.mockResolvedValueOnce(user('owner'));
    await expect(runGuard(queryClient)).resolves.toBeUndefined();
  });

  it('미인증(401)이면 /login으로 리다이렉트한다', async () => {
    mockGet.mockRejectedValueOnce(new ApiError(401, '{"detail":"인증이 필요합니다"}'));

    const err = await runGuard(queryClient).catch((e: unknown) => e);
    expect(isRedirect(err)).toBe(true);
    expect(redirectTarget(err)).toBe('/login');
  });

  it('로그인은 됐지만 reader면 /login으로 리다이렉트한다 (인증≠인가)', async () => {
    mockGet.mockResolvedValueOnce(user('reader'));

    const err = await runGuard(queryClient).catch((e: unknown) => e);
    expect(isRedirect(err)).toBe(true);
    expect(redirectTarget(err)).toBe('/login');
  });

  it('세션이 만료되면 캐시된 유저로 통과시키지 않고 서버에 재검증한다', async () => {
    // 이전 화면에서 채워진 캐시(로그아웃 누락·만료 시나리오).
    queryClient.setQueryData(ME_QUERY_KEY, user('owner'));
    // 서버는 더 이상 이 세션을 인정하지 않는다.
    mockGet.mockRejectedValueOnce(new ApiError(401, '{"detail":"인증이 필요합니다"}'));

    const err = await runGuard(queryClient).catch((e: unknown) => e);

    // ensureQueryData였다면 캐시를 그대로 반환해 가드가 통과했을 자리다.
    expect(mockGet).toHaveBeenCalledOnce();
    expect(isRedirect(err)).toBe(true);
    expect(redirectTarget(err)).toBe('/login');
  });

  it('401로 리다이렉트할 때 캐시된 유저 정보를 비운다 (#91)', async () => {
    // 직전 로그인에서 남은 캐시. 비우지 않으면 /login에서도 useMe 구독 UI가 이전 로그인
    // 상태로 남고, 다른 계정으로 재로그인 시 직전 계정 데이터가 잠깐 비친다.
    queryClient.setQueryData(ME_QUERY_KEY, user('owner'));
    mockGet.mockRejectedValueOnce(new ApiError(401, '{"detail":"인증이 필요합니다"}'));

    await runGuard(queryClient).catch(() => undefined);

    expect(queryClient.getQueryData(ME_QUERY_KEY)).toBeUndefined();
  });

  it('reader로 리다이렉트할 때도 캐시를 비운다', async () => {
    // fetchQuery가 reader를 캐시에 채운 뒤 role 체크에서 튕긴다 - 그 캐시도 남기지 않는다.
    mockGet.mockResolvedValueOnce(user('reader'));

    await runGuard(queryClient).catch(() => undefined);

    expect(queryClient.getQueryData(ME_QUERY_KEY)).toBeUndefined();
  });
});
