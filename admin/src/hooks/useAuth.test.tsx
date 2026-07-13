import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@d-web/shared';
import { ME_QUERY_KEY, meQueryOptions, useAdminTotpConfirm, useLogout } from './useAuth';
import type { UserRead } from '../types';

vi.mock('../lib/api', async () => {
  const shared = await vi.importActual<typeof import('@d-web/shared')>('@d-web/shared');
  return {
    ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
    api: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
    ApiError: shared.ApiError,
  };
});

const { api } = await import('../lib/api');
const mockPost = vi.mocked(api.post);

const OWNER: UserRead = {
  id: 'u1',
  email: 'owner@example.com',
  nickname: '작가',
  profile_image: null,
  is_email_verified: true,
  role: 'owner',
  created_at: '2026-07-14T00:00:00Z',
};

const TOTP_SETUP_KEY = ['admin', '2fa', 'setup'];

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useLogout', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  it('로그아웃 성공 시 me 캐시를 실제로 비운다 (setQueryData(undefined) no-op 회귀)', async () => {
    // 로그인된 상태를 재현: 캐시에 owner가 들어있다.
    queryClient.setQueryData(ME_QUERY_KEY, OWNER);
    expect(queryClient.getQueryData(ME_QUERY_KEY)).toEqual(OWNER);
    mockPost.mockResolvedValueOnce({ message: '로그아웃되었습니다' });

    const { result } = renderHook(() => useLogout(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    // 캐시가 남아 있으면 _auth 가드가 그 값으로 통과해 로그아웃한 사용자에게
    // 대시보드가 렌더된다 - 반드시 비어 있어야 한다.
    expect(queryClient.getQueryData(ME_QUERY_KEY)).toBeUndefined();
  });

  it('로그아웃 시 TOTP 시크릿(QR) 캐시도 함께 폐기한다', async () => {
    queryClient.setQueryData(TOTP_SETUP_KEY, { otpauth_uri: 'otpauth://totp/x?secret=SECRET' });
    mockPost.mockResolvedValueOnce({ message: '로그아웃되었습니다' });

    const { result } = renderHook(() => useLogout(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(TOTP_SETUP_KEY)).toBeUndefined();
  });

  it('로그아웃 API가 실패하면 에러 상태를 노출한다 (사용자 알림 근거)', async () => {
    mockPost.mockRejectedValueOnce(new ApiError(500, '{"detail":"서버 오류"}'));

    const { result } = renderHook(() => useLogout(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useAdminTotpConfirm', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  it('등록 확정 시 me 캐시를 채우고 QR(시크릿) 캐시는 제거한다', async () => {
    queryClient.setQueryData(TOTP_SETUP_KEY, { otpauth_uri: 'otpauth://totp/x?secret=SECRET' });
    mockPost.mockResolvedValueOnce(OWNER);

    const { result } = renderHook(() => useAdminTotpConfirm(), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate({ code: '123456', remember_device: false });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(meQueryOptions.queryKey)).toEqual(OWNER);
    // 활성화된 뒤에도 시크릿 원문을 메모리에 들고 있을 이유가 없다.
    expect(queryClient.getQueryData(TOTP_SETUP_KEY)).toBeUndefined();
  });
});

describe('meQueryOptions', () => {
  it('staleTime이 0이라 가드(fetchQuery)가 매번 세션을 재검증한다', () => {
    // 값이 0보다 크면 그 시간 동안 만료·강등된 세션이 캐시만으로 가드를 통과한다.
    expect(meQueryOptions.staleTime).toBe(0);
  });

  it('retry가 꺼져 있어 비로그인 401에서 즉시 실패한다', () => {
    expect(meQueryOptions.retry).toBe(false);
  });
});
