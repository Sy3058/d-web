import { describe, expect, it } from 'vitest';
import {
  buildWorksUrl,
  formatEpisodeDate,
  formatPrice,
  orderEpisodes,
  parseOrder,
  totalPages,
} from './catalog';

describe('totalPages', () => {
  it('빈 목록(total=0)이면 1페이지로 취급한다', () => {
    expect(totalPages(0, 24)).toBe(1);
  });

  it('나누어 떨어지면 정확히 그 몫이 된다', () => {
    expect(totalPages(48, 24)).toBe(2);
  });

  it('나누어 떨어지지 않으면 올림한다', () => {
    expect(totalPages(25, 24)).toBe(2);
  });

  it('size가 0 이하이면 방어적으로 1을 반환한다', () => {
    expect(totalPages(100, 0)).toBe(1);
  });
});

describe('buildWorksUrl', () => {
  it('파라미터가 없으면 기본 목록 경로만 반환한다', () => {
    expect(buildWorksUrl({})).toBe('/works');
  });

  it('page=1은 기본값이라 쿼리에서 생략한다', () => {
    expect(buildWorksUrl({ page: 1 })).toBe('/works');
  });

  it('page=2 이상은 쿼리에 싣는다', () => {
    expect(buildWorksUrl({ page: 2 })).toBe('/works?page=2');
  });

  it('태그는 URL 인코딩된다(한글 포함)', () => {
    expect(buildWorksUrl({ tag: '판타지' })).toBe(`/works?tag=${encodeURIComponent('판타지')}`);
  });

  it('page와 tag를 함께 실을 수 있다', () => {
    expect(buildWorksUrl({ page: 3, tag: '로맨스' })).toBe(
      `/works?page=3&tag=${encodeURIComponent('로맨스')}`,
    );
  });
});

describe('formatEpisodeDate', () => {
  it('null이면 null을 반환한다(예약만 걸리고 미공개)', () => {
    expect(formatEpisodeDate(null)).toBeNull();
  });

  it('UTC와 KST가 같은 날이면 그대로 표기한다', () => {
    expect(formatEpisodeDate('2026-08-04T05:30:00+00:00')).toBe('2026.08.04');
  });

  it('UTC 자정 경계를 넘어 KST로는 다음 날인 경우 KST 날짜로 표기한다(타임존 미고려 시 08.04로 잘못 나옴)', () => {
    // UTC 15:00:00 + 9h = KST 00:00:00(다음 날 자정) - naive 구현이면 여전히 UTC 날짜(08-04)를 반환한다.
    expect(formatEpisodeDate('2026-08-04T15:00:00+00:00')).toBe('2026.08.05');
  });

  it('UTC 자정 직전(23:59:59)이 KST로는 이미 같은 날 낮인 경우를 정확히 구분한다', () => {
    expect(formatEpisodeDate('2026-08-03T23:59:59+00:00')).toBe('2026.08.04');
  });
});

describe('parseOrder', () => {
  it('asc는 그대로 asc로 파싱한다', () => {
    expect(parseOrder('asc')).toBe('asc');
  });

  it('null·오타·낡은 값은 전부 기본값 desc로 폴백한다(422 없음)', () => {
    expect(parseOrder(null)).toBe('desc');
    expect(parseOrder('DESC')).toBe('desc');
    expect(parseOrder('oldest')).toBe('desc');
  });
});

describe('orderEpisodes', () => {
  // 서버가 sort_order 오름차순으로 준 순서를 그대로 흉내낸 fixture. id가 생성 순서와도
  // 다르게 섞여 있어(프롤로그가 나중에 끼워진 상황을 흉내) "뒤집기가 실제로 일어났는지"를
  // 판별할 수 있다 - 시작 배열과 desc 기대값이 다르다.
  const episodes = [{ id: 'prologue' }, { id: 'ep1' }, { id: 'ep2' }];

  it('asc는 서버가 준 순서를 그대로 유지한다', () => {
    expect(orderEpisodes(episodes, 'asc').map((e) => e.id)).toEqual([
      'prologue',
      'ep1',
      'ep2',
    ]);
  });

  it('desc는 순서를 뒤집는다(시작 배열과 다른 순서라 판별력 있음)', () => {
    expect(orderEpisodes(episodes, 'desc').map((e) => e.id)).toEqual([
      'ep2',
      'ep1',
      'prologue',
    ]);
  });

  it('원본 배열을 변형하지 않는다("첫 화 보기"가 뒤집기 전 순서를 안전하게 참조해야 함)', () => {
    orderEpisodes(episodes, 'desc');
    expect(episodes.map((e) => e.id)).toEqual(['prologue', 'ep1', 'ep2']);
  });
});

describe('formatPrice', () => {
  it('null이면 무료로 표기한다', () => {
    expect(formatPrice(null)).toBe('무료');
  });

  it('0원은 무료와 구분해 0원으로 표기한다', () => {
    expect(formatPrice(0)).toBe('0원');
  });

  it('천 단위 구분자를 넣어 표기한다', () => {
    expect(formatPrice(3000)).toBe('3,000원');
  });
});
