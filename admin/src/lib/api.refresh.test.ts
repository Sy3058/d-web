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
function stubFetch(queues: Record<string, Array<() => Response | Promise<Response>>>) {
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

function stubCrossTabLock() {
  // 가짜 LockManager: 같은 이름의 콜백을 도착 순서대로 순차 실행한다.
  let chain: Promise<unknown> = Promise.resolve();
  const lockRequest = vi.fn((_name: string, cb: () => Promise<unknown>) => {
    const run = chain.then(cb);
    chain = run.catch(() => undefined);
    return run;
  });
  vi.stubGlobal('navigator', { locks: { request: lockRequest } });
  return lockRequest;
}

function pendingResponse() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((finish) => { resolve = finish; });
  return { promise, resolve };
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
    const lockRequest = stubCrossTabLock();

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

describe('createApi 로그아웃과 세션 갱신', () => {
  it.each(['/auth/me', '/episodes/a/content'])('%s 갱신이 끝날 때까지 로그아웃을 기다리고 이전 요청의 재시도를 막는다', async (path) => {
    const refresh = pendingResponse();
    const lockRequest = stubCrossTabLock();
    const { calls } = stubFetch({
      [path]: [unauthorized],
      '/auth/refresh': [() => refresh.promise],
      '/auth/logout': [ok],
    });
    const api = createApi(BASE);

    const request = expect(api.get(path)).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual([path, '/auth/refresh']));
    const firstLogout = api.post('/auth/logout', {});
    const secondLogout = api.post('/auth/logout', {});
    await Promise.resolve();
    expect(calls.map((call) => call.path)).toEqual([path, '/auth/refresh']);

    refresh.resolve(ok());
    await request;
    await expect(Promise.all([firstLogout, secondLogout])).resolves.toEqual([{ message: 'ok' }, { message: 'ok' }]);
    expect(calls.map((call) => call.path)).toEqual([path, '/auth/refresh', '/auth/logout']);
    expect(calls.at(-1)?.init).toMatchObject({ method: 'POST', credentials: 'include', body: '{}' });
    expect(lockRequest.mock.calls.map(([name]) => name)).toEqual(['dweb-auth-refresh', 'dweb-auth-refresh']);
  });

  it('로그아웃 시작 전과 진행 중에 시작한 요청의 늦은 401은 재로그인 세션을 갱신하지 않는다', async () => {
    const beforeLogout = pendingResponse();
    const duringLogout = pendingResponse();
    const logout = pendingResponse();
    const { calls } = stubFetch({
      '/auth/me': [
        () => beforeLogout.promise, () => duringLogout.promise,
        unauthorized, () => ok({ id: 'new-reader' }),
      ],
      '/auth/logout': [() => logout.promise],
      '/auth/login': [() => ok({ id: 'new-reader' })],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);

    const oldRequest = expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 });
    const pendingLogout = api.post('/auth/logout', {});
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/logout']));
    const duringRequest = expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 });
    logout.resolve(ok());
    await pendingLogout;
    await api.post('/auth/login', { email: 'reader@example.com', password: 'password' });

    beforeLogout.resolve(unauthorized());
    duringLogout.resolve(unauthorized());
    await Promise.all([oldRequest, duringRequest]);
    await expect(api.get('/auth/me')).resolves.toEqual({ id: 'new-reader' });
    expect(calls.map((call) => call.path)).toEqual([
      '/auth/me', '/auth/logout', '/auth/me', '/auth/login',
      '/auth/me', '/auth/refresh', '/auth/me',
    ]);
  });

  it('진행 중인 갱신이 실패해도 로그아웃 요청을 보낸다', async () => {
    const refresh = pendingResponse();
    const { calls } = stubFetch({
      '/auth/me': [unauthorized],
      '/auth/refresh': [() => refresh.promise],
      '/auth/logout': [ok],
    });
    const api = createApi(BASE);

    const request = expect(api.get('/auth/me')).rejects.toMatchObject({ status: 503 });
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh']));
    const logout = api.post('/auth/logout', {});
    refresh.resolve(res(503, {}));

    await request;
    await expect(logout).resolves.toEqual({ message: 'ok' });
    expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh', '/auth/logout']);
  });

  it('로그아웃 자체의 401은 갱신을 시작하지 않고 다음 요청은 다시 갱신할 수 있다', async () => {
    const { calls } = stubFetch({
      '/auth/logout': [unauthorized],
      '/auth/me': [unauthorized, () => ok({ id: 'reader' })],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);

    await expect(api.post('/auth/logout', {})).rejects.toMatchObject({ status: 401 });
    expect(calls.map((call) => call.path)).toEqual(['/auth/logout']);
    await expect(api.get('/auth/me')).resolves.toEqual({ id: 'reader' });
    expect(calls.map((call) => call.path)).toEqual(['/auth/logout', '/auth/me', '/auth/refresh', '/auth/me']);
  });

  it('다른 탭의 토큰 갱신이 끝난 뒤 로그아웃 요청을 보낸다', async () => {
    const refresh = pendingResponse();
    const lockRequest = stubCrossTabLock();
    const { calls } = stubFetch({
      '/auth/me': [unauthorized, () => ok({ id: 'reader' })],
      '/auth/refresh': [() => refresh.promise],
      '/auth/logout': [ok],
    });

    const me = createApi(BASE).get('/auth/me');
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh']));
    const logout = createApi(BASE).post('/auth/logout', {});
    await vi.waitFor(() => expect(lockRequest).toHaveBeenCalledTimes(2));
    expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh']);

    refresh.resolve(ok());
    await expect(me).resolves.toEqual({ id: 'reader' });
    await expect(logout).resolves.toEqual({ message: 'ok' });
    expect(calls.filter((call) => call.init?.method === 'POST').map((call) => call.path)).toEqual([
      '/auth/refresh', '/auth/logout',
    ]);
    expect(lockRequest.mock.calls.map(([name]) => name)).toEqual(['dweb-auth-refresh', 'dweb-auth-refresh']);
  });
});

