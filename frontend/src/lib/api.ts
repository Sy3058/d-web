import { createApi, ApiError } from '@d-web/shared';
export { ApiError } from '@d-web/shared';

export const api = createApi(import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000');

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
