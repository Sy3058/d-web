import { Link, createFileRoute, useNavigate } from '@tanstack/react-router';
import { WorkForm } from '../../../../components/works/WorkForm';
import { useUpdateWork, useUploadCover, useWork } from '../../../../hooks/useWorks';
import { describeAuthError } from '../../../../lib/api';
import type { WorkInput } from '../../../../lib/validation';

export const Route = createFileRoute('/_auth/works/$workId/')({
  component: EditWorkPage,
});

function EditWorkPage() {
  const { workId } = Route.useParams();
  const navigate = useNavigate();
  const { data: work, isLoading, isError, error } = useWork(workId);
  const updateWork = useUpdateWork();
  const uploadCover = useUploadCover();

  const handleSubmit = async (data: WorkInput, coverFile: File | null) => {
    try {
      await updateWork.mutateAsync({ workId, body: data });
      if (coverFile) {
        await uploadCover.mutateAsync({ workId, file: coverFile });
      }
      navigate({ to: '/works' });
    } catch {
      // 실패 내용은 아래 mutation error 상태로 화면에 표시된다. 여기서 삼키지 않으면
      // react-hook-form의 handleSubmit이 예외를 재throw해 unhandled rejection이 된다.
    }
  };

  const isPending = updateWork.isPending || uploadCover.isPending;
  const submitError = updateWork.error ?? uploadCover.error;

  return (
    <main className="mx-auto max-w-2xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">작품 수정</h1>
        <Link
          to="/works/$workId/episodes"
          params={{ workId }}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          에피소드 관리
        </Link>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {work && (
        <WorkForm
          defaultValues={{
            title: work.title,
            synopsis: work.synopsis ?? '',
            episode_base_price: work.episode_base_price,
            status: work.status,
            is_published: work.is_published,
            tag_names: work.tags.map((tag) => tag.name),
          }}
          hasExistingCover={!!work.cover_image}
          onSubmit={handleSubmit}
          isPending={isPending}
          error={submitError ? describeAuthError(submitError) : null}
          submitLabel="저장"
        />
      )}
    </main>
  );
}
