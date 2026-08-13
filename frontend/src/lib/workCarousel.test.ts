import { describe, expect, it } from 'vitest';
import {
  getCarouselSlides,
  getCarouselTransitionSlides,
  wrapCarouselIndex,
} from './workCarousel';

describe('작품 캐러셀 인덱스', () => {
  it('마지막 다음은 첫 작품, 첫 작품 이전은 마지막 작품으로 순환한다', () => {
    expect(wrapCarouselIndex(3, 3)).toBe(0);
    expect(wrapCarouselIndex(-1, 3)).toBe(2);
  });

  it('작품이 없으면 슬라이드가 없다', () => {
    expect(getCarouselSlides(0, 0)).toEqual([]);
  });

  it('작품 하나는 중앙에만 표시한다', () => {
    expect(getCarouselSlides(0, 1)).toEqual([{ index: 0, offset: 0 }]);
  });

  it('작품 둘은 같은 주변 작품을 양쪽에 중복하지 않는다', () => {
    expect(getCarouselSlides(0, 2)).toEqual([
      { index: 0, offset: 0 },
      { index: 1, offset: 1 },
    ]);
    expect(getCarouselSlides(1, 2)).toEqual([
      { index: 0, offset: -1 },
      { index: 1, offset: 0 },
    ]);
  });

  it('작품 셋은 모바일에서도 보이는 중앙과 양옆을 배치한다', () => {
    expect(getCarouselSlides(0, 3)).toEqual([
      { index: 2, offset: -1 },
      { index: 0, offset: 0 },
      { index: 1, offset: 1 },
    ]);
  });

  it('작품 다섯 개 이상은 현재 작품을 중심으로 최대 다섯 개를 순환 배치한다', () => {
    expect(getCarouselSlides(0, 6)).toEqual([
      { index: 4, offset: -2 },
      { index: 5, offset: -1 },
      { index: 0, offset: 0 },
      { index: 1, offset: 1 },
      { index: 2, offset: 2 },
    ]);
  });

  it('다음 이동은 오른쪽 숨은 카드를 들이고 기존 카드를 모두 왼쪽으로 옮긴다', () => {
    expect(getCarouselTransitionSlides(0, 6, 1)).toEqual([
      { index: 4, offset: -2, targetOffset: -3 },
      { index: 5, offset: -1, targetOffset: -2 },
      { index: 0, offset: 0, targetOffset: -1 },
      { index: 1, offset: 1, targetOffset: 0 },
      { index: 2, offset: 2, targetOffset: 1 },
      { index: 3, offset: 3, targetOffset: 2 },
    ]);
  });

  it('작품 셋의 순환은 같은 카드를 반대편으로 날리지 않고 숨은 복제본을 진입시킨다', () => {
    expect(getCarouselTransitionSlides(0, 3, 1)).toEqual([
      { index: 2, offset: -1, targetOffset: -2 },
      { index: 0, offset: 0, targetOffset: -1 },
      { index: 1, offset: 1, targetOffset: 0 },
      { index: 2, offset: 2, targetOffset: 1 },
    ]);
  });

  it('이전 이동은 왼쪽 숨은 카드를 들이고 기존 카드를 모두 오른쪽으로 옮긴다', () => {
    expect(getCarouselTransitionSlides(0, 4, -1)).toEqual([
      { index: 3, offset: -1, targetOffset: 0 },
      { index: 0, offset: 0, targetOffset: 1 },
      { index: 1, offset: 1, targetOffset: 2 },
      { index: 2, offset: 2, targetOffset: 3 },
      { index: 2, offset: -2, targetOffset: -1 },
    ]);
  });
});
