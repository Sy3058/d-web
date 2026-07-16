import { createFileRoute } from '@tanstack/react-router';
import { EpisodeEditor } from '../../../../../components/episodes/EpisodeEditor';

export const Route = createFileRoute('/_auth/works/$workId/episodes/upload')({
  component: NewEpisodePage,
});

function NewEpisodePage() {
  const { workId } = Route.useParams();
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-bold">새 에피소드</h1>
      <EpisodeEditor initialWorkId={workId} />
    </main>
  );
}
