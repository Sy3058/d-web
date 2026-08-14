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
  getEpisodeContent.mockResolvedValue({
    episode_id: 'episode-a',
    content: {
      type: 'doc',
      content: [{ type: 'image', attrs: { src: 'https://example.test/page.webp' } }],
    },
    has_paid_part: false,
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
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
