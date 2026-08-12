// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getWorkProgress, isLoggedIn } = vi.hoisted(() => ({
  getWorkProgress: vi.fn(),
  isLoggedIn: vi.fn(),
}));

vi.mock('../../lib/workProgress', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/workProgress')>();
  return { ...original, getWorkProgress };
});

vi.mock('../../lib/viewer', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/viewer')>();
  return { ...original, isLoggedIn };
});

import WorkProgress from './WorkProgress';

let container: HTMLDivElement;
let root: Root;

const episodes = [
  { id: 'a', publicId: 11111111, title: '첫 만남' },
  { id: 'b', publicId: 22222222, title: '비 오는 날' },
  { id: 'c', publicId: 33333333, title: '달빛 아래 재회' },
  { id: 'd', publicId: 44444444, title: '새로운 아침' },
];

async function renderProgress() {
  await act(async () => {
    root.render(<WorkProgress workId="work-a" episodes={episodes} />);
  });
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  getWorkProgress.mockReset();
  isLoggedIn.mockReset();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('WorkProgress', () => {
  it('서버 초기 HTML에는 공개 첫 화 CTA만 있고 개인 진행도는 없다', () => {
    const html = renderToString(<WorkProgress workId="work-a" episodes={episodes} />);
    expect(html).toContain('첫 화 보기');
    expect(html).toContain('첫 만남');
    expect(html).toContain('data-floating-reading-cta');
    expect(html).not.toContain('읽은 진행도');
    expect(html).not.toContain('다음 화 보기');
  });

  it('비로그인은 API 요청 없이 첫 화 CTA를 유지한다', async () => {
    isLoggedIn.mockReturnValue(false);
    await renderProgress();

    expect(getWorkProgress).not.toHaveBeenCalled();
    expect(container.querySelector('[data-floating-reading-cta]')?.className).toContain('fixed');
    expect(container.textContent).toContain('첫 화 보기');
    expect(container.textContent).toContain('첫 만남');
  });

  it('stale login_hint의 401 결과는 공개 첫 화 CTA로 폴백한다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue(null);
    await renderProgress();

    expect(getWorkProgress).toHaveBeenCalledWith('work-a');
    expect(container.textContent).toContain('첫 화 보기');
  });

  it('진행도 0건은 0% 바와 제목이 붙은 첫 화 CTA를 표시한다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue({ read_episode_ids: [], last_episode: null });
    await renderProgress();

    const bar = container.querySelector('[role="progressbar"]');
    expect(bar?.getAttribute('aria-valuenow')).toBe('0');
    expect(container.textContent).toContain('0/4화');
    expect(container.textContent).toContain('첫 화 보기');
    expect(container.textContent).toContain('첫 만남');
  });

  it('정상 응답은 clamp된 진행률과 다음 화 제목·링크를 표시한다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue({
      read_episode_ids: ['a', 'a', 'b', 'c', 'stale'],
      last_episode: { id: 'c', public_id: 87654321, title: '달빛 아래 재회' },
    });
    await renderProgress();

    expect(container.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe(
      '100',
    );
    expect(container.textContent).toContain('4/4화');
    expect(container.textContent).toContain('다음 화 보기');
    expect(container.textContent).toContain('새로운 아침');
    expect(container.querySelector('a')?.getAttribute('href')).toBe('/works/work-a/44444444');
  });

  it('unmount 뒤 늦은 응답은 상태를 갱신하지 않는다', async () => {
    isLoggedIn.mockReturnValue(true);
    let resolveRequest: (value: {
      read_episode_ids: string[];
      last_episode: null;
    }) => void = () => undefined;
    getWorkProgress.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );

    await renderProgress();
    await act(async () => root.unmount());
    await act(async () => resolveRequest({ read_episode_ids: ['a'], last_episode: null }));

    expect(container.innerHTML).toBe('');
    root = createRoot(container);
  });
});
