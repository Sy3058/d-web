import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { CommissionForm } from '../../../components/commission/CommissionForm';
import { SampleImageManager } from '../../../components/commission/SampleImageManager';
import {
  commissionItemDetailKey,
  useCommissionItems,
  useUpdateCommissionItem,
} from '../../../hooks/useCommissionItems';
import { describeAuthError } from '../../../lib/api';
import type { CommissionItemInput } from '../../../lib/validation';
import { useQueryClient } from '@tanstack/react-query';

export const Route = createFileRoute('/_auth/commission/$itemId')({
  component: EditCommissionItemPage,
});

function EditCommissionItemPage() {
  const { itemId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // 상세 GET이 없어(카드도 episode 패턴과 동일) 목록 캐시에서 찾는다. 목록이 아직 없으면
  // (직접 URL 진입 등) detail 캐시에서 시도 - useCreateCommissionItem이 생성 직후 채워둔다.
  const { data: items, isLoading, isError, error } = useCommissionItems();
  const item =
    items?.find((candidate) => candidate.id === itemId) ??
    queryClient.getQueryData(commissionItemDetailKey(itemId));
  const updateItem = useUpdateCommissionItem();

  const handleSubmit = async (data: CommissionItemInput) => {
    try {
      await updateItem.mutateAsync({ itemId, body: data });
    } catch {
      // 실패 내용은 아래 mutation error 상태로 표시된다.
    }
  };

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">커미션 카드 수정</h1>
        <button
          type="button"
          onClick={() => navigate({ to: '/commission' })}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
        >
          목록으로
        </button>
      </div>
      {isLoading && <p className="text-gray-500">불러오는 중...</p>}
      {isError && <p className="text-sm text-red-600">{describeAuthError(error)}</p>}
      {!isLoading && !item && <p className="text-sm text-red-600">카드를 찾을 수 없습니다.</p>}
      {item && (
        <>
          <CommissionForm
            defaultValues={{
              title: item.title,
              description: item.description ?? '',
              price_text: item.price_text,
              duration_text: item.duration_text ?? '',
              is_open: item.is_open,
            }}
            onSubmit={handleSubmit}
            isPending={updateItem.isPending}
            error={updateItem.error ? describeAuthError(updateItem.error) : null}
            submitLabel="저장"
          />
          <SampleImageManager item={item} />
        </>
      )}
    </main>
  );
}
