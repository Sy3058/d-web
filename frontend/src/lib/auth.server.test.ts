import { afterEach, describe, expect, it, vi } from 'vitest';
import { getMeOnServer } from './auth.server';

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe('SSR account lookup', () => {
  it('access 만료는 refresh 헛요청 없이 브라우저 복구로 넘긴다', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 401 }));
    vi.stubGlobal('fetch', fetcher);
    vi.stubEnv('API_INTERNAL_URL', 'http://api.internal');
    expect(await getMeOnServer('login_hint=reader')).toBeNull();
    expect(fetcher).toHaveBeenCalledExactlyOnceWith('http://api.internal/auth/me', {
      headers: { Cookie: 'login_hint=reader' }, cache: 'no-store',
    });
  });

  it('유효한 쿠키의 본인 응답을 반환한다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ nickname: 'reader' }))));
    expect(await getMeOnServer('access_token=example')).toEqual({ nickname: 'reader' });
  });

  it('일시 장애는 인증 만료로 바꾸지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    await expect(getMeOnServer()).rejects.toMatchObject({ status: 503 });
  });
});
