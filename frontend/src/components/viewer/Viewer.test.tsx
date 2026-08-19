// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getBrowserGuestProgress,
  getEpisodeContent,
  getProgress,
  isLoggedIn,
  putBrowserGuestProgress,
  putProgress,
} = vi.hoisted(() => ({
  getBrowserGuestProgress: vi.fn(),
  getEpisodeContent: vi.fn(),
  getProgress: vi.fn(),
  isLoggedIn: vi.fn(),
  putBrowserGuestProgress: vi.fn(),
  putProgress: vi.fn(),
}));

vi.mock('../../lib/guestProgress', () => ({
  getBrowserGuestProgress,
  putBrowserGuestProgress,
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

const navigation = {
  workId: 'work-a',
  workTitle: '작품 A',
  episodeTitle: '회차 A',
  episodeSubtitle: null,
  previousEpisode: null,
  nextEpisode: { publicId: 10_000_002, title: '다음 회차' },
};

beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('IntersectionObserver', MockIntersectionObserver);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) =>
    window.setTimeout(() => callback(0), 0),
  );
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn((id: number) => window.clearTimeout(id)),
  );
  Object.defineProperty(window, 'scrollY', { configurable: true, writable: true, value: 0 });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 });
  Object.defineProperty(document.documentElement, 'scrollHeight', {
    configurable: true,
    value: 1_600,
  });
  getEpisodeContent.mockReset();
  getBrowserGuestProgress.mockReset();
  getProgress.mockReset();
  isLoggedIn.mockReset();
  putBrowserGuestProgress.mockReset();
  putProgress.mockReset();
  isLoggedIn.mockReturnValue(true);
  getBrowserGuestProgress.mockReturnValue(null);
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
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('Viewer floating controls', () => {
  it('사용자 하향·상향 누적 스크롤에 따라 상하단 컨트롤을 함께 전환한다', async () => {
    await act(async () => root.render(<Viewer episodeId="episode-a" navigation={navigation} />));

    const topControls = () => container.querySelector('[data-viewer-top-controls]');
    const bottomControls = () => container.querySelector('[data-viewer-bottom-controls]');
    expect(topControls()?.getAttribute('data-visible')).toBe('true');
    expect(bottomControls()?.getAttribute('data-visible')).toBe('true');

    window.scrollY = 47;
    await act(async () => window.dispatchEvent(new window.Event('scroll')));
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(topControls()?.getAttribute('data-visible')).toBe('true');

    window.scrollY = 48;
    await act(async () => window.dispatchEvent(new window.Event('scroll')));
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(topControls()?.getAttribute('data-visible')).toBe('false');
    expect(bottomControls()?.getAttribute('data-visible')).toBe('false');

    window.scrollY = 24;
    await act(async () => window.dispatchEvent(new window.Event('scroll')));
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(topControls()?.getAttribute('data-visible')).toBe('true');
    expect(bottomControls()?.getAttribute('data-visible')).toBe('true');
  });

  it('프로그램적 진행도 복원 뒤에도 컨트롤을 최초 표시 상태로 유지한다', async () => {
    isLoggedIn.mockReturnValue(false);
    getBrowserGuestProgress.mockReturnValue({ pageNo: 0, blockOffsetBp: 6_000, updatedAt: 1 });
    getEpisodeContent.mockResolvedValue({
      episode_id: 'episode-a',
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '복원 대상' }] }],
      },
      has_paid_part: false,
    });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      top: 0,
      bottom: 1_000,
      left: 0,
      right: 100,
      width: 100,
      height: 1_000,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
    vi.stubGlobal('scrollTo', ({ top }: ScrollToOptions) => {
      window.scrollY = Number(top);
      window.dispatchEvent(new window.Event('scroll'));
    });

    await act(async () => root.render(<Viewer episodeId="episode-a" navigation={navigation} />));
    await act(async () => vi.advanceTimersByTimeAsync(1));

    expect(window.scrollY).toBe(600);
    expect(container.querySelector('[data-viewer-top-controls]')?.getAttribute('data-visible')).toBe(
      'true',
    );
    expect(
      container.querySelector('[data-viewer-bottom-controls]')?.getAttribute('data-visible'),
    ).toBe('true');
  });

  it('언마운트할 때 컨트롤 scroll listener와 예약된 rAF를 정리한다', async () => {
    const removeEventListener = vi.spyOn(window, 'removeEventListener');
    const cancelAnimationFrame = vi.mocked(globalThis.cancelAnimationFrame);

    await act(async () => root.render(<Viewer episodeId="episode-a" navigation={navigation} />));
    window.scrollY = 20;
    await act(async () => window.dispatchEvent(new window.Event('scroll')));
    await act(async () => root.unmount());
    rootMounted = false;

    expect(removeEventListener.mock.calls.some(([type]) => type === 'scroll')).toBe(true);
    expect(cancelAnimationFrame).toHaveBeenCalled();
  });
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

  it('비로그인 스크롤 후 계산한 블록과 내부 위치를 로컬에 저장한다', async () => {
    isLoggedIn.mockReturnValue(false);
    getEpisodeContent.mockResolvedValue({
      episode_id: 'episode-a',
      content: {
        type: 'doc',
        content: [
          { type: 'paragraph', content: [{ type: 'text', text: '첫 블록' }] },
          { type: 'paragraph', content: [{ type: 'text', text: '긴 두 번째 블록' }] },
        ],
      },
      has_paid_part: false,
    });
    let scrolled = false;
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      const index = Number(this.dataset.blockIndex ?? 0);
      const top = scrolled ? (index === 0 ? -5_400 : -3_240) : index * 5_400;
      return {
        top,
        bottom: top + 5_400,
        left: 0,
        right: 100,
        width: 100,
        height: 5_400,
        x: 0,
        y: top,
        toJSON: () => ({}),
      };
    });

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => vi.advanceTimersByTimeAsync(1));
    scrolled = true;
    await act(async () => window.dispatchEvent(new window.Event('scroll')));
    await act(async () => vi.advanceTimersByTimeAsync(801));

    expect(getProgress).not.toHaveBeenCalled();
    expect(putProgress).not.toHaveBeenCalled();
    expect(getBrowserGuestProgress).toHaveBeenCalledWith('episode-a');
    expect(putBrowserGuestProgress).toHaveBeenCalledTimes(1);
    expect(putBrowserGuestProgress).toHaveBeenCalledWith('episode-a', 1, 6_000);
  });

  it('로그인은 localStorage 경로를 읽거나 쓰지 않는다', async () => {
    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => vi.advanceTimersByTimeAsync(801));

    expect(getProgress).toHaveBeenCalledWith('episode-a');
    expect(putProgress).toHaveBeenCalledWith('episode-a', 0, 0);
    expect(getBrowserGuestProgress).not.toHaveBeenCalled();
    expect(putBrowserGuestProgress).not.toHaveBeenCalled();
  });

  it('비로그인 저장 인덱스를 줄어든 본문의 마지막 블록으로 clamp하고 내부 위치를 복원한다', async () => {
    isLoggedIn.mockReturnValue(false);
    getBrowserGuestProgress.mockReturnValue({ pageNo: 99, blockOffsetBp: 6_000, updatedAt: 1 });
    getEpisodeContent.mockResolvedValue({
      episode_id: 'episode-a',
      content: {
        type: 'doc',
        content: [
          { type: 'paragraph', content: [{ type: 'text', text: '첫 블록' }] },
          { type: 'paragraph', content: [{ type: 'text', text: '마지막 블록' }] },
        ],
      },
      has_paid_part: false,
    });
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      const index = Number(this.dataset.blockIndex ?? 0);
      return {
        top: index * 100,
        bottom: index * 100 + 100,
        left: 0,
        right: 100,
        width: 100,
        height: 100,
        x: 0,
        y: index * 100,
        toJSON: () => ({}),
      };
    });
    const scrollTo = vi.fn();
    vi.stubGlobal('scrollTo', scrollTo);

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => vi.advanceTimersByTimeAsync(1));

    expect(scrollTo).toHaveBeenCalledWith({ top: 160, behavior: 'auto' });
    expect(getProgress).not.toHaveBeenCalled();
  });

  it('비로그인 로컬 진행도가 있어도 유료 경계 표시는 유지한다', async () => {
    isLoggedIn.mockReturnValue(false);
    getBrowserGuestProgress.mockReturnValue({ pageNo: 0, blockOffsetBp: 9_999, updatedAt: 1 });
    getEpisodeContent.mockResolvedValue({
      episode_id: 'episode-a',
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '무료 미리보기' }] }],
      },
      has_paid_part: true,
    });

    await act(async () => root.render(<Viewer episodeId="episode-a" />));

    expect(container.textContent).toContain('여기부터는 유료 구간이에요.');
    expect(getProgress).not.toHaveBeenCalled();
  });

  it('비로그인 회차가 바뀌면 새 episodeId의 로컬 위치만 읽고 저장한다', async () => {
    isLoggedIn.mockReturnValue(false);
    getEpisodeContent
      .mockResolvedValueOnce(episodeContent('episode-a'))
      .mockResolvedValueOnce(episodeContent('episode-b'));

    await act(async () => root.render(<Viewer episodeId="episode-a" />));
    await act(async () => vi.advanceTimersByTimeAsync(801));
    await act(async () => root.render(<Viewer episodeId="episode-b" />));
    await act(async () => vi.advanceTimersByTimeAsync(801));

    expect(getBrowserGuestProgress.mock.calls).toEqual([['episode-a'], ['episode-b']]);
    expect(putBrowserGuestProgress).toHaveBeenLastCalledWith('episode-b', 0, 0);
    expect(getProgress).not.toHaveBeenCalled();
    expect(putProgress).not.toHaveBeenCalled();
  });
});