describe('createApi 로그인·비밀번호 변경의 쿠키 순서', () => {
  it('기존 갱신의 401 쿠키 삭제 응답이 끝난 뒤 로그인한다', async () => {
    const refresh = pendingResponse();
    const { calls } = stubFetch({
      '/auth/me': [unauthorized],
      '/auth/refresh': [() => refresh.promise],
      '/auth/login': [() => ok({ id: 'new-reader' })],
    });
    const api = createApi(BASE);

    const me = expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh']));
    const login = api.post('/auth/login', { email: 'reader@example.com', password: 'password' });
    await Promise.resolve();
    expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh']);

    refresh.resolve(unauthorized());
    await me;
    await expect(login).resolves.toEqual({ id: 'new-reader' });
    expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/refresh', '/auth/login']);
  });

  it('기존 갱신의 새 쿠키가 도착한 뒤 비밀번호를 변경한다', async () => {
    const refresh = pendingResponse();
    const { calls } = stubFetch({
      '/episodes/a/content': [unauthorized],
      '/auth/refresh': [() => refresh.promise],
      '/auth/me/password': [ok],
    });
    const api = createApi(BASE);

    const content = expect(api.get('/episodes/a/content')).rejects.toMatchObject({ status: 401 });
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/episodes/a/content', '/auth/refresh']));
    const change = api.post('/auth/me/password', { current_password: 'old', new_password: 'new' });
    await Promise.resolve();
    expect(calls.map((call) => call.path)).toEqual(['/episodes/a/content', '/auth/refresh']);

    refresh.resolve(ok());
    await content;
    await expect(change).resolves.toEqual({ message: 'ok' });
    expect(calls.map((call) => call.path)).toEqual(['/episodes/a/content', '/auth/refresh', '/auth/me/password']);
  });

  it('비밀번호 변경의 access 401은 같은 락에서 갱신 후 동일 본문으로 한 번 재시도한다', async () => {
    const lockRequest = stubCrossTabLock();
    const { calls } = stubFetch({
      '/auth/me/password': [unauthorized, ok],
      '/auth/refresh': [ok],
    });
    const api = createApi(BASE);
    const change = { current_password: 'old', new_password: 'new' };

    await expect(api.post('/auth/me/password', change)).resolves.toEqual({ message: 'ok' });
    expect(calls.map((call) => call.path)).toEqual(['/auth/me/password', '/auth/refresh', '/auth/me/password']);
    expect(calls[2].init).toMatchObject({ method: 'POST', credentials: 'include', body: JSON.stringify(change) });
    expect(lockRequest).toHaveBeenCalledExactlyOnceWith('dweb-auth-refresh', expect.any(Function));
  });

  it.each([401, 503, 'network'] as const)('비밀번호 변경 중 갱신 %s 실패는 그대로 전파하고 변경을 반복하지 않는다', async (failure) => {
    const error = new TypeError('network');
    const { calls } = stubFetch({
      '/auth/me/password': [() => res(401, { detail: '비밀번호 변경 인증 필요' })],
      '/auth/refresh': [() => failure === 'network' ? Promise.reject(error) : res(failure, {})],
    });
    const api = createApi(BASE);
    const change = api.post('/auth/me/password', {});

    if (failure === 'network') await expect(change).rejects.toBe(error);
    else if (failure === 401) await expect(change).rejects.toMatchObject({ status: 401, message: '{"detail":"비밀번호 변경 인증 필요"}' });
    else await expect(change).rejects.toMatchObject({ status: 503 });
    expect(calls.map((call) => call.path)).toEqual(['/auth/me/password', '/auth/refresh']);
  });

  it.each([400, 422])('비밀번호 변경의 %s 응답에 갱신을 시작하지 않는다', async (status) => {
    const { calls } = stubFetch({ '/auth/me/password': [() => res(status, {})] });
    const api = createApi(BASE);

    await expect(api.post('/auth/me/password', {})).rejects.toMatchObject({ status });
    expect(calls.map((call) => call.path)).toEqual(['/auth/me/password']);
  });

  it('로그인은 앞선 요청의 늦은 401을 차단하고 자격 증명 401에도 갱신하지 않는다', async () => {
    const previous = pendingResponse();
    const { calls } = stubFetch({
      '/auth/me': [() => previous.promise],
      '/auth/login': [unauthorized],
    });
    const api = createApi(BASE);

    const me = expect(api.get('/auth/me')).rejects.toMatchObject({ status: 401 });
    await expect(api.post('/auth/login', {})).rejects.toMatchObject({ status: 401 });
    previous.resolve(unauthorized());
    await me;
    expect(calls.map((call) => call.path)).toEqual(['/auth/me', '/auth/login']);
  });

  it('쿠키 변경을 호출 순서대로 처리하고 중간 요청이 실패해도 다음 요청을 실행한다', async () => {
    const firstLogout = pendingResponse();
    const { calls } = stubFetch({
      '/auth/logout': [() => firstLogout.promise, ok],
      '/auth/login': [unauthorized],
      '/auth/me/password': [ok, ok],
    });
    const api = createApi(BASE);

    const logout = api.post('/auth/logout', {});
    const login = expect(api.post('/auth/login', {})).rejects.toMatchObject({ status: 401 });
    const firstChange = api.post('/auth/me/password', { new_password: 'first' });
    const secondChange = api.post('/auth/me/password', { new_password: 'second' });
    const finalLogout = api.post('/auth/logout', {});
    await vi.waitFor(() => expect(calls.map((call) => call.path)).toEqual(['/auth/logout']));
    firstLogout.resolve(ok());

    await Promise.all([logout, login, firstChange, secondChange, finalLogout]);
    expect(calls.map((call) => call.path)).toEqual([
      '/auth/logout', '/auth/login', '/auth/me/password', '/auth/me/password', '/auth/logout',
    ]);
    expect(calls.slice(2, 4).map((call) => call.init?.body)).toEqual([
      '{"new_password":"first"}', '{"new_password":"second"}',
    ]);
  });
});
