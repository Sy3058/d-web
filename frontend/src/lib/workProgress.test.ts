import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api';

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock('./api', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api')>();
  return { ...original, api: { ...original.api, get: apiGet } };
});

import { getWorkProgress, selectReadingCta, summarizeWorkProgress } from './workProgress';

describe('getWorkProgress', () => {
  beforeEach(() => {
    apiGet.mockReset();
  });

  it('작품 진행도 API 계약을 그대로 반환한다', async () => {
    const response = {
      read_episode_ids: ['episode-a'],
      last_episode: { id: 'episode-a', public_id: 12345678, title: '첫 번째 모험' },
    };
    apiGet.mockResolvedValue(response);

    await expect(getWorkProgress('work-a')).resolves.toEqual(response);
    expect(apiGet).toHaveBeenCalledWith('/works/work-a/progress');
  });

  it('stale login_hint의 401은 미렌더용 null로 바꾼다', async () => {
    apiGet.mockRejectedValue(new ApiError(401, 'unauthorized'));
    await expect(getWorkProgress('work-a')).resolves.toBeNull();
  });

  it('404와 5xx는 0% 성공 상태로 위장하지 않고 전파한다', async () => {
    const notFound = new ApiError(404, 'not found');
    apiGet.mockRejectedValue(notFound);
    await expect(getWorkProgress('work-a')).rejects.toBe(notFound);

    const serverError = new ApiError(500, 'error');
    apiGet.mockRejectedValue(serverError);
    await expect(getWorkProgress('work-a')).rejects.toBe(serverError);
  });
});

describe('summarizeWorkProgress', () => {
  it('읽은 회차 수와 반올림한 비율을 계산한다', () => {
    expect(summarizeWorkProgress(['a', 'b'], 3)).toEqual({ readCount: 2, percent: 67 });
  });

  it('중복·stale 응답을 제거하고 공개 SSR 회차 수로 clamp한다', () => {
    expect(summarizeWorkProgress(['a', 'a', 'b', 'c'], 2)).toEqual({
      readCount: 2,
      percent: 100,
    });
  });

  it('회차가 0개거나 잘못된 음수이면 0으로 방어한다', () => {
    expect(summarizeWorkProgress(['a'], 0)).toEqual({ readCount: 0, percent: 0 });
    expect(summarizeWorkProgress(['a'], -1)).toEqual({ readCount: 0, percent: 0 });
  });
});

describe('selectReadingCta', () => {
  const episodes = [
    { id: 'a', publicId: 11111111, title: '첫 만남' },
    { id: 'b', publicId: 22222222, title: '비 오는 날' },
    { id: 'c', publicId: 33333333, title: '다시 출발' },
  ];

  it('진행도가 없으면 첫 화를 고른다', () => {
    expect(selectReadingCta(episodes, null)).toEqual({
      label: '첫 화 보기',
      episode: episodes[0],
    });
  });

  it('마지막으로 읽은 회차 다음의 작가 지정 순서 회차를 고른다', () => {
    expect(
      selectReadingCta(episodes, { id: 'a', public_id: 11111111, title: '첫 만남' }),
    ).toEqual({ label: '다음 화 보기', episode: episodes[1] });
  });

  it('마지막 회차까지 읽었으면 마지막 화 다시 보기를 제공한다', () => {
    expect(
      selectReadingCta(episodes, { id: 'c', public_id: 33333333, title: '다시 출발' }),
    ).toEqual({ label: '마지막 화 다시 보기', episode: episodes[2] });
  });

  it('SSR 목록에 최근 회차가 없으면 개인 API의 회차로 이어 본다', () => {
    expect(
      selectReadingCta(episodes, { id: 'new', public_id: 99999999, title: '새 회차' }),
    ).toEqual({
      label: '이어 보기',
      episode: { id: 'new', publicId: 99999999, title: '새 회차' },
    });
  });

  it('공개 회차가 없으면 CTA를 만들지 않는다', () => {
    expect(selectReadingCta([], null)).toBeNull();
  });
});
