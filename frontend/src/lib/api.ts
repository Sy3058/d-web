const BASE_URL = import.meta.env.PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

type RequestOptions = RequestInit & { json?: unknown };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { json, ...init } = options;

  const headers: HeadersInit = { ...(init.headers as Record<string, string>) };
  let body = init.body;

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    ...init,
    headers,
    body,
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }

  const text = await res.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>(path, init),
  post: <T>(path: string, json: unknown, init?: RequestInit) => request<T>(path, { method: 'POST', json, ...init }),
  put: <T>(path: string, json: unknown, init?: RequestInit) => request<T>(path, { method: 'PUT', json, ...init }),
  delete: <T>(path: string, init?: RequestInit) => request<T>(path, { method: 'DELETE', ...init }),
};
