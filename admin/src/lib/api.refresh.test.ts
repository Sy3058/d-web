import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApi } from '@d-web/shared';

// shared의 createApi 401 자동 refresh 동작 테스트 (#67).
// shared 패키지엔 vitest가 없어 admin에 둔다 - extractDetail 계열(api.test.ts)과 같은 선례.

const BASE = 'http://api.test';

function res(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status });
}

const ok = (body: unknown = { message: 'ok' }) => res(200, body);
const unauthorized = () => res(401, { detail: '인증이 필요합니다' });

/** URL별 응답 큐로 fetch를 mock한다. 큐가 비면 마지막 항목을 반복하지 않고 실패시켜
 * "예상보다 많은 호출"이 조용히 통과하는 걸 막는다. */
function stubFetch(queues: Record<string, Array<() => Response>>) {
  const calls: Array<{ path: string; init?: RequestInit }> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(BASE, '');
    calls.push({ path, init });
    const next = queues[path]?.shift();
    if (!next) throw new Error(`예상 밖의 fetch 호출: ${path}`);
    return next();
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, refreshCount: () => calls.filter((c) => c.path === '/auth/refresh').length };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('createApi 401 자동 refresh', () => {
  it('401을 받으면 refresh 후 원요청을 같은 body로 1회 재시도한다', async () => {
    const { calls, refreshCount } = stubFetch({
      '/admin/works': [unauthorized, () => ok({ id: 'w1' })],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);

    const result = await api.post<{ id: string }>('/admin/works', { title: '작품' });

    expect(result).toEqual({ id: 'w1' });
    expect(refreshCount()).toBe(1);
    // 재시도(3번째 호출)가 원요청과 같은 메서드·body를 보내는지 - json 재직렬화 확인
    const [first, , retry] = calls;
    expect(retry.path).toBe('/admin/works');
    expect(retry.init?.method).toBe('POST');
    expect(retry.init?.body).toBe(first.init?.body);
  });

  it('동시에 여러 요청이 401을 받아도 refresh는 한 번만 나간다', async () => {
    const { refreshCount } = stubFetch({
      '/admin/works': [unauthorized, () => ok([{ id: 'w1' }])],
      '/auth/me': [unauthorized, () => ok({ id: 'u1' })],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);

    const [works, me] = await Promise.all([
      api.get<Array<{ id: string }>>('/admin/works'),
      api.get<{ id: string }>('/auth/me'),
    ]);

    expect(works).toEqual([{ id: 'w1' }]);
    expect(me).toEqual({ id: 'u1' });
    expect(refreshCount()).toBe(1);
  });

  it('refresh가 실패하면 재시도 없이 원요청의 401을 전파한다', async () => {
    const { calls } = stubFetch({
      '/admin/works': [unauthorized],
      '/auth/refresh': [unauthorized],
    });
    const api = createApi(BASE);

    const err = await api.get('/admin/works').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
    // 원요청 1 + refresh 1, 재시도 없음
    expect(calls.map((c) => c.path)).toEqual(['/admin/works', '/auth/refresh']);
  });

  it('로그인 계열 경로의 401은 refresh를 트리거하지 않는다', async () => {
    const { calls } = stubFetch({
      '/admin/login': [unauthorized],
    });
    const api = createApi(BASE);

    const err = await api.post('/admin/login', { email: 'a@b.c', password: 'x' }).catch((e: unknown) => e);

    expect((err as ApiError).status).toBe(401);
    expect(calls.map((c) => c.path)).toEqual(['/admin/login']);
  });

  it('두 탭(두 인스턴스)이 동시에 401을 받아도 refresh는 락으로 직렬화된다', async () => {
    // 가짜 LockManager: 같은 이름의 콜백을 도착 순서대로 순차 실행 (Web Locks exclusive 모드 흉내).
    // in-flight 공유(refreshPromise)는 탭 안에서만 유효하므로 탭 간 겹침은 락만이 막는다.
    let chain: Promise<unknown> = Promise.resolve();
    const lockRequest = vi.fn((_name: string, cb: () => Promise<unknown>) => {
      const run = chain.then(cb);
      chain = run.catch(() => undefined);
      return run;
    });
    vi.stubGlobal('navigator', { locks: { request: lockRequest } });

    let worksCalls = 0;
    let refreshInFlight = 0;
    let maxConcurrentRefresh = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input).replace(BASE, '');
      if (path === '/auth/refresh') {
        refreshInFlight += 1;
        maxConcurrentRefresh = Math.max(maxConcurrentRefresh, refreshInFlight);
        // 한 tick 잡아서 겹칠 "기회"를 만든다 - 락이 없으면 여기서 2가 관측된다
        await new Promise((resolve) => setTimeout(resolve, 0));
        refreshInFlight -= 1;
        return ok();
      }
      worksCalls += 1;
      // 각 탭의 첫 호출(1·2번째)은 401, 재시도(3·4번째)는 200
      return worksCalls <= 2 ? unauthorized() : ok({ id: 'w1' });
    });
    vi.stubGlobal('fetch', fetchMock);

    const tabA = createApi(BASE);
    const tabB = createApi(BASE);
    await Promise.all([tabA.get('/admin/works'), tabB.get('/admin/works')]);

    expect(lockRequest).toHaveBeenCalledWith('dweb-auth-refresh', expect.any(Function));
    expect(maxConcurrentRefresh).toBe(1);
  });

  it('refresh 성공 후 재시도가 또 401이면 그대로 전파한다 (2회 재시도 없음)', async () => {
    const { calls } = stubFetch({
      '/admin/works': [unauthorized, unauthorized],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);

    const err = await api.get('/admin/works').catch((e: unknown) => e);

    expect((err as ApiError).status).toBe(401);
    expect(calls.map((c) => c.path)).toEqual(['/admin/works', '/auth/refresh', '/admin/works']);
  });
});
