/// <reference path="../.astro/types.d.ts" />

interface ImportMetaEnv {
  readonly PUBLIC_API_BASE_URL: string;
  readonly PUBLIC_SENTRY_DSN: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
