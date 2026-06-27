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
