// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ViewerEntry from './ViewerEntry';
import Viewer from './Viewer';

const bootstrap = {
  work_id: 'work-a',
  work_title: '비공개 작품',
  episode_id: 'episode-a',
  public_id: 12345678,
  episode_title: '구매한 비공개 회차',
  episode_subtitle: '부제',
  previous_episode: null,
  next_episode: { public_id: 23456789, title: '공개 다음 회차' },
};
const fullContent = {
  episode_id: 'episode-a',
  content: {
    type: 'doc',
    content: [
      { type: 'image', attrs: { src: 'https://images.test/free.webp' } },
      { type: 'image', attrs: { src: 'https://images.test/paid-full.webp' } },
    ],
  },
  has_paid_part: false,
};
let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

function response(status: number, body: unknown = {}) {
  return new Response(JSON.stringify(body), { status });
}

function paths(): string[] {
  return fetchMock.mock.calls.map(([url]) => new URL(url).pathname);
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  document.cookie = 'login_hint=1';
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubGlobal('IntersectionObserver', class {
    observe() {}
    disconnect() {}
  });
  vi.stubGlobal('requestAnimationFrame', vi.fn(() => 1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  document.cookie = 'login_hint=; Max-Age=0';
  vi.unstubAllGlobals();
});

async function mount() {
  await act(async () => root.render(<ViewerEntry workId="work-a" publicId={12345678} />));
}

function authorizeThenLoad() {
  fetchMock
    .mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, bootstrap))
    .mockResolvedValueOnce(response(200, fullContent))
    .mockResolvedValueOnce(response(404)); // 진행도 없음
}

it('서버 렌더에는 비공개 메타·본문 없이 로딩 셸만 남기고 API를 호출하지 않는다', () => {
  const html = renderToString(<ViewerEntry workId="work-a" publicId={12345678} />);
  expect(html).toContain('회차를 불러오고 있어요');
  expect(html).not.toContain(bootstrap.work_title);
  expect(html).not.toContain(bootstrap.episode_title);
  expect(html).not.toContain('images.test');
  expect(fetchMock).not.toHaveBeenCalled();
});

it('일반 구매자의 세션 복구와 bootstrap 인가 뒤에만 실제 Viewer가 full 본문을 요청한다', async () => {
  let resolveBootstrap!: (value: Response) => void;
  fetchMock
    .mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockReturnValueOnce(new Promise<Response>((resolve) => { resolveBootstrap = resolve; }))
    .mockResolvedValueOnce(response(200, fullContent))
    .mockResolvedValueOnce(response(404));
  await mount();
  expect(paths()).toEqual(['/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap']);
  expect(container.querySelector('img')).toBeNull();
  expect(container.textContent).not.toContain(bootstrap.work_title);

  await act(async () => resolveBootstrap(response(200, bootstrap)));
  expect(paths()).toEqual([
    '/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap',
    '/episodes/episode-a/content', '/episodes/episode-a/progress',
  ]);
  expect([...container.querySelectorAll('img')].map((image) => image.src)).toEqual([
    'https://images.test/free.webp', 'https://images.test/paid-full.webp',
  ]);
  expect(container.textContent).not.toContain('여기부터는 유료 구간');
  const nextLink = container.querySelector('nav[aria-label="회차 끝 이동"] a');
  expect(nextLink?.getAttribute('href')).toBe('/works/work-a/23456789');
  expect(nextLink?.hasAttribute('data-astro-reload')).toBe(true);
  expect(fetchMock.mock.calls.every(([, init]) => init.credentials === 'include')).toBe(true);
});

it('access 만료는 refresh 한 번과 me 재조회 뒤 bootstrap 및 full content로 연결한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200));
  authorizeThenLoad();
  await mount();
  expect(paths()).toEqual([
    '/auth/me', '/auth/refresh', '/auth/me',
    '/works/work-a/episodes/12345678/viewer-bootstrap',
    '/episodes/episode-a/content', '/episodes/episode-a/progress',
  ]);
  expect(container.querySelector('img[src$="paid-full.webp"]')).not.toBeNull();
});

