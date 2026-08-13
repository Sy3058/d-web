import { beforeEach, describe, expect, it, vi } from 'vitest';
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }));

vi.mock('./api', () => ({
  api: { get: apiGet },
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

import {
  commissionAvailability,
  getCommissionItems,
  getSiteText,
  isNotFoundError,
  resolveOptionalSiteText,
  selectLandingCommissions,
  splitLandingWorks,
  type PublicCommissionItem,
} from './commission';

const item = (id: string, isOpen: boolean): PublicCommissionItem => ({
  id,
  title: `커미션 ${id}`,
  description: null,
  price_text: '50,000원~',
  duration_text: null,
  sample_image_urls: [],
  is_open: isOpen,
});

describe('공개 커미션 API', () => {
  beforeEach(() => apiGet.mockReset());

  it('서버가 정렬한 카드 배열을 그대로 반환한다', async () => {
    const response = [item('second', false), item('first', true)];
    apiGet.mockResolvedValue(response);

    await expect(getCommissionItems()).resolves.toEqual(response);
    expect(apiGet).toHaveBeenCalledWith('/commission-items');
  });

  it('사이트 문구 슬롯을 지정한 경로에서 읽는다', async () => {
    const response = { key: 'landing_intro', body: '소개', updated_at: null };
    apiGet.mockResolvedValue(response);

    await expect(getSiteText('landing_intro')).resolves.toEqual(response);
    expect(apiGet).toHaveBeenCalledWith('/site-texts/landing_intro');
  });

  it('미저장 문구의 404만 정상 빈 상태로 변환한다', async () => {
    expect(isNotFoundError({ status: 404 })).toBe(true);
    await expect(resolveOptionalSiteText(() => Promise.reject({ status: 404 }))).resolves.toBeNull();
  });

  it('5xx와 네트워크 오류를 빈 문구로 숨기지 않는다', async () => {
    const serverError = { status: 500 };
    const networkError = new TypeError('network');

    expect(isNotFoundError(serverError)).toBe(false);
    expect(isNotFoundError(networkError)).toBe(false);
    await expect(resolveOptionalSiteText(() => Promise.reject(serverError))).rejects.toBe(serverError);
    await expect(resolveOptionalSiteText(() => Promise.reject(networkError))).rejects.toBe(networkError);
  });
});

describe('랜딩 작품 분기', () => {
  const work = (id: string) => ({ id }) as never;

  it('0개면 최근 작품이 없다', () => {
    expect(splitLandingWorks([])).toEqual({ recent: null, others: [] });
  });

  it('서버 등록 최신순의 첫 작품과 나머지를 분리하고 원본 순서를 보존한다', () => {
    expect(splitLandingWorks([work('recent'), work('older'), work('oldest')])).toEqual({
      recent: { id: 'recent' },
      others: [{ id: 'older' }, { id: 'oldest' }],
    });
  });
});

describe('커미션 모집 상태', () => {
  it('카드 없음과 전부 마감과 모집 중을 구분한다', () => {
    expect(commissionAvailability([])).toBe('empty');
    expect(commissionAvailability([item('a', false), item('b', false)])).toBe('closed');
    expect(commissionAvailability([item('a', false), item('b', true)])).toBe('open');
  });
});

describe('랜딩 커미션 미리보기', () => {
  it('서버 정렬을 보존하며 앞의 4개만 노출한다', () => {
    const items = ['a', 'b', 'c', 'd', 'e'].map((id) => item(id, true));

    expect(selectLandingCommissions(items).map(({ id }) => id)).toEqual(['a', 'b', 'c', 'd']);
    expect(items.map(({ id }) => id)).toEqual(['a', 'b', 'c', 'd', 'e']);
  });
});
