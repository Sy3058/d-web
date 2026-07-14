type RequestOptions = RequestInit & { json?: unknown };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const REFRESH_PATH = '/auth/refresh';

/** 401이 "access 만료"가 아니라 자격 증명 거부·로그인 단계 만료를 뜻하는 경로(prefix).
 *
 * 여기서 자동 refresh를 돌리면 틀린 비밀번호·TOTP 제출이 refresh 후 자동 재전송되고,
 * refresh 자신이 401일 때 재귀한다. 로그인 계열의 401은 그대로 호출자에게 전달돼야
 * 폼이 에러 문구를 보여줄 수 있다.
 */
const NO_RETRY_PREFIXES = [REFRESH_PATH, '/auth/login', '/admin/login', '/admin/2fa'];

async function rawRequest<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { json, ...init } = options;
  const headers: HeadersInit = { ...(init.headers as Record<string, string>) };
  let body = init.body;

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    credentials: 'include',
    headers,
    body,
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }

  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

/** FastAPI 에러 본문에서 사람이 읽을 문구를 뽑는다.
 *
 * detail은 문자열(HTTPException)이거나 배열(pydantic 422 검증 에러)이다.
 * 응답이 JSON이 아니면 undefined - 호출자가 폴백 문구를 정한다.
 */
export function extractDetail(err: ApiError): string | undefined {
  try {
    const body = JSON.parse(err.message) as { detail?: unknown };
    const detail = body.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown };
      if (typeof first?.msg === 'string') return first.msg;
    }
  } catch {
    // 응답이 JSON이 아니면 undefined 반환
  }
  return undefined;
}

/** refresh를 같은 오리진의 다른 탭과 직렬화한다.
 *
 * 아래 in-flight 공유(refreshPromise)는 탭 하나 안에서만 유효하다 - 탭마다 JS 컨텍스트가
 * 따로라서, 두 탭이 동시에 401을 받으면 각자 refresh를 쏘고 둘 다 같은 refresh 토큰
 * (쿠키는 브라우저 공유)을 제출한다. 백엔드 회전(rotate_refresh)은 이미 회전된 토큰의
 * 재제출을 탈취 신호로 보고 전 세션을 revoke하므로, 락 없이는 멀티탭이 오발동을 만든다.
 * 락을 기다린 탭은 앞 탭이 회전해 둔 새 쿠키로 갱신하므로 성공한다.
 * Web Locks 미지원(비보안 컨텍스트·node/Astro 빌드)이면 기존처럼 직접 호출로 폴백.
 */
function withCrossTabLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator === 'undefined' || !navigator.locks) return fn();
  return navigator.locks.request('dweb-auth-refresh', fn);
}

export function createApi(baseUrl: string) {
  // 동시에 여러 요청이 401을 받아도(화면 진입 시 쿼리 병렬 발사) refresh는 한 번만
  // 나가도록 in-flight promise를 공유한다. refresh 토큰은 회전식이라 중복 호출하면
  // 나중 호출이 이미 회전된 토큰을 재제출하게 돼 401로 튕긴다(_claim 패자).
  let refreshPromise: Promise<boolean> | null = null;

  function refreshSession(): Promise<boolean> {
    refreshPromise ??= withCrossTabLock(() =>
      rawRequest<unknown>(baseUrl, REFRESH_PATH, { method: 'POST' }),
    )
      .then(
        () => true,
        // refresh 실패(리프레시 토큰 만료/무효)는 여기서 삼키고 false만 알린다 -
        // 호출자는 원요청의 401을 던져 각 앱의 인증 가드가 로그인 화면으로 보내게 한다.
        () => false,
      )
      .finally(() => {
        refreshPromise = null;
      });
    return refreshPromise;
  }

  async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    try {
      return await rawRequest<T>(baseUrl, path, options);
    } catch (err) {
      const accessExpired =
        err instanceof ApiError &&
        err.status === 401 &&
        !NO_RETRY_PREFIXES.some((prefix) => path.startsWith(prefix));
      if (accessExpired && (await refreshSession())) {
        // 재시도는 1회뿐: 이 rawRequest가 또 401이면 catch 없이 그대로 전파된다.
        return rawRequest<T>(baseUrl, path, options);
      }
      throw err;
    }
  }

  return {
    get: <T>(path: string, init?: RequestInit) => request<T>(path, init),
    post: <T>(path: string, json: unknown, init?: RequestInit) =>
      request<T>(path, { method: 'POST', json, ...init }),
    put: <T>(path: string, json: unknown, init?: RequestInit) =>
      request<T>(path, { method: 'PUT', json, ...init }),
    delete: <T>(path: string, init?: RequestInit) => request<T>(path, { method: 'DELETE', ...init }),
  };
}
