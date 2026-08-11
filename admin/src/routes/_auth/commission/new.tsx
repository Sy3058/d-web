import { useRef, useState } from 'react';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { CommissionForm } from '../../../components/commission/CommissionForm';
import { SampleImageStaging } from '../../../components/commission/SampleImageStaging';
import {
  useCreateCommissionItem,
  useUpdateCommissionItem,
  useUploadCommissionSample,
} from '../../../hooks/useCommissionItems';
import { describeAuthError } from '../../../lib/api';
import type { CommissionItemInput } from '../../../lib/validation';

export const Route = createFileRoute('/_auth/commission/new')({
  component: NewCommissionItemPage,
});

function NewCommissionItemPage() {
  const navigate = useNavigate();
  const createItem = useCreateCommissionItem();
  const updateItem = useUpdateCommissionItem();
  const uploadSample = useUploadCommissionSample();
  // 카드 생성과 샘플 업로드는 별개 요청이다(백엔드가 item_id를 요구) - 업로드만 실패하면
  // 재시도 시 같은 카드가 또 만들어지지 않도록 생성된 id를 기억한다(works/new.tsx와 같은 이유).
  const createdItemIdRef = useRef<string | null>(null);
  const [sampleFiles, setSampleFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleSubmit = async (data: CommissionItemInput) => {
    setUploadError(null);
    let itemId = createdItemIdRef.current;
    try {
      if (itemId === null) {
        const item = await createItem.mutateAsync(data);
        itemId = item.id;
        createdItemIdRef.current = itemId;
      } else {
        // 재시도 경로: 카드는 이미 있으므로 만들지 않고, 폼에서 고친 값만 반영한다.
        await updateItem.mutateAsync({ itemId, body: data });
      }
    } catch {
      // 카드 생성/수정 실패는 아래 mutation error 상태로 표시된다. 여기서 삼키지 않으면
      // react-hook-form의 handleSubmit이 예외를 재throw해 unhandled rejection이 된다.
      return;
    }

    // 스테이징한 샘플을 순차 업로드(SampleImageManager와 같은 이유 - 서버의 원자 append가
    // expected_len 기반 조건부 UPDATE라 병렬 전송은 뒤 요청이 409로 실패하며 미참조 파일을
    // 남긴다). 하나라도 실패하면 페이지에 머물러 - 이미 올라간 장은 스테이징에서 빼
    // 재제출이 중복 업로드하지 않게 한다.
    let uploaded = 0;
    for (const file of sampleFiles) {
      try {
        await uploadSample.mutateAsync({ itemId, file });
        uploaded += 1;
      } catch (err) {
        setUploadError(
          sampleFiles.length > 1
            ? `${describeAuthError(err)} (${sampleFiles.length}장 중 ${uploaded}장 업로드됨, 나머지는 다시 시도해 주세요)`
            : describeAuthError(err),
        );
        setSampleFiles((prev) => prev.slice(uploaded));
        return;
      }
    }
    navigate({ to: '/commission/$itemId', params: { itemId } });
  };

  const isPending = createItem.isPending || updateItem.isPending || uploadSample.isPending;
  const mutationError = createItem.error ?? updateItem.error;
  const submitError = uploadError ?? (mutationError ? describeAuthError(mutationError) : null);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <h1 className="text-2xl font-bold">커미션 카드 등록</h1>
      <CommissionForm
        onSubmit={handleSubmit}
        isPending={isPending}
        error={submitError}
        submitLabel="등록"
      />
      <SampleImageStaging files={sampleFiles} onChange={setSampleFiles} />
    </main>
  );
}
