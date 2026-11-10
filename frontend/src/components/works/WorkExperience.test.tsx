// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getBrowserGuestWorkProgress, getWorkProgress, isLoggedIn } = vi.hoisted(() => ({
  getBrowserGuestWorkProgress: vi.fn(),
  getWorkProgress: vi.fn(),
  isLoggedIn: vi.fn(),
}));

vi.mock('../../lib/guestProgress', () => ({ getBrowserGuestWorkProgress }));

vi.mock('../../lib/workProgress', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/workProgress')>();
  return { ...original, getWorkProgress };
});

vi.mock('../../lib/viewer', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../lib/viewer')>();
  return { ...original, isLoggedIn };
});

import WorkExperience from './WorkExperience';

let container: HTMLDivElement;
let root: Root;

const episodes = [
  { id: 'a', public_id: 11111111, title: '첫 만남' },
  { id: 'b', public_id: 22222222, title: '비 오는 날' },
  { id: 'c', public_id: 33333333, title: '달빛 아래 재회' },
  { id: 'd', public_id: 44444444, title: '새로운 아침' },
].map((episode) => ({ ...episode, subtitle: '부제', thumbnail_url: null, is_free: episode.id === 'a', is_locked: episode.id !== 'a', is_purchased: true, price: 500, first_published_at: '2026-01-01T00:00:00Z' }));

