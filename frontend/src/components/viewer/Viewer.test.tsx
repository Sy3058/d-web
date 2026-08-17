// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getEpisodeContent, getProgress, isLoggedIn, putProgress } = vi.hoisted(() => ({
  getEpisodeContent: vi.fn(),
  getProgress: vi.fn(),
  isLoggedIn: vi.fn(),
  putProgress: vi.fn(),
}));

vi.mock('../../lib/viewer', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/viewer')>();
  return {
    ...original,
    getEpisodeContent,
    getProgress,
    isLoggedIn,
    putProgress,
  };
});

import Viewer from './Viewer';

class MockIntersectionObserver {
  readonly root = null;
  readonly rootMargin = '0px';
  readonly thresholds = [0];

  constructor(private readonly callback: IntersectionObserverCallback) {}

  observe(target: Element) {
    this.callback(
      [{ isIntersecting: true, target } as IntersectionObserverEntry],
      this as unknown as IntersectionObserver,
    );
  }

  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}

let container: HTMLDivElement;
let root: Root;
let rootMounted: boolean;

const episodeContentWithImages = (episodeId: string, srcs: string[]) => ({
  episode_id: episodeId,
  content: {
    type: 'doc' as const,
    content: srcs.map((src) => ({ type: 'image', attrs: { src } })),
  },
  has_paid_part: false,
});

const episodeContent = (episodeId: string, src = `https://example.test/${episodeId}.webp`) =>
  episodeContentWithImages(episodeId, [src]);

beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(0), 0),
  );
  vi.stubGlobal('cancelAnimationFrame', (id: number) => window.clearTimeout(id));
  getEpisodeContent.mockReset();
  getProgress.mockReset();
  isLoggedIn.mockReset();
  putProgress.mockReset();
  isLoggedIn.mockReturnValue(true);
  getEpisodeContent.mockResolvedValue(episodeContent('episode-a'));
  getProgress.mockResolvedValue(null);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  rootMounted = true;
});

