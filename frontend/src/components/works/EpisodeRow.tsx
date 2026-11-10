import { useEffect, useRef, useState } from 'react';
import { formatEpisodeDate, formatPrice, type EpisodeSummary } from '../../lib/catalog';

interface Props {
  workId: string;
  episode: EpisodeSummary;
  first?: boolean;
  purchased: boolean;
}

export default function EpisodeRow({ workId, episode, first = false, purchased }: Props) {
  const [failedThumbnail, setFailedThumbnail] = useState<string | null>(null);
  const thumbnailRef = useRef<HTMLImageElement>(null);
  const thumbnailUrl = episode.thumbnail_url;
  useEffect(() => {
    const image = thumbnailRef.current;
    if (thumbnailUrl && image?.getAttribute('src') === thumbnailUrl && image.complete && image.naturalWidth === 0) {
      // hydration 이전에 끝난 실패는 onError가 받지 못하므로 DOM의 완료 상태로 복구한다.
      setFailedThumbnail(thumbnailUrl);
    }
  }, [thumbnailUrl]);
  const displayDate = formatEpisodeDate(episode.first_published_at);
  const badgeClass = 'inline-flex items-center gap-1 text-label-md rounded-pill px-2.5 py-0.5';
  return (
    <a
      href={`/works/${workId}/${episode.public_id}`}
      data-episode-id={episode.id}
      className={`flex items-center gap-4 py-4 hover:bg-hover -mx-4 px-4${first ? '' : ' border-t border-line'}`}
    >
      <div className="h-16 w-16 shrink-0 overflow-hidden rounded-control bg-hover">
        {episode.thumbnail_url && failedThumbnail !== episode.thumbnail_url && (
          <img key={thumbnailUrl} ref={thumbnailRef} src={episode.thumbnail_url} alt="" loading="lazy" className="h-full w-full object-cover" onError={(event) => {
            if (event.currentTarget === thumbnailRef.current && event.currentTarget.getAttribute('src') === thumbnailUrl) {
              setFailedThumbnail(thumbnailUrl);
            }
          }} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><span className="text-body-md text-ink truncate">{episode.title}</span></div>
        {episode.subtitle && <p className="text-sm text-muted truncate">{episode.subtitle}</p>}
        {displayDate && <time dateTime={episode.first_published_at ?? undefined} className="text-xs text-muted">{displayDate}</time>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {purchased ? <span className={`${badgeClass} border border-ink-strong text-ink-strong`}>구매완료</span> : episode.is_free ? (
          <span className={`${badgeClass} border border-ink-strong text-ink-strong`}>무료</span>
        ) : (
          <><span className={`${badgeClass} bg-hover text-muted`}>잠금</span><span className="text-label-md text-ink tabular-nums">{formatPrice(episode.price)}</span></>
        )}
      </div>
    </a>
  );
}
