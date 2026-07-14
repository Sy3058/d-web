import { useRef } from 'react';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { WorkForm } from '../../../components/works/WorkForm';
import { useCreateWork, useUpdateWork, useUploadCover } from '../../../hooks/useWorks';
import { describeAuthError } from '../../../lib/api';
import type { WorkInput } from '../../../lib/validation';

export const Route = createFileRoute('/_auth/works/new')({
  component: NewWorkPage,
});

function NewWorkPage() {
  const navigate = useNavigate();
  const createWork = useCreateWork();
  const updateWork = useUpdateWork();
  const uploadCover = useUploadCover();
  // 작품 생성과 표지 업로드는 별개 요청이라(백엔드가 work_id를 요구) 중간에 표지만
  // 실패할 수 있다. 그때 생성된 id를 기억해두지 않으면 사용자가 다시 '등록'을 눌렀을 때
  // 같은 작품이 하나 더 만들어진다(백엔드에 멱등성 없음).
  const createdWorkIdRef = useRef<string | null>(null);

  const handleSubmit = async (data: WorkInput, coverFile: File | null) => {
    try {
      let workId = createdWorkIdRef.current;
      if (workId === null) {
        workId = (await createWork.mutateAsync(data)).id;
        createdWorkIdRef.current = workId;
      } else {
        // 재시도 경로: 작품은 이미 있으므로 만들지 않고, 폼에서 고친 값만 반영한다.
        await updateWork.mutateAsync({ workId, body: data });
      }
      if (coverFile) {
        await uploadCover.mutateAsync({ workId, file: coverFile });
      }
      navigate({ to: '/works' });
    } catch {
      // 실패 내용은 아래 mutation error 상태로 화면에 표시된다. 여기서 삼키지 않으면
      // react-hook-form의 handleSubmit이 예외를 재throw해 unhandled rejection이 된다.
    }
  };

  const isPending = createWork.isPending || updateWork.isPending || uploadCover.isPending;
  const submitError = createWork.error ?? updateWork.error ?? uploadCover.error;

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="mb-4 text-2xl font-bold">작품 등록</h1>
      <WorkForm
        onSubmit={handleSubmit}
        isPending={isPending}
        error={submitError ? describeAuthError(submitError) : null}
        submitLabel="등록"
      />
    </main>
  );
}
