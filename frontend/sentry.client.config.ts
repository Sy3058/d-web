import * as Sentry from '@sentry/astro';

export function shouldInitializeClientSentry(pathname: string) {
  return !/^\/auth\/reset-password\/?$/.test(pathname);
}

const dsn = import.meta.env.PUBLIC_SENTRY_DSN;
// The emailed reset URL carries its secret in the fragment. This module runs
// before React can strip it, so telemetry stays disabled for this one page.
if (dsn && shouldInitializeClientSentry(window.location.pathname)) {
  Sentry.init({
    dsn,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 1.0,
  });
}
