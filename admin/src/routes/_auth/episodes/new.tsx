import { createFileRoute } from '@tanstack/react-router';
import { EpisodeEditor } from '../../../components/episodes/EpisodeEditor';

export const Route = createFileRoute('/_auth/episodes/new')({
  component: NewEpisodeGlobalPage,
});

// 작품(시리즈)을 미리 정하지 않고 바로 글쓰기를 시작하는 진입점. 작품은 에디터 상단에서
// 선택하며(이미지·저장 전 필수), 작품 경로(/works/$workId/episodes/upload)와 달리 workId가 없다.
function NewEpisodeGlobalPage() {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-bold">새 에피소드</h1>
      <EpisodeEditor />
    </main>
  );
}