async function renderProgress() {
  await act(async () => {
    root.render(<WorkExperience order="asc" pathname="/works/work-a" workId="work-a" episodes={episodes} />);
  });
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  getWorkProgress.mockReset();
  getBrowserGuestWorkProgress.mockReset();
  isLoggedIn.mockReset();
  getBrowserGuestWorkProgress.mockReturnValue({ readEpisodeIds: [], lastEpisodeId: null });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

describe('WorkExperience', () => {
  it('서버 초기 HTML에는 공개 첫 화 CTA만 있고 개인 진행도는 없다', () => {
    const html = renderToString(<WorkExperience order="asc" pathname="/works/work-a" workId="work-a" episodes={episodes} />);
    expect(html).toContain('첫 화 보기');
    expect(html).toContain('첫 만남');
    expect(html).toContain('data-floating-reading-cta');
    expect(html).not.toContain('읽은 진행도');
    expect(html).not.toContain('다음 화 보기');
    expect(getBrowserGuestWorkProgress).not.toHaveBeenCalled();
    expect(getWorkProgress).not.toHaveBeenCalled();
    expect(html).toContain('잠금');
    expect(html).not.toContain('구매완료');
  });

  it('공개 HTML hydration 뒤 구매 배지를 한 요청으로 갱신한다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue({ read_episode_ids: [], purchased_episode_ids: ['b'], last_episode: null });
    await act(async () => root.unmount());
    container.innerHTML = renderToString(<WorkExperience workId="work-a" episodes={episodes} order="asc" pathname="/works/work-a" />);
    expect(container.textContent).not.toContain('구매완료');
    expect(getWorkProgress).not.toHaveBeenCalled();
    await act(async () => {
      root = hydrateRoot(container, <WorkExperience workId="work-a" episodes={episodes} order="asc" pathname="/works/work-a" />);
    });
    expect(container.querySelector('[data-episode-id="b"]')?.textContent).toContain('구매완료');
    expect(getWorkProgress).toHaveBeenCalledTimes(1);
  });

  it('비로그인은 API 요청 없이 로컬 0% 진행도와 첫 화 CTA를 표시한다', async () => {
    isLoggedIn.mockReturnValue(false);
    await renderProgress();

    expect(getWorkProgress).not.toHaveBeenCalled();
    expect(getBrowserGuestWorkProgress).toHaveBeenCalledWith(['a', 'b', 'c', 'd']);
    expect(container.querySelector('[data-floating-reading-cta]')?.className).toContain('fixed');
    expect(container.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe(
      '0',
    );
    expect(container.textContent).toContain('첫 화 보기');
    expect(container.textContent).toContain('첫 만남');
  });

  it('비로그인은 가장 최근에 연 공개 회차 자체로 이어 본다', async () => {
    isLoggedIn.mockReturnValue(false);
    getBrowserGuestWorkProgress.mockReturnValue({
      readEpisodeIds: ['a', 'b'],
      lastEpisodeId: 'b',
    });

    await renderProgress();

    expect(container.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe(
      '50',
    );
    expect(container.textContent).toContain('2/4화');
    expect(container.textContent).toContain('이어 보기');
    expect(container.textContent).toContain('비 오는 날');
    expect(container.querySelector('[data-floating-reading-cta] a')?.getAttribute('href')).toBe('/works/work-a/22222222');
  });

  it('stale login_hint의 401 결과는 공개 첫 화 CTA로 폴백한다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue(null);
    await renderProgress();

    expect(getWorkProgress).toHaveBeenCalledWith('work-a');
    expect(getBrowserGuestWorkProgress).not.toHaveBeenCalled();
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
    expect(container.querySelector('[data-floating-reading-cta] a')?.getAttribute('href')).toBe('/works/work-a/44444444');
  });

  it('읽기 이력 없는 구매도 한 번의 요청으로 표시하고 잠금과 가격을 없앤다', async () => {
    isLoggedIn.mockReturnValue(true);
    getWorkProgress.mockResolvedValue({ read_episode_ids: [], purchased_episode_ids: ['b', 'a'], last_episode: null });
    await renderProgress();
    const purchased = container.querySelector('[data-episode-id="b"]');
    expect(purchased?.textContent).toContain('구매완료');
    expect(purchased?.textContent).not.toContain('잠금');
    expect(purchased?.textContent).not.toContain('500');
    expect(container.querySelector('[data-episode-id="a"]')?.textContent).toContain('구매완료');
    expect(container.querySelector('[data-episode-id="c"]')?.textContent).toContain('잠금');
    expect(getWorkProgress).toHaveBeenCalledTimes(1);
  });

  it('로컬 구매 위조는 무료·잠금 배지에 영향을 주지 않는다', async () => {
    isLoggedIn.mockReturnValue(false);
    getBrowserGuestWorkProgress.mockReturnValue({ readEpisodeIds: ['b'], lastEpisodeId: 'b', purchased_episode_ids: ['b'] });
    await renderProgress();
    expect(container.textContent).not.toContain('구매완료');
    expect(container.querySelector('[data-episode-id="a"]')?.textContent).toContain('무료');
    expect(container.querySelector('[data-episode-id="b"]')?.textContent).toContain('잠금');
  });

  it.each([null, new Error('503')])('인증 만료와 서버 오류는 구매 표시 없이 공개 목록을 유지한다: %s', async (result) => {
    isLoggedIn.mockReturnValue(true);
    if (result instanceof Error) getWorkProgress.mockRejectedValue(result);
    else getWorkProgress.mockResolvedValue(result);
    await renderProgress();
    expect(container.textContent).not.toContain('구매완료');
    expect(container.querySelector('[data-episode-id="b"]')?.textContent).toContain('잠금');
  });

  it('최신순 목록도 작가 순서의 첫 화 CTA를 유지한다', async () => {
    isLoggedIn.mockReturnValue(false);
    await act(async () => root.render(<WorkExperience workId="work-a" episodes={episodes} order="desc" pathname="/works/work-a" />));
    expect(container.querySelector('[data-episode-id]')?.getAttribute('data-episode-id')).toBe('d');
    expect(container.querySelector('[data-floating-reading-cta] a')?.getAttribute('href')).toBe('/works/work-a/11111111');
  });

  it('작품 전환 시 기존 배지를 즉시 지우고 늦은 이전 응답을 무시한다', async () => {
    isLoggedIn.mockReturnValue(true);
    let resolveOld: (value: unknown) => void = () => undefined;
    getWorkProgress.mockReturnValueOnce(new Promise((resolve) => { resolveOld = resolve; }));
    getWorkProgress.mockResolvedValueOnce({ read_episode_ids: [], purchased_episode_ids: ['b'], last_episode: null });
    await renderProgress();
    await act(async () => root.render(<WorkExperience workId="work-b" episodes={episodes} order="asc" pathname="/works/work-b" />));
    expect(container.querySelector('[data-episode-id="b"]')?.textContent).toContain('구매완료');
    await act(async () => resolveOld({ read_episode_ids: [], purchased_episode_ids: ['c'], last_episode: null }));
    expect(container.querySelector('[data-episode-id="c"]')?.textContent).toContain('잠금');
    getWorkProgress.mockReturnValueOnce(new Promise(() => undefined));
    await act(async () => root.render(<WorkExperience workId="work-c" episodes={episodes} order="asc" pathname="/works/work-c" />));
    expect(container.textContent).not.toContain('구매완료');
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
