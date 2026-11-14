import { useEffect, useState } from 'react';
import { getViewerBootstrap, type ViewerBootstrap } from '../../lib/viewerBootstrap';
import Viewer from './Viewer';

interface Props {
  workId: string;
  publicId: number;
}

type EntryState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'notFound' }
  | { status: 'ready'; bootstrap: ViewerBootstrap };

export default function ViewerEntry({ workId, publicId }: Props) {
  return <ViewerEntryRequest key={`${workId}/${publicId}`} workId={workId} publicId={publicId} />;
}

function ViewerEntryRequest({ workId, publicId }: Props) {
  const [state, setState] = useState<EntryState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getViewerBootstrap(workId, publicId, document.cookie)
      .then((bootstrap) => {
        if (cancelled) return;
        setState(bootstrap ? { status: 'ready', bootstrap } : { status: 'notFound' });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'error' });
      });
    return () => {
      cancelled = true;
    };
  }, [workId, publicId, attempt]);

  if (state.status === 'loading') {
    return <p className="text-sm text-muted" role="status">회차를 불러오고 있어요.</p>;
  }
  if (state.status === 'notFound') {
    return <p className="text-sm text-muted">회차를 찾을 수 없어요.</p>;
  }
  if (state.status === 'error') {
    return (
      <div>
        <p className="text-sm text-muted">일시적인 오류로 회차를 불러오지 못했어요.</p>
        <button
          type="button"
          className="mt-4 text-sm underline"
          onClick={() => {
            setState({ status: 'loading' });
            setAttempt((value) => value + 1);
          }}
        >
          다시 시도
        </button>
      </div>
    );
  }

  const bootstrap = state.bootstrap;
  const previous = bootstrap.previous_episode;
  const next = bootstrap.next_episode;
  return (
    <>
      <h1 className="sr-only">{bootstrap.work_title} · {bootstrap.episode_title}</h1>
      <Viewer
        key={bootstrap.episode_id}
        episodeId={bootstrap.episode_id}
        initialSessionReady
        navigation={{
          workId: bootstrap.work_id,
          workTitle: bootstrap.work_title,
          episodeTitle: bootstrap.episode_title,
          episodeSubtitle: bootstrap.episode_subtitle,
          previousEpisode: previous ? { publicId: previous.public_id, title: previous.title } : null,
          nextEpisode: next ? { publicId: next.public_id, title: next.title } : null,
        }}
      />
      <nav
        aria-label="회차 끝 이동"
        className="flex items-center justify-between gap-4 mt-10 pt-6 border-t border-line text-sm"
      >
        {previous ? (
          <a
            href={`/works/${bootstrap.work_id}/${previous.public_id}`}
            className="min-h-[44px] rounded-control px-3 py-3 text-ink hover:bg-hover truncate max-w-[45%]"
            title={previous.title}
            data-astro-reload
          >
            ← {previous.title}
          </a>
        ) : <span />}
        {next ? (
          <a
            href={`/works/${bootstrap.work_id}/${next.public_id}`}
            className="min-h-[44px] rounded-control px-3 py-3 text-ink hover:bg-hover truncate max-w-[45%]"
            title={next.title}
            data-astro-reload
          >
            {next.title} →
          </a>
        ) : <span />}
      </nav>
    </>
  );
}
