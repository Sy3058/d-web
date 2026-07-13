type RequestOptions = RequestInit & { json?: unknown };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(baseUrl: string, path: string, options: RequestOptions = {}): Promise<T> {
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

export function createApi(baseUrl: string) {
  return {
    get: <T>(path: string, init?: RequestInit) => request<T>(baseUrl, path, init),
    post: <T>(path: string, json: unknown, init?: RequestInit) =>
      request<T>(baseUrl, path, { method: 'POST', json, ...init }),
    put: <T>(path: string, json: unknown, init?: RequestInit) =>
      request<T>(baseUrl, path, { method: 'PUT', json, ...init }),
    delete: <T>(path: string, init?: RequestInit) =>
      request<T>(baseUrl, path, { method: 'DELETE', ...init }),
  };
}
