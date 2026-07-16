import { createFileRoute } from '@tanstack/react-router';
import { EpisodeEditor } from '../../../../../components/episodes/EpisodeEditor';
import { useEpisodes } from '../../../../../hooks/useEpisodes';
import { describeAuthError } from '../../../../../lib/api';

export const Route = createFileRoute('/_auth/works/$workId/episodes/$episodeId')({
  component: EditEpisodePage,
});

function EditEpisodePage() {
  const { workId, episodeId } = Route.useParams();
  // 상세 GET이 없어(D3 계약) 목록에서 찾는다. 본문 이미지 미리보기는 에디터가 presigned로 로드한다.
  const { data: episodes, isLoading, isError, error } = useEpisodes(workId);
  const episode = episodes?.find((ep) => ep.id === episodeId);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-bold">에피소드 편집</h1>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {!isLoading && !isError && episodes && !episode && (
        <p className="text-sm text-red-600">에피소드를 찾을 수 없습니다.</p>
      )}
      {/* 다른 에피소드로 이동해도 에디터 상태(본문·제목)가 남지 않게 episodeId로 리마운트. */}
      {episode && <EpisodeEditor key={episodeId} initialWorkId={workId} episode={episode} />}
    </main>
  );
}
