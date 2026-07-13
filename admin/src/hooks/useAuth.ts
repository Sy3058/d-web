import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { AdminLoginResponse, TotpSetupResponse, UserRead } from '../types';

export const ME_QUERY_KEY = ['auth', 'me'] as const;
const TOTP_SETUP_QUERY_KEY = ['admin', '2fa', 'setup'] as const;

export const meQueryOptions = queryOptions({
  queryKey: ME_QUERY_KEY,
  queryFn: () => api.get<UserRead>('/auth/me'),
  // 비로그인 상태의 401은 정상적인 상태(재시도로 해결 안 됨) - 기본 retry(3회, 지수
  // 백오프)를 끄지 않으면 _auth.tsx 가드의 리다이렉트 판단이 수 초 지연된다.
  retry: false,
  // staleTime 0 = 라우트 가드(fetchQuery)가 진입할 때마다 세션을 실제로 재검증한다.
  // 값을 주면 그 시간 동안 만료·강등된 세션이 캐시만으로 가드를 통과한다.
  staleTime: 0,
});

export function useMe() {
  return useQuery(meQueryOptions);
}

export function useAdminLogin() {
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api.post<AdminLoginResponse>('/admin/login', body),
  });
}

export function useAdminLoginTotp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { code: string; remember_device: boolean }) =>
      api.post<UserRead>('/admin/login/totp', body),
    onSuccess: (user) => {
      // 서버가 이미 최신 UserRead를 응답으로 줬으므로 invalidateQueries(재요청)
      // 대신 setQueryData로 캐시에 바로 반영 - 불필요한 네트워크 왕복을 없앤다.
      queryClient.setQueryData(meQueryOptions.queryKey, user);
    },
  });
}

export function useAdminTotpSetup() {
  // POST지만 시맨틱은 "마운트 시 표시할 데이터(QR URI) 조회"라 query로 다룬다.
  // mutation을 useEffect에서 발화하면 StrictMode의 mount->cleanup->mount에서 observer가
  // mutation과 분리돼 성공 알림이 유실된다(TanStack/query#8512) - query는 재구독·중복
  // 요청 dedupe를 정상 처리한다. staleTime Infinity로 포커스 복귀 시 시크릿 재발급을 막는다.
  return useQuery({
    queryKey: TOTP_SETUP_QUERY_KEY,
    queryFn: () => api.post<TotpSetupResponse>('/admin/2fa/setup', undefined),
    retry: false,
    staleTime: Infinity,
  });
}

export function useAdminTotpConfirm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { code: string; remember_device: boolean }) =>
      api.post<UserRead>('/admin/2fa/confirm', body),
    onSuccess: (user) => {
      queryClient.setQueryData(meQueryOptions.queryKey, user);
      // 등록이 끝나면 QR(=TOTP 시크릿 원문)을 메모리에 남길 이유가 없다 - 즉시 폐기.
      queryClient.removeQueries({ queryKey: TOTP_SETUP_QUERY_KEY });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ message: string }>('/auth/logout', undefined),
    onSuccess: () => {
      // clear()로 캐시를 통째로 비운다. setQueryData(key, undefined)는 TanStack이
      // undefined를 "업데이트 안 함" 신호로 보고 bail-out하는 no-op이라 유저 정보가
      // 그대로 남고, 뒤로가기 시 라우트 가드가 그 캐시로 통과해버린다(query-core
      // queryClient.js: `if (data === void 0) return void 0`). 남은 TOTP 시크릿도 함께 폐기.
      queryClient.clear();
    },
  });
}
