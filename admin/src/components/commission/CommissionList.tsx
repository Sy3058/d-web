import { useNavigate } from '@tanstack/react-router';
import type { CommissionItem } from '../../types';
import {
  useDeleteCommissionItem,
  useReorderCommissionItems,
  useUpdateCommissionItem,
} from '../../hooks/useCommissionItems';
import { describeAuthError } from '../../lib/api';
import { CommissionActionsMenu } from './CommissionActionsMenu';

const BADGE_CLASS = 'rounded px-2 py-0.5 text-xs';

interface CommissionListProps {
  items: CommissionItem[];
}

export function CommissionList({ items }: CommissionListProps) {
  const navigate = useNavigate();
  const updateItem = useUpdateCommissionItem();
  const reorderItems = useReorderCommissionItems();
  const deleteItem = useDeleteCommissionItem();

  if (items.length === 0) {
    return <p className="text-gray-500">등록된 커미션 카드가 없습니다.</p>;
  }

  const goToEdit = (itemId: string) => {
    navigate({ to: '/commission/$itemId', params: { itemId } });
  };

  const handleDelete = (item: CommissionItem) => {
    if (window.confirm(`"${item.title}" 카드를 삭제할까요? 샘플 이미지도 함께 삭제됩니다.`)) {
      deleteItem.mutate(item.id);
    }
  };

  const toggleOpen = (item: CommissionItem) => {
    updateItem.mutate({ itemId: item.id, body: { is_open: !item.is_open } });
  };

  // 순서는 컬렉션 전체의 속성이다. 인접 두 카드를 로컬에서 맞바꾼 뒤 전량 ID를 한 번에
  // 보내면 서버가 한 트랜잭션에서 1..N으로 정규화한다. 집합이 어긋난 stale 요청은 409다.
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    reorderItems.mutate(next.map((item) => item.id));
  };

  const deletingItemId = deleteItem.isPending ? deleteItem.variables : null;
  const updatingItemId = updateItem.isPending ? updateItem.variables?.itemId : null;
  const ordering = reorderItems.isPending;

  // isError를 각각 확인해 고른다 - `deleteItem.error ?? updateItem.error`로 합치면
  // 삭제가 먼저 실패해 에러가 남은 뒤 수정이 실패했을 때 낡은 삭제 문구가 표시된다.
  const actionError = deleteItem.isError
      ? deleteItem.error
      : updateItem.isError
        ? updateItem.error
        : reorderItems.isError
          ? reorderItems.error
        : null;

  return (
    <>
      {actionError && (
        <p className="mb-2 text-sm text-red-600">
          처리하지 못했습니다. {describeAuthError(actionError)}
        </p>
      )}
      <ul className="flex flex-col divide-y divide-gray-100">
        {items.map((item, index) => (
          <li key={item.id} className="flex items-center gap-2 py-2 pr-2 hover:bg-gray-50">
            <div className="flex flex-col">
              <button
                type="button"
                onClick={() => move(index, -1)}
                disabled={index === 0 || updatingItemId !== null || ordering}
                aria-label="위로 이동"
                className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
              >
                ▲
              </button>
              <button
                type="button"
                onClick={() => move(index, 1)}
                disabled={index === items.length - 1 || updatingItemId !== null || ordering}
                aria-label="아래로 이동"
                className="flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-700 disabled:opacity-30"
              >
                ▼
              </button>
            </div>

            <button
              type="button"
              onClick={() => goToEdit(item.id)}
              className={`flex min-w-0 flex-1 items-center gap-4 px-2 py-4 text-left${
                item.is_open ? '' : ' opacity-60'
              }`}
            >
              {item.sample_images[0]?.url ? (
                <img
                  src={item.sample_images[0].url}
                  alt=""
                  className="aspect-[4/3] w-24 shrink-0 rounded border border-gray-200 object-cover"
                />
              ) : (
                <div className="flex aspect-[4/3] w-24 shrink-0 items-center justify-center rounded border border-gray-200 bg-gray-100 text-[11px] text-gray-400">
                  샘플 없음
                </div>
              )}

              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="truncate font-medium">{item.title}</span>
                <span className="truncate text-sm text-gray-500">
                  {item.price_text}
                  {item.duration_text ? ` · ${item.duration_text}` : ''}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`${BADGE_CLASS} ${
                      item.is_open
                        ? 'bg-green-100 text-green-700'
                        : 'bg-yellow-100 text-yellow-700'
                    }`}
                  >
                    {item.is_open ? '접수 중' : '마감'}
                  </span>
                  <span className={`${BADGE_CLASS} bg-gray-100 text-gray-600`}>
                    샘플 {item.sample_images.length}장
                  </span>
                </div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => toggleOpen(item)}
              disabled={updatingItemId !== null || ordering}
              className="rounded border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {item.is_open ? '마감 처리' : '접수 재개'}
            </button>

            <CommissionActionsMenu
              onEdit={() => goToEdit(item.id)}
              onDelete={() => handleDelete(item)}
              isDeleting={deletingItemId === item.id}
            />
          </li>
        ))}
      </ul>
    </>
  );
}
