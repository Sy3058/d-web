// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { init, browserTracingIntegration } = vi.hoisted(() => ({
  init: vi.fn(),
  browserTracingIntegration: vi.fn(() => ({ name: 'browser-tracing' })),
}));

vi.mock('@sentry/astro', () => ({ init, browserTracingIntegration }));

async function loadClientConfig(url: string) {
  window.history.replaceState({}, '', url);
  vi.resetModules();
  await import('./sentry.client.config');
}

describe('client Sentry 초기화 경로', () => {
  beforeEach(() => {
    init.mockReset();
    browserTracingIntegration.mockClear();
    vi.stubEnv('PUBLIC_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each([
    '/auth/reset-password#token=secret',
    '/auth/reset-password/#token=secret',
  ])('재설정 URL %s에서는 실제 Sentry 초기화를 건너뛴다', async (url) => {
    await loadClientConfig(url);
    expect(init).not.toHaveBeenCalled();
    expect(browserTracingIntegration).not.toHaveBeenCalled();
  });

  it('일반 페이지에서는 browser tracing과 Sentry를 초기화한다', async () => {
    await loadClientConfig('/auth/forgot-password');
    expect(browserTracingIntegration).toHaveBeenCalledOnce();
    expect(init).toHaveBeenCalledWith(expect.objectContaining({
      dsn: 'https://public@example.ingest.sentry.io/1',
      integrations: [{ name: 'browser-tracing' }],
    }));
  });
});
