import { createApi } from '@d-web/shared';
// extractDetail은 admin과 공유한다(@d-web/shared) - FastAPI detail 파싱 규칙이 한 곳에만 있도록.
export { ApiError, extractDetail } from '@d-web/shared';

const DEFAULT_API_URL = 'http://localhost:8000';

interface ApiBaseUrlOptions {
  isServer: boolean;
  publicUrl?: string;
  internalUrl?: string;
}

export function resolveApiBaseUrl({
  isServer,
  publicUrl,
  internalUrl,
}: ApiBaseUrlOptions): string {
  if (isServer && internalUrl) return internalUrl;
  return publicUrl ?? DEFAULT_API_URL;
}

// PUBLIC_API_URL은 브라우저가 접근할 주소, API_INTERNAL_URL은 SSR Node가
// compose 네트워크에서 접근할 주소다. Node adapter는 process.env로
// 런타임 환경을 읽는다. SSR 분기 밖에서는 참조하지 않아 클라이언트
// 번들에 내부 주소가 들어가지 않는다.
const internalApiUrl = import.meta.env.SSR ? process.env.API_INTERNAL_URL : undefined;

export const api = createApi(
  resolveApiBaseUrl({
    isServer: import.meta.env.SSR,
    publicUrl: import.meta.env.PUBLIC_API_URL,
    internalUrl: internalApiUrl,
  }),
);
