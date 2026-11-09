// @vitest-environment jsdom
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import Viewer from './Viewer';

// BE 회귀 테스트가 증명하는 삭제 응답을 브라우저가 적용했을 때의 FE 호환성이다.
// 쿠키 삭제가 없는 구버전 BE 동작은 ViewerEntry.test.tsx에서 별도로 검증한다.
it('refresh 401의 쿠키 정리 뒤에는 추가 refresh 없이 익명 preview만 요청한다', async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  document.cookie = 'login_hint=stale';
  const fetch = vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockImplementationOnce(async () => {
      // 실제 Set-Cookie 3종·Path·보안 속성은 BE ASGI 테스트에서 확인한다.
      document.cookie = 'login_hint=; Max-Age=0; Path=/';
      return new Response('{}', { status: 401 });
    })
    .mockResolvedValueOnce(new Response(JSON.stringify({
      episode_id: 'episode-a',
      access_scope: 'preview',
      content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '무료 구간' }] }] },
      has_paid_part: true,
    })));
  vi.stubGlobal('fetch', fetch);
  vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} });
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const container = document.createElement('div');
  document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    expect(fetch.mock.calls.map(([url]) => new URL(url).pathname)).toEqual([
      '/auth/me', '/auth/refresh', '/episodes/episode-a/content',
    ]);
    expect(document.cookie).not.toContain('login_hint=');
    expect(container.textContent).toContain('무료 구간');
    expect(container.textContent).toContain('여기부터는 유료 구간');
    expect(container.querySelector('img')).toBeNull();
  } finally {
    await act(async () => root.unmount());
    container.remove();
    document.cookie = 'login_hint=; Max-Age=0; Path=/';
    vi.unstubAllGlobals();
  }
});
