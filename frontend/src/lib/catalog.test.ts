import { describe, expect, it } from 'vitest';
import { buildWorksUrl, formatPrice, totalPages } from './catalog';

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