it('비구매 404는 메타·본문과 Viewer 컨트롤을 마운트하지 않는다', async () => {
  fetchMock.mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(404));
  await mount();
  expect(container.textContent).toBe('회차를 찾을 수 없어요.');
  expect(container.querySelector('img, nav, h1')).toBeNull();
  expect(paths()).toEqual(['/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap']);
});

it('stale hint와 최종 401은 익명 bootstrap의 404로 종료한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(404));
  await mount();
  expect(paths()).toEqual([
    '/auth/me', '/auth/refresh', '/works/work-a/episodes/12345678/viewer-bootstrap',
  ]);
  expect(container.textContent).toBe('회차를 찾을 수 없어요.');
  expect(container.querySelector('img')).toBeNull();
  expect(document.cookie).toContain('login_hint=1');
});

it('세션 장애는 bootstrap을 막고 명시적 재시도로 회복한다', async () => {
  fetchMock.mockRejectedValueOnce(new Error('offline'));
  await mount();
  expect(container.textContent).toContain('일시적인 오류');
  expect(paths()).toEqual(['/auth/me']);
  authorizeThenLoad();
  await act(async () => container.querySelector('button')!.click());
  expect(container.querySelector('img[src$="paid-full.webp"]')).not.toBeNull();
});

it('refresh 장애는 메타와 본문을 막고 오류 UI의 재시도로 다시 refresh한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(503))
    .mockResolvedValue(response(404));
  await mount();
  expect(paths()).toEqual(['/auth/me', '/auth/refresh']);
  expect(container.textContent).toContain('일시적인 오류');
  expect(container.querySelector('img, nav, h1')).toBeNull();

  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200));
  authorizeThenLoad();
  await act(async () => container.querySelector('button')!.click());
  expect(paths()).toEqual([
    '/auth/me', '/auth/refresh', '/auth/me', '/auth/refresh', '/auth/me',
    '/works/work-a/episodes/12345678/viewer-bootstrap',
    '/episodes/episode-a/content', '/episodes/episode-a/progress',
  ]);
  expect(container.querySelector('img[src$="paid-full.webp"]')).not.toBeNull();
});

it('회차 전환 후 늦게 끝난 이전 bootstrap으로 본문을 열지 않는다', async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockReturnValueOnce(new Promise<Response>((done) => { resolve = done; }))
    .mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(404));
  await mount();
  await act(async () => root.render(<ViewerEntry workId="work-b" publicId={34567890} />));
  await act(async () => resolve(response(200, bootstrap)));
  expect(container.textContent).toBe('회차를 찾을 수 없어요.');
  expect(paths().some((path) => path.endsWith('/content'))).toBe(false);
});

it('공개 Viewer도 최초 content 전에 세션을 refresh하고 full을 렌더한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(200))
    .mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, fullContent)).mockResolvedValueOnce(response(404));
  await act(async () => root.render(<Viewer episodeId="episode-a" />));
  expect(paths()).toEqual([
    '/auth/me', '/auth/refresh', '/auth/me', '/episodes/episode-a/content',
    '/episodes/episode-a/progress',
  ]);
  expect(container.querySelector('img[src$="paid-full.webp"]')).not.toBeNull();
});

it('공개 게스트 Viewer는 세션 요청 없이 서버가 절단한 preview만 렌더한다', async () => {
  document.cookie = 'login_hint=; Max-Age=0';
  fetchMock.mockResolvedValueOnce(response(200, {
    ...fullContent, content: { type: 'doc', content: [fullContent.content.content[0]] },
    has_paid_part: true,
  }));
  await act(async () => root.render(<Viewer episodeId="episode-a" />));
  expect(paths()).toEqual(['/episodes/episode-a/content']);
  expect(container.querySelectorAll('img')).toHaveLength(1);
  expect(container.querySelector('img[src$="paid-full.webp"]')).toBeNull();
  expect(container.textContent).toContain('여기부터는 유료 구간');
});

