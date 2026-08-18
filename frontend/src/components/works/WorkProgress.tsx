import { useEffect, useState } from 'react';
import { getBrowserGuestWorkProgress } from '../../lib/guestProgress';
import { isLoggedIn } from '../../lib/viewer';
import {
  getWorkProgress,
  selectReadingCta,
  summarizeWorkProgress,
  type ProgressEpisode,
  type WorkProgressRead,
} from '../../lib/workProgress';

interface Props {
  workId: string;
  episodes: ProgressEpisode[];
}

type DisplayProgress = WorkProgressRead & { source: 'server' | 'guest' };

export default function WorkProgress({ workId, episodes }: Props) {
  // undefined는 hydration 전/로딩 중, null은 stale login_hint의 401이나 서버 오류로 공개
  // 첫 화 CTA만 유지하는 상태다. 비로그인은 hydration 뒤 로컬 진행도 객체로 전환한다.
  const [progress, setProgress] = useState<DisplayProgress | null | undefined>(undefined);

  useEffect(() => {
    if (!isLoggedIn(document.cookie)) {
      const local = getBrowserGuestWorkProgress(episodes.map((episode) => episode.id));
      const lastEpisode = episodes.find((episode) => episode.id === local.lastEpisodeId) ?? null;
      // localStorage는 hydration 뒤 effect에서만 읽는다. 공개 SSR에는 로컬 위치를 넣지 않는다.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProgress({
        source: 'guest',
        read_episode_ids: local.readEpisodeIds,
        last_episode: lastEpisode
          ? {
              id: lastEpisode.id,
              public_id: lastEpisode.publicId,
              title: lastEpisode.title,
            }
          : null,
      });
      return;
    }

    let cancelled = false;
    getWorkProgress(workId).then(
      (result) => {
        if (!cancelled) setProgress(result ? { ...result, source: 'server' } : null);
      },
      () => {
        // 진행도는 열람을 막지 않는 부가 기능이다. 404·5xx를 0%로 오인시키지 않고 숨긴다.
        if (!cancelled) setProgress(null);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [episodes, workId]);

  // 첫 화 CTA와 회차 목록은 공개 정보라 SSR에 포함해도 안전하다. 개인 진행도와 그에 따른
  // 다음 화 선택은 hydration 뒤 응답이 있을 때만 렌더한다.
  const guestLastEpisode =
    progress?.source === 'guest' && progress.last_episode
      ? episodes.find((episode) => episode.id === progress.last_episode?.id) ?? null
      : null;
  const cta = guestLastEpisode
    ? { label: '이어 보기' as const, episode: guestLastEpisode }
    : selectReadingCta(episodes, progress?.last_episode ?? null);
  if (!cta) return null;

  const summary = progress
    ? summarizeWorkProgress(progress.read_episode_ids, episodes.length)
    : null;

  return (
    <>
      {summary && (
        <section
          className="mb-6 rounded-control border border-line bg-paper p-4"
          aria-label="작품 진행도"
        >
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium text-ink">읽은 진행도</span>
            <span className="text-muted">
              {summary.readCount}/{episodes.length}화
            </span>
          </div>
          <div
            className="mb-4 h-2 overflow-hidden rounded-pill bg-line"
            role="progressbar"
            aria-label="읽은 회차 비율"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={summary.percent}
          >
            <div
              className="h-full rounded-pill bg-ink-strong"
              style={{ width: `${summary.percent}%` }}
            />
          </div>
        </section>
      )}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-4 pt-3"
        style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))' }}
        data-floating-reading-cta
      >
        <a
          href={`/works/${workId}/${cta.episode.publicId}`}
          className="pointer-events-auto mx-auto flex min-h-14 w-full max-w-xl min-w-0 flex-col items-center justify-center rounded-control border border-ink-strong bg-ink-strong px-4 py-2.5 text-center text-paper transition-colors hover:bg-ink"
        >
          <span className="text-sm font-semibold">{cta.label}</span>
          <span className="mt-0.5 block max-w-full truncate text-xs text-paper/75">
            {cta.episode.title}
          </span>
        </a>
      </div>
    </>
  );
}
