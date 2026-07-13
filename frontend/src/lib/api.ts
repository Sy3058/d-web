import { createApi } from '@d-web/shared';
// extractDetail은 admin과 공유한다(@d-web/shared) - FastAPI detail 파싱 규칙이 한 곳에만 있도록.
export { ApiError, extractDetail } from '@d-web/shared';

export const api = createApi(import.meta.env.PUBLIC_API_URL ?? 'http://localhost:8000');