it('복구를 기다리는 공개 Viewer가 언마운트되면 content를 요청하지 않는다', async () => {
  let resolve!: (value: Response) => void;
  fetchMock.mockReturnValueOnce(new Promise<Response>((done) => { resolve = done; }));
  await act(async () => root.render(<Viewer episodeId="episode-a" />));
  await act(async () => root.render(null));
  await act(async () => resolve(response(200, { id: 'reader' })));
  expect(paths()).toEqual(['/auth/me']);
});

it('공개 Viewer의 stale hint 최종 401 뒤에는 익명 preview로 수렴한다', async () => {
  fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(401))
    .mockResolvedValueOnce(response(200, {
      ...fullContent,
      content: { type: 'doc', content: [fullContent.content.content[0]] },
      has_paid_part: true,
    })).mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(401));
  await act(async () => root.render(<Viewer episodeId="episode-a" />));
  expect(paths()).toEqual([
    '/auth/me', '/auth/refresh', '/episodes/episode-a/content',
    '/episodes/episode-a/progress', '/auth/refresh',
  ]);
  expect(container.querySelectorAll('img')).toHaveLength(1);
  expect(document.cookie).toContain('login_hint=1');
  expect(container.querySelector('img[src$="paid-full.webp"]')).toBeNull();
  expect(container.textContent).toContain('여기부터는 유료 구간');
});

it.each(['me', 'refresh'])('공개 Viewer의 %s 장애는 content를 막고 수동 재시도 때 다시 복구한다', async (stage) => {
  if (stage === 'refresh') {
    fetchMock.mockResolvedValueOnce(response(401)).mockResolvedValueOnce(response(503))
      .mockResolvedValue(response(404));
  } else {
    fetchMock.mockRejectedValueOnce(new Error('offline'));
  }
  await act(async () => root.render(<Viewer episodeId="episode-a" />));
  const failedPaths = stage === 'refresh' ? ['/auth/me', '/auth/refresh'] : ['/auth/me'];
  expect(paths()).toEqual(failedPaths);
  expect(container.textContent).toContain('일시적인 오류');
  expect(container.querySelector('img')).toBeNull();
  fetchMock.mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, fullContent)).mockResolvedValueOnce(response(404));
  await act(async () => container.querySelector('button')!.click());
  expect(paths()).toEqual([
    ...failedPaths, '/auth/me', '/episodes/episode-a/content', '/episodes/episode-a/progress',
  ]);
  expect(container.querySelector('img[src$="paid-full.webp"]')).not.toBeNull();
});

it('bootstrap 후 최초 content만 세션 재조회를 생략하고 이미지 재발급은 다시 복구한다', async () => {
  authorizeThenLoad();
  await mount();
  fetchMock.mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, fullContent));
  await act(async () => container.querySelector('img')!.dispatchEvent(new Event('error')));
  expect(paths()).toEqual([
    '/auth/me', '/works/work-a/episodes/12345678/viewer-bootstrap',
    '/episodes/episode-a/content', '/episodes/episode-a/progress',
    '/auth/me', '/episodes/episode-a/content',
  ]);
});

it('initialSessionReady는 최초 회차에만 적용하고 회차 변경 때 세션을 복구한다', async () => {
  fetchMock.mockResolvedValueOnce(response(200, fullContent)).mockResolvedValueOnce(response(404));
  await act(async () => root.render(<Viewer episodeId="episode-a" initialSessionReady />));
  expect(paths()).toEqual(['/episodes/episode-a/content', '/episodes/episode-a/progress']);
  fetchMock.mockResolvedValueOnce(response(200, { id: 'reader' }))
    .mockResolvedValueOnce(response(200, { ...fullContent, episode_id: 'episode-b' }))
    .mockResolvedValueOnce(response(404));
  await act(async () => root.render(<Viewer episodeId="episode-b" initialSessionReady />));
  expect(paths().slice(2)).toEqual([
    '/auth/me', '/episodes/episode-b/content', '/episodes/episode-b/progress',
  ]);
});
