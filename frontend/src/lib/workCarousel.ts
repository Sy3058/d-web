export interface CarouselSlide {
  index: number;
  offset: CarouselOffset;
}

export type CarouselOffset = -3 | -2 | -1 | 0 | 1 | 2 | 3;
export type CarouselDirection = -1 | 1;

export function wrapCarouselIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return ((index % length) + length) % length;
}

export function getCarouselSlides(activeIndex: number, length: number): CarouselSlide[] {
  if (length <= 0) return [];

  const current = wrapCarouselIndex(activeIndex, length);
  if (length === 1) return [{ index: current, offset: 0 }];
  if (length === 2) {
    return current === 0
      ? [
          { index: current, offset: 0 },
          { index: 1, offset: 1 },
        ]
      : [
          { index: 0, offset: -1 },
          { index: current, offset: 0 },
        ];
  }

  const offsets: CarouselSlide['offset'][] =
    length === 3 ? [-1, 0, 1] : length === 4 ? [-1, 0, 1, 2] : [-2, -1, 0, 1, 2];
  return offsets.map((offset) => ({
    index: wrapCarouselIndex(current + offset, length),
    offset,
  }));
}

export interface CarouselTransitionSlide extends CarouselSlide {
  targetOffset: CarouselOffset;
}

export function getCarouselTransitionSlides(
  activeIndex: number,
  length: number,
  direction: CarouselDirection | null,
): CarouselTransitionSlide[] {
  const stationary = getCarouselSlides(activeIndex, length);
  if (direction === null || length <= 2) {
    return stationary.map((slide) => ({ ...slide, targetOffset: slide.offset }));
  }

  const enteringOffset = (direction === 1
    ? Math.max(...stationary.map(({ offset }) => offset)) + 1
    : Math.min(...stationary.map(({ offset }) => offset)) - 1) as CarouselOffset;
  const enteringIndex = wrapCarouselIndex(activeIndex + enteringOffset, length);

  return [
    ...stationary.map((slide) => ({
      ...slide,
      targetOffset: (slide.offset - direction) as CarouselOffset,
    })),
    {
      index: enteringIndex,
      offset: enteringOffset,
      targetOffset: (enteringOffset - direction) as CarouselOffset,
    },
  ];
}
