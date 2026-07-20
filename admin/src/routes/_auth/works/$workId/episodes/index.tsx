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
          {work && <h1 className="text-2xl font-bold">{work.title}</h1>}
          <p className="text-sm text-gray-500">에피소드 관리</p>
        </div>
        <div className="flex gap-2">
          {/* Secondary(DESIGN.md) - 얇은 잉크색 테두리 + 투명 배경. 여러 액션이 나란히 있을 때
              가장 어두운 Primary와 구분한다(악센트 색 없이 강조 순위만 표현). */}
          <Link
            to="/works/$workId"
            params={{ workId }}
            className="rounded-lg border border-gray-900 px-3 py-2 text-sm text-gray-900 hover:bg-gray-50"
          >
            수정
          </Link>
          <Link
            to="/works/$workId/episodes/upload"
            params={{ workId }}
            className="rounded-lg bg-gray-900 px-3 py-2 text-sm text-white"
          >
            새 에피소드
          </Link>
        </div>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {episodes && (
        <EpisodeList workId={workId} episodes={episodes} basePrice={work?.episode_base_price} />
      )}
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
