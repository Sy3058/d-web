import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet, apiPut } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }));

vi.mock('./api', async (importOriginal) => {
  const original = await importOriginal<typeof import('./api')>();
  return { ...original, api: { ...original.api, get: apiGet, put: apiPut } };
});

import { ApiError } from './api';
import {
  calculateBlockOffsetBp,
  calculateBlockRestoreY,
  clampBlockIndex,
  getEpisodeContent,
  imageFetchPriority,
  isLoggedIn,
  putProgress,
} from './viewer';

beforeEach(() => {
  apiGet.mockReset();
  apiPut.mockReset();
});

describe('getEpisodeContent', () => {
  it('404는 회차 없음 정상 흐름인 null로 변환한다', async () => {
    apiGet.mockRejectedValue(new ApiError(404, 'not found'));

    await expect(getEpisodeContent('episode-a')).resolves.toBeNull();
  });

  it('5xx와 네트워크 오류는 성공 상태로 숨기지 않고 전파한다', async () => {
    const serverError = new ApiError(500, 'server error');
    apiGet.mockRejectedValueOnce(serverError);

    await expect(getEpisodeContent('episode-a')).rejects.toBe(serverError);

    const networkError = new Error('network error');
    apiGet.mockRejectedValueOnce(networkError);

    await expect(getEpisodeContent('episode-a')).rejects.toBe(networkError);
  });
});

describe('putProgress', () => {
  it('블록 인덱스와 내부 오프셋을 함께 전송한다', async () => {
    apiPut.mockResolvedValue(undefined);

    await putProgress('episode-a', 3, 6_250);

    expect(apiPut).toHaveBeenCalledWith('/episodes/episode-a/progress', {
      page_no: 3,
      block_offset_bp: 6_250,
    });
  });
});

describe('imageFetchPriority', () => {
  it('앞 3장(0,1,2번째 이미지)은 high', () => {
    expect(imageFetchPriority(0)).toBe('high');
    expect(imageFetchPriority(1)).toBe('high');
    expect(imageFetchPriority(2)).toBe('high');
  });

  it('4번째 이미지부터는 low', () => {
    expect(imageFetchPriority(3)).toBe('low');
    expect(imageFetchPriority(10)).toBe('low');
  });
});

describe('clampBlockIndex', () => {
  it('범위 안이면 그대로 반환한다', () => {
    expect(clampBlockIndex(3, 10)).toBe(3);
  });

  it('음수는 0으로 자른다', () => {
    expect(clampBlockIndex(-5, 10)).toBe(0);
  });

  it('블록 수를 넘으면 마지막 인덱스로 자른다(본문 축소 후 stale page_no)', () => {
    expect(clampBlockIndex(99, 10)).toBe(9);
  });

  it('블록이 0개면 0을 반환한다(빈 문서 방어)', () => {
    expect(clampBlockIndex(5, 0)).toBe(0);
  });
});

describe('block-local progress', () => {
  it('5400px 긴 이미지 내부 위치를 basis point로 계산한다', () => {
    expect(calculateBlockOffsetBp(-3240, 5400)).toBe(6000);
  });

  it('블록 앞과 뒤의 위치를 유효 범위로 자른다', () => {
    expect(calculateBlockOffsetBp(100, 5400)).toBe(0);
    expect(calculateBlockOffsetBp(-6000, 5400)).toBe(10_000);
    expect(calculateBlockOffsetBp(-100, 0)).toBe(0);
  });

  it('현재 렌더 높이에 같은 상대 위치를 복원한다', () => {
    expect(calculateBlockRestoreY(1000, 5400, 6000)).toBe(4240);
    expect(calculateBlockRestoreY(1000, 5400, -1)).toBe(1000);
    expect(calculateBlockRestoreY(1000, 5400, 20_000)).toBe(6400);
  });
});

describe('isLoggedIn', () => {
  it('login_hint 쿠키가 있으면 true', () => {
    expect(isLoggedIn('login_hint=%EB%8F%84%EA%B5%B0')).toBe(true);
  });

  it('다른 쿠키들 사이에 섞여 있어도 찾는다', () => {
    expect(isLoggedIn('theme=dark; login_hint=abc; foo=bar')).toBe(true);
  });

  it('없으면 false', () => {
    expect(isLoggedIn('theme=dark; foo=bar')).toBe(false);
  });

  it('빈 문자열이면 false', () => {
    expect(isLoggedIn('')).toBe(false);
  });
});
