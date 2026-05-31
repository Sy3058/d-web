import { createApi } from '@d-web/shared';
export { ApiError } from '@d-web/shared';

export const api = createApi(import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000');