afterEach(async () => {
  if (rootMounted) await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('Viewer content request state', () => {
  it('초기 요청이 reject되면 로딩을 끝내고 오류 UI를 표시한다', async () => {
    getEpisodeContent.mockRejectedValue(new Error('network error'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));

    expect(container.textContent).not.toContain('불러오는 중...');
    expect(container.textContent).toContain('일시적인 오류로 회차 내용을 불러오지 못했어요.');
    expect(container.querySelector('button')?.textContent).toContain('다시 시도');
  });

  it('오류 UI에서 다시 시도한 요청이 성공하면 콘텐츠를 렌더한다', async () => {
    getEpisodeContent
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce(episodeContent('episode-a'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => (container.querySelector('button') as HTMLButtonElement).click());

    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      'https://example.test/episode-a.webp',
    );
    expect(getEpisodeContent).toHaveBeenCalledTimes(2);
  });

  it('404 null 응답은 기존 notFound UI를 유지한다', async () => {
    getEpisodeContent.mockResolvedValue(null);

    await act(async () => root.render(<Viewer episodeId="episode-a" />));

    expect(container.textContent).toContain('회차를 찾을 수 없어요.');
    expect(container.querySelector('button')).toBeNull();
  });

  it('이미지 재발급 요청이 reject되면 unhandled rejection 없이 오류 상태가 된다', async () => {
    getEpisodeContent
      .mockResolvedValueOnce(episodeContent('episode-a'))
      .mockRejectedValueOnce(new Error('presign refresh failed'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () =>
      container.querySelector('img')?.dispatchEvent(new window.Event('error', { bubbles: true })),
    );

    expect(container.textContent).toContain('일시적인 오류로 회차 내용을 불러오지 못했어요.');
    expect(getEpisodeContent).toHaveBeenCalledTimes(2);
  });

  it('재발급 진행 중 옛 이미지가 더 실패해도 placeholder나 중복 요청을 만들지 않는다', async () => {
    let resolveRefresh: (value: ReturnType<typeof episodeContentWithImages>) => void = () =>
      undefined;
    getEpisodeContent
      .mockResolvedValueOnce(
        episodeContentWithImages('episode-a', [
          'https://example.test/old-1.webp',
          'https://example.test/old-2.webp',
        ]),
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveRefresh = resolve;
        }),
      );

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    const oldImages = container.querySelectorAll('img');
    await act(async () => oldImages[0].dispatchEvent(new window.Event('error')));
    await act(async () => oldImages[1].dispatchEvent(new window.Event('error')));

    expect(getEpisodeContent).toHaveBeenCalledTimes(2);
    expect(container.querySelectorAll('[data-image-error="true"]')).toHaveLength(0);

    await act(async () =>
      resolveRefresh(
        episodeContentWithImages('episode-a', [
          'https://example.test/new-1.webp',
          'https://example.test/new-2.webp',
        ]),
      ),
    );
  });

  it('재발급된 URL도 실패한 이미지 블록만 버튼 없는 placeholder로 바꾼다', async () => {
    getEpisodeContent
      .mockResolvedValueOnce(
        episodeContentWithImages('episode-a', [
          'https://example.test/old-1.webp',
          'https://example.test/old-2.webp',
          'https://example.test/old-3.webp',
          'https://example.test/old-4.webp',
        ]),
      )
      .mockResolvedValueOnce(
        episodeContentWithImages('episode-a', [
          'https://example.test/new-1.webp',
          'https://example.test/new-2.webp',
          'https://example.test/new-3.webp',
          'https://example.test/new-4.webp',
        ]),
      );

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () =>
      container
        .querySelector('[data-block-index="1"] img')
        ?.dispatchEvent(new window.Event('error')),
    );
    await act(async () =>
      container
        .querySelector('[data-block-index="1"] img')
        ?.dispatchEvent(new window.Event('error')),
    );
    await act(async () =>
      container
        .querySelector('[data-block-index="3"] img')
        ?.dispatchEvent(new window.Event('error')),
    );

    expect(container.querySelectorAll('[data-image-error="true"]')).toHaveLength(2);
    expect(container.querySelectorAll('img')).toHaveLength(2);
    expect(container.querySelector('[data-block-index="0"] img')?.getAttribute('src')).toBe(
      'https://example.test/new-1.webp',
    );
    expect(container.querySelector('[data-block-index="2"] img')?.getAttribute('src')).toBe(
      'https://example.test/new-3.webp',
    );
    expect(container.querySelector('button')).toBeNull();
    expect(getEpisodeContent).toHaveBeenCalledTimes(2);
  });

  it('동일 URL이 재발급돼도 img를 재마운트해 다음 실패를 placeholder로 연결한다', async () => {
    const sameContent = episodeContent('episode-a', 'https://example.test/same.webp');
    getEpisodeContent.mockResolvedValueOnce(sameContent).mockResolvedValueOnce(sameContent);

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    const initialImage = container.querySelector('img') as HTMLImageElement;
    await act(async () => initialImage.dispatchEvent(new window.Event('error')));

    const refreshedImage = container.querySelector('img') as HTMLImageElement;
    expect(refreshedImage).not.toBe(initialImage);
    expect(refreshedImage.getAttribute('src')).toBe('https://example.test/same.webp');

    await act(async () => refreshedImage.dispatchEvent(new window.Event('error')));

    expect(container.querySelector('[data-image-error="true"]')).not.toBeNull();
    expect(getEpisodeContent).toHaveBeenCalledTimes(2);
  });

  it('episodeId가 바뀌면 이미지 placeholder 상태도 제거한다', async () => {
    getEpisodeContent
      .mockResolvedValueOnce(episodeContent('episode-a', 'https://example.test/old.webp'))
      .mockResolvedValueOnce(episodeContent('episode-a', 'https://example.test/new.webp'))
      .mockResolvedValueOnce(episodeContent('episode-b'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () =>
      container.querySelector('img')?.dispatchEvent(new window.Event('error')),
    );
    await act(async () =>
      container.querySelector('img')?.dispatchEvent(new window.Event('error')),
    );
    expect(container.querySelector('[data-image-error="true"]')).not.toBeNull();

    await act(async () => root.render(<Viewer episodeId="episode-b" />));

    expect(container.querySelector('[data-image-error="true"]')).toBeNull();
    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      'https://example.test/episode-b.webp',
    );
  });

  it('episodeId가 바뀌면 이전 콘텐츠와 이미지 재시도 상태를 초기화한다', async () => {
    getEpisodeContent
      .mockResolvedValueOnce(episodeContent('episode-a'))
      .mockResolvedValueOnce(episodeContent('episode-a', 'https://example.test/episode-a-new.webp'))
      .mockResolvedValueOnce(episodeContent('episode-b'))
      .mockResolvedValueOnce(episodeContent('episode-b', 'https://example.test/episode-b-new.webp'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () =>
      container.querySelector('img')?.dispatchEvent(new window.Event('error', { bubbles: true })),
    );
    await act(async () => root.render(<Viewer episodeId="episode-b" />));
    await act(async () =>
      container.querySelector('img')?.dispatchEvent(new window.Event('error', { bubbles: true })),
    );

    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      'https://example.test/episode-b-new.webp',
    );
    expect(getEpisodeContent.mock.calls).toEqual([
      ['episode-a'],
      ['episode-a'],
      ['episode-b'],
      ['episode-b'],
    ]);
  });

  it('이전 회차의 늦은 응답이 새 회차 콘텐츠를 덮어쓰지 않는다', async () => {
    let resolveEpisodeA: (value: ReturnType<typeof episodeContent>) => void = () => undefined;
    getEpisodeContent
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveEpisodeA = resolve;
        }),
      )
      .mockResolvedValueOnce(episodeContent('episode-b'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => root.render(<Viewer episodeId="episode-b" />));
    await act(async () => resolveEpisodeA(episodeContent('episode-a')));

    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      'https://example.test/episode-b.webp',
    );
  });

  it('언마운트 뒤 늦은 reject를 처리하고 상태를 갱신하지 않는다', async () => {
    let rejectRequest: (reason: Error) => void = () => undefined;
    getEpisodeContent.mockReturnValueOnce(
      new Promise((_, reject) => {
        rejectRequest = reject;
      }),
    );

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => root.unmount());
    rootMounted = false;
    await act(async () => rejectRequest(new Error('late reject')));

    expect(container.textContent).toBe('');
  });
});

describe('Viewer progress restore gate', () => {
  it('느린 진행도 GET이 끝나기 전에는 초기 위치를 저장하지 않는다', async () => {
    let resolveProgress: (value: null) => void = () => undefined;
    getProgress.mockReturnValue(
      new Promise<null>((resolve) => {
        resolveProgress = resolve;
      }),
    );

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => vi.advanceTimersByTimeAsync(2_000));

    expect(putProgress).not.toHaveBeenCalled();

    await act(async () => resolveProgress(null));
    await act(async () => vi.advanceTimersByTimeAsync(801));

    expect(putProgress).toHaveBeenCalledWith('episode-a', 0, 0);
  });
});
