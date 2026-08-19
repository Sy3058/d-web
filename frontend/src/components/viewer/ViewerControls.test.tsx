// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ViewerControls from './ViewerControls';

let container: HTMLDivElement;
let root: Root;

const props = {
  visible: true,
  workId: 'work-a',
  workTitle: '작품 A',
  episodeTitle: '회차 A',
  episodeSubtitle: null,
  previousEpisode: { publicId: 10_000_001, title: '이전 회차' },
  nextEpisode: { publicId: 10_000_003, title: '다음 회차' },
};

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('ViewerControls', () => {
  it('긴 회차 제목과 부제를 블록에서 말줄임하고 전체 문자열을 제공한다', async () => {
    await act(async () =>
      root.render(<ViewerControls {...props} episodeSubtitle="긴 부제" />),
    );

    const title = container.querySelector('[data-viewer-episode-title]');
    expect(title?.className).toContain('truncate');
    expect(title?.getAttribute('title')).toBe('회차 A · 긴 부제');
  });

  it('작품 상세·목록·인접 회차를 실제 경로에 연결한다', async () => {
    await act(async () => root.render(<ViewerControls {...props} />));

    expect(container.querySelector('a[aria-label="작품 A 작품 상세로 이동"]')?.getAttribute('href')).toBe(
      '/works/work-a',
    );
    expect(
      container.querySelector('a[aria-label="작품 A 전체 회차 목록으로 이동"]')?.getAttribute('href'),
    ).toBe('/works/work-a#episodes');
    expect(container.querySelector('a[aria-label="이전 화: 이전 회차"]')?.getAttribute('href')).toBe(
      '/works/work-a/10000001',
    );
    expect(container.querySelector('a[aria-label="다음 화: 다음 회차"]')?.getAttribute('href')).toBe(
      '/works/work-a/10000003',
    );
    expect(container.querySelectorAll('a[data-astro-reload]')).toHaveLength(2);
  });

  it('첫 화와 마지막 화의 없는 방향을 비활성 접근성 상태로 표시한다', async () => {
    await act(async () =>
      root.render(<ViewerControls {...props} previousEpisode={null} nextEpisode={null} />),
    );

    const previous = container.querySelector('button[aria-label="이전 화 없음"]');
    const next = container.querySelector('button[aria-label="다음 화 없음"]');
    expect((previous as HTMLButtonElement).disabled).toBe(true);
    expect(previous?.getAttribute('aria-disabled')).toBe('true');
    expect((next as HTMLButtonElement).disabled).toBe(true);
    expect(next?.getAttribute('aria-disabled')).toBe('true');
  });

  it('숨김 상태에서는 두 컨트롤을 접근성 트리와 포인터 입력에서 제외한다', async () => {
    await act(async () => root.render(<ViewerControls {...props} visible={false} />));

    for (const controls of container.querySelectorAll('[data-visible="false"]')) {
      expect(controls.getAttribute('aria-hidden')).toBe('true');
      expect(controls.hasAttribute('inert')).toBe(true);
      expect(controls.className).toContain('pointer-events-none');
    }
  });

  it('Web Share API를 우선 사용하고 결과를 알린다', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { share });
    await act(async () => root.render(<ViewerControls {...props} />));

    await act(async () =>
      (container.querySelector('button[aria-label="현재 회차 공유"]') as HTMLButtonElement).click(),
    );

    expect(share).toHaveBeenCalledWith({
      title: '회차 A · 작품 A',
      url: window.location.href,
    });
    expect(container.querySelector('[role="status"]')?.textContent).toBe('공유 창을 열었어요.');
  });

  it('Web Share 미지원 환경에서는 현재 주소를 clipboard에 복사한다', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    await act(async () => root.render(<ViewerControls {...props} />));

    await act(async () =>
      (container.querySelector('button[aria-label="현재 회차 공유"]') as HTMLButtonElement).click(),
    );

    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(container.querySelector('[role="status"]')?.textContent).toBe('주소를 복사했어요.');
  });

  it('Web Share 실패도 clipboard 복사로 복구한다', async () => {
    const share = vi.fn().mockRejectedValue(new Error('share failed'));
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { share, clipboard: { writeText } });
    await act(async () => root.render(<ViewerControls {...props} />));

    await act(async () =>
      (container.querySelector('button[aria-label="현재 회차 공유"]') as HTMLButtonElement).click(),
    );

    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(container.querySelector('[role="status"]')?.textContent).toBe('주소를 복사했어요.');
  });

  it('공유 수단이 없으면 실패를 알린다', async () => {
    vi.stubGlobal('navigator', {});
    await act(async () => root.render(<ViewerControls {...props} />));

    await act(async () =>
      (container.querySelector('button[aria-label="현재 회차 공유"]') as HTMLButtonElement).click(),
    );

    expect(container.querySelector('[role="status"]')?.textContent).toBe('공유하지 못했어요.');
  });
});
