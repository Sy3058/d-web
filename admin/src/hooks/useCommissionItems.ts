import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type {
  CommissionItem,
  CommissionItemCreate,
  CommissionItemReorder,
  CommissionItemUpdate,
} from '../types';

// useWorks와 같은 규칙: 키를 세그먼트로 분리해 서로 prefix가 되지 않게 한다
// (prefix 매칭 무효화가 무관한 쿼리까지 재요청하는 F2 함정).
export const commissionItemsListKey = ['admin', 'commission', 'list'] as const;
export const commissionItemDetailKey = (itemId: string) =>
  ['admin', 'commission', 'detail', itemId] as const;

const commissionItemsUrl = '/admin/commission-items';

export const commissionItemsQueryOptions = queryOptions({
  queryKey: commissionItemsListKey,
  queryFn: () => api.get<CommissionItem[]>(commissionItemsUrl),
});

/** sort_order 순 목록. 상세 GET이 없어 편집 화면도 이 목록에서 찾는다(episode 패턴과 동일). */
export function useCommissionItems() {
  return useQuery(commissionItemsQueryOptions);
}

export function useCreateCommissionItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CommissionItemCreate) =>
      api.post<CommissionItem>(commissionItemsUrl, body),
    onSuccess: (item) => {
      queryClient.setQueryData(commissionItemDetailKey(item.id), item);
      queryClient.invalidateQueries({ queryKey: commissionItemsListKey });
    },
  });
}

/** 카드 전량을 원하는 순서로 보내 서버가 한 트랜잭션에서 sort_order를 1..N으로 재배정한다. */
export function useReorderCommissionItems() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemIds: string[]) => {
      const body: CommissionItemReorder = { item_ids: itemIds };
      return api.put<CommissionItem[]>(commissionItemsUrl, body);
    },
    onSuccess: (items) => {
      queryClient.setQueryData(commissionItemsListKey, items);
    },
    // 409는 다른 탭에서 카드 집합이 바뀌었다는 뜻이다. 실패 시 최신 목록을 다시 읽는다.
    onError: () => {
      queryClient.invalidateQueries({ queryKey: commissionItemsListKey });
    },
  });
}

/** 부분수정(생략=미변경). is_open 단독 토글·sample_image_keys 단독 재배열·삭제도 이 훅을 쓴다
 * (PR1 인계 계약 - PUT은 sample_image_keys 기준). */
export function useUpdateCommissionItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: CommissionItemUpdate }) =>
      api.put<CommissionItem>(`${commissionItemsUrl}/${itemId}`, body),
    onSuccess: (item) => {
      queryClient.setQueryData(commissionItemDetailKey(item.id), item);
      queryClient.invalidateQueries({ queryKey: commissionItemsListKey });
    },
  });
}

export function useDeleteCommissionItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => api.delete<void>(`${commissionItemsUrl}/${itemId}`),
    onSuccess: (_data, itemId) => {
      queryClient.removeQueries({ queryKey: commissionItemDetailKey(itemId) });
      queryClient.invalidateQueries({ queryKey: commissionItemsListKey });
    },
  });
}

/** 샘플 1장 업로드 - 응답은 append 반영된 카드 전체(useUploadCover와 같은 구조). */
export function useUploadCommissionSample() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, file }: { itemId: string; file: File }) => {
      const formData = new FormData();
      // 백엔드 UploadFile 파라미터명 `image`와 일치해야 한다(FastAPI 이름 바인딩).
      formData.append('image', file);
      return api.post<CommissionItem>(`${commissionItemsUrl}/${itemId}/images`, undefined, {
        body: formData,
      });
    },
    onSuccess: (item) => {
      queryClient.setQueryData(commissionItemDetailKey(item.id), item);
      queryClient.invalidateQueries({ queryKey: commissionItemsListKey });
    },
  });
}
