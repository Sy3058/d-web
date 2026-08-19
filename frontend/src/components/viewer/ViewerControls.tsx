import { useState } from 'react';

export interface ViewerEpisodeLink {
  publicId: number;
  title: string;
}

interface Props {
  visible: boolean;
  workId: string;
  workTitle: string;
  episodeTitle: string;
  episodeSubtitle: string | null;
  previousEpisode: ViewerEpisodeLink | null;
  nextEpisode: ViewerEpisodeLink | null;
}

type ShareStatus = 'idle' | 'shared' | 'copied' | 'error';

const iconButtonClass =
  'size-11 shrink-0 inline-flex items-center justify-center rounded-control text-ink hover:bg-hover disabled:text-muted disabled:opacity-50 disabled:pointer-events-none';

function ArrowLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
      <path d="M15 5 8 12l7 7" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5" aria-hidden="true">
      <path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function EpisodeNavigation({
  direction,
  episode,
  workId,
}: {
  direction: 'previous' | 'next';
  episode: ViewerEpisodeLink | null;
  workId: string;
}) {
  const previous = direction === 'previous';
  const label = episode
    ? `${previous ? '이전 화' : '다음 화'}: ${episode.title}`
    : `${previous ? '이전 화' : '다음 화'} 없음`;
  const icon = previous ? <ArrowLeftIcon /> : <ArrowRightIcon />;

  if (!episode) {
    return (
      <button type="button" className={iconButtonClass} aria-label={label} aria-disabled="true" disabled>
        {icon}
      </button>
    );
  }

  return (
    <a
      href={`/works/${workId}/${episode.publicId}`}
      className={iconButtonClass}
      aria-label={label}
      title={episode.title}
      data-astro-reload
    >
      {icon}
    </a>
  );
}

export default function ViewerControls({
  visible,
  workId,
  workTitle,
  episodeTitle,
  episodeSubtitle,
  previousEpisode,
  nextEpisode,
}: Props) {
  const [shareStatus, setShareStatus] = useState<ShareStatus>('idle');
  const episodeDisplayTitle = episodeSubtitle
    ? `${episodeTitle} · ${episodeSubtitle}`
    : episodeTitle;
  const visibilityClass = visible
    ? 'translate-y-0 opacity-100'
    : 'pointer-events-none opacity-0';

  async function handleShare() {
    const url = window.location.href;
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: `${episodeTitle} · ${workTitle}`, url });
        setShareStatus('shared');
        return;
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
      }
    }

    try {
      if (typeof navigator.clipboard?.writeText === 'function') {
        await navigator.clipboard.writeText(url);
        setShareStatus('copied');
        return;
      }
      setShareStatus('error');
    } catch {
      setShareStatus('error');
    }
  }

  const shareMessage =
    shareStatus === 'shared'
      ? '공유 창을 열었어요.'
      : shareStatus === 'copied'
        ? '주소를 복사했어요.'
        : shareStatus === 'error'
          ? '공유하지 못했어요.'
          : '';

  return (
    <>
      <header
        data-viewer-top-controls
        data-visible={visible ? 'true' : 'false'}
        aria-hidden={!visible}
        inert={!visible}
        className={`fixed inset-x-0 top-0 z-50 border-b border-line bg-paper/95 transition-[transform,opacity] duration-200 motion-reduce:transition-none ${visibilityClass} ${visible ? '' : '-translate-y-full'}`}
        style={{ paddingTop: 'env(safe-area-inset-top)' }}
      >
        <div className="mx-auto flex h-14 max-w-[720px] items-center gap-2 px-3 sm:px-4">
          <a
            href={`/works/${workId}`}
            className={iconButtonClass}
            aria-label={`${workTitle} 작품 상세로 이동`}
          >
            <ArrowLeftIcon />
          </a>
          <div className="min-w-0 flex-1 text-center">
            <p className="truncate text-xs text-muted">{workTitle}</p>
            <p
              data-viewer-episode-title
              className="truncate text-sm font-medium text-ink"
              title={episodeDisplayTitle}
            >
              {episodeTitle}
              {episodeSubtitle && <span className="font-normal text-muted"> · {episodeSubtitle}</span>}
            </p>
          </div>
          <button
            type="button"
            className={`${iconButtonClass} text-xs font-medium`}
            aria-label="현재 회차 공유"
            onClick={() => void handleShare()}
          >
            공유
          </button>
          <a
            href={`/works/${workId}#episodes`}
            className={`${iconButtonClass} text-xs font-medium`}
            aria-label={`${workTitle} 전체 회차 목록으로 이동`}
          >
            목록
          </a>
        </div>
        <p className="sr-only" role="status" aria-live="polite">
          {shareMessage}
        </p>
      </header>

      <nav
        data-viewer-bottom-controls
        data-visible={visible ? 'true' : 'false'}
        aria-label="회차 이동"
        aria-hidden={!visible}
        inert={!visible}
        className={`fixed left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-control border border-line bg-paper/95 px-2 py-1.5 transition-[transform,opacity] duration-200 motion-reduce:transition-none ${visibilityClass} ${visible ? '' : 'translate-y-[calc(100%+2rem)]'}`}
        style={{ bottom: 'calc(1rem + env(safe-area-inset-bottom))' }}
      >
        <EpisodeNavigation direction="previous" episode={previousEpisode} workId={workId} />
        <span className="h-5 w-px bg-line" aria-hidden="true" />
        <EpisodeNavigation direction="next" episode={nextEpisode} workId={workId} />
      </nav>
    </>
  );
}
