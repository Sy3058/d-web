import { ApiError, resolveApiBaseUrl } from './api';
import type { User } from './auth';

// /auth/refresh 전용 쿠키는 페이지 요청에 오지 않는다. SSR에서는 확인만 하고,
// access 만료 시의 갱신은 쿠키를 직접 보유한 브라우저에서 수행한다.
export async function getMeOnServer(cookieHeader?: string): Promise<User | null> {
  const baseUrl = resolveApiBaseUrl({
    isServer: true,
    publicUrl: import.meta.env.PUBLIC_API_URL,
    internalUrl: process.env.API_INTERNAL_URL,
  });
  const response = await fetch(`${baseUrl}/auth/me`, {
    headers: cookieHeader ? { Cookie: cookieHeader } : {},
    cache: 'no-store',
  });
  if (response.status === 401) return null;
  if (!response.ok) throw new ApiError(response.status, await response.text());
  return response.json() as Promise<User>;
}
