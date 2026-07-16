import { Link, createFileRoute } from '@tanstack/react-router';
import { EpisodeList } from '../../../../../components/episodes/EpisodeList';
import { useEpisodes } from '../../../../../hooks/useEpisodes';
import { useWork } from '../../../../../hooks/useWorks';
import { describeAuthError } from '../../../../../lib/api';

export const Route = createFileRoute('/_auth/works/$workId/episodes/')({
  component: EpisodesPage,
});

function EpisodesPage() {
  const { workId } = Route.useParams();
  const { data: work } = useWork(workId);
  const { data: episodes, isLoading, isError, error } = useEpisodes(workId);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">에피소드 관리</h1>
          {work && <p className="text-sm text-gray-500">{work.title}</p>}
        </div>
        <Link
          to="/works/$workId/episodes/upload"
          params={{ workId }}
          className="rounded bg-gray-900 px-3 py-2 text-sm text-white"
        >
          새 에피소드
        </Link>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {episodes && <EpisodeList workId={workId} episodes={episodes} />}
      <p className="mt-6">
        <Link
          to="/works"
          className="text-sm text-gray-500 underline"
        >
          ← 작품 리스트로
        </Link>
      </p>
    </main>
  );
}
