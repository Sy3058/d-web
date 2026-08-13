import { useEffect, useState, type KeyboardEvent } from 'react';
import { statusLabel, type WorkListItem } from '../../lib/catalog';
import {
  getCarouselTransitionSlides,
  wrapCarouselIndex,
  type CarouselDirection,
  type CarouselOffset,
} from '../../lib/workCarousel';

interface Props {
  works: WorkListItem[];
}

function Cover({ work, active }: { work: WorkListItem; active: boolean }) {
  return (
    <div className="relative aspect-[3/4] w-full overflow-hidden rounded-surface bg-hover shadow-sm">
      {work.cover_image_url && (
        <img
          src={work.cover_image_url}
          alt=""
          loading={active ? 'eager' : 'lazy'}
          className="h-full w-full object-cover"
          onError={(event) => {
            event.currentTarget.hidden = true;
            event.currentTarget.nextElementSibling?.removeAttribute('hidden');
          }}
        />
      )}
      <div
        className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-muted"
        hidden={!!work.cover_image_url}
      >
        표지 준비 중
      </div>
    </div>
  );
}

export default function WorkCarousel({ works }: Props) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [direction, setDirection] = useState<CarouselDirection | null>(null);
  const [isMoving, setIsMoving] = useState(false);
  const slides = getCarouselTransitionSlides(activeIndex, works.length, direction);

  useEffect(() => {
    if (direction === null) return;
    const frame = requestAnimationFrame(() => setIsMoving(true));
    return () => cancelAnimationFrame(frame);
  }, [direction]);

  useEffect(() => {
    if (!isMoving || direction === null) return;
    const timer = window.setTimeout(() => {
      setActiveIndex((current) => wrapCarouselIndex(current + direction, works.length));
      setIsMoving(false);
      setDirection(null);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [direction, isMoving, works.length]);

  if (slides.length === 0) return null;

  const current = wrapCarouselIndex(activeIndex, works.length);
  const activeWork = works[current];
  const hasMultiple = works.length > 1;

  function move(delta: number) {
    if (direction !== null || works.length <= 1) return;
    if (works.length === 2) {
      setActiveIndex((current) => wrapCarouselIndex(current + delta, works.length));
      return;
    }
    setDirection(delta < 0 ? -1 : 1);
  }

  function select(index: number) {
    if (direction !== null) return;
    setActiveIndex(index);
  }

  const slideClass: Record<CarouselOffset, string> = {
    [-3]: 'pointer-events-none hidden opacity-0 sm:block sm:w-[120px]',
    [-2]: 'pointer-events-none hidden sm:block sm:z-0 sm:w-[150px] sm:opacity-20',
    [-1]: 'z-[1] w-[96px] opacity-35 min-[380px]:w-[128px] sm:w-[190px] sm:opacity-45',
    [0]: 'z-10 w-[170px] min-[380px]:w-[190px] sm:w-[270px]',
    [1]: 'z-[1] w-[96px] opacity-35 min-[380px]:w-[128px] sm:w-[190px] sm:opacity-45',
    [2]: 'pointer-events-none hidden sm:block sm:z-0 sm:w-[150px] sm:opacity-20',
    [3]: 'pointer-events-none hidden opacity-0 sm:block sm:w-[120px]',
  };

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      move(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      move(1);
    }
  }

  return (
    <section
      aria-label="작품 캐러셀"
      aria-roledescription="carousel"
      className="work-carousel outline-none"
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <div className="relative mx-auto h-[270px] max-w-[1140px] overflow-hidden sm:h-[380px]">
        {slides.map((slide) => {
          const work = works[slide.index];
          const renderedOffset = isMoving ? slide.targetOffset : slide.offset;
          const sharedClass = `work-carousel-slide absolute ${isMoving ? 'transition-[transform,width,opacity] duration-300 motion-reduce:transition-none' : ''} ${slideClass[renderedOffset]} ${renderedOffset === 0 ? '' : 'hover:opacity-60'}`;
          return (
            <div
              key={`${work.id}:${slide.offset}`}
              data-offset={renderedOffset}
              className={sharedClass}
              aria-hidden={Math.abs(renderedOffset) >= 2 ? 'true' : undefined}
            >
              {renderedOffset === 0 ? (
                <a
                  href={`/works/${work.id}`}
                  aria-label={`${work.title} 상세 보기`}
                  className="block"
                >
                  <Cover work={work} active />
                </a>
              ) : (
                <button
                  type="button"
                  aria-label={`${work.title} 작품 보기`}
                  className="block w-full"
                  tabIndex={Math.abs(renderedOffset) === 1 ? 0 : -1}
                  onClick={() => move(renderedOffset < 0 ? -1 : 1)}
                >
                  <Cover work={work} active={false} />
                </button>
              )}
            </div>
          );
        })}

        {hasMultiple && (
          <>
            <button
              type="button"
              aria-label="이전 작품"
              className="absolute left-2 top-1/2 z-20 flex size-10 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-paper/90 text-xl text-ink shadow-sm hover:bg-hover sm:left-0"
              onClick={() => move(-1)}
            >
              <span aria-hidden="true">‹</span>
            </button>
            <button
              type="button"
              aria-label="다음 작품"
              className="absolute right-2 top-1/2 z-20 flex size-10 -translate-y-1/2 items-center justify-center rounded-full border border-line bg-paper/90 text-xl text-ink shadow-sm hover:bg-hover sm:right-0"
              onClick={() => move(1)}
            >
              <span aria-hidden="true">›</span>
            </button>
          </>
        )}
      </div>

      <div className="mx-auto mt-3 max-w-[520px] text-center" aria-live="polite">
        <div className="flex items-center justify-center gap-3">
          <h2 className="text-headline-md text-ink">{activeWork.title}</h2>
          <span className="shrink-0 text-label-md text-muted">
            {statusLabel(activeWork.status)}
          </span>
        </div>
        {activeWork.tags.length > 0 && (
          <p className="mt-2 text-sm text-muted">
            {activeWork.tags.map(({ name }) => `#${name}`).join(' ')}
          </p>
        )}
        <a
          href={`/works/${activeWork.id}`}
          className="mt-5 inline-flex items-center justify-center rounded-control bg-ink-strong px-4 py-2.5 text-sm font-medium text-paper transition-colors hover:bg-ink"
        >
          작품 보러 가기
        </a>
        <div className="mt-4 flex justify-center">
          <div className="flex max-w-full gap-2 overflow-x-auto px-1 py-1" aria-label="작품 위치">
            {works.map((work, index) => (
              <button
                key={work.id}
                type="button"
                aria-label={`${index + 1}번째 작품 ${work.title} 보기`}
                aria-current={index === current ? 'true' : undefined}
                className={`size-2.5 shrink-0 rounded-full transition-colors ${
                  index === current ? 'bg-ink-strong' : 'bg-line hover:bg-muted'
                }`}
                onClick={() => select(index)}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
