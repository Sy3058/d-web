import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import type { Work, WorkCreate, WorkUpdate } from '../types';

// 키는 서로 prefix가 되지 않게 세그먼트로 나눈다. TanStack Query의 무효화·제거는 기본이
// prefix 매칭이라, 목록 키가 ['admin','works']였다면 목록 하나를 무효화할 때 상세까지
// 전부 재요청된다.
// 회차 변경이 작품의 episode_count를 바꾸므로 useEpisodes도 이 키로 무효화한다(#85).
export const worksListKey = ['admin', 'works', 'list'] as const;
export const workDetailKey = (workId: string) => ['admin', 'works', 'detail', workId] as const;

export const worksQueryOptions = queryOptions({
  queryKey: worksListKey,
  queryFn: () => api.get<Work[]>('/admin/works'),
});

export function useWorks() {
  return useQuery(worksQueryOptions);
}

export function useWork(workId: string) {
  return useQuery({
    queryKey: workDetailKey(workId),
    queryFn: () => api.get<Work>(`/admin/works/${workId}`),
  });
}

export function useCreateWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkCreate) => api.post<Work>('/admin/works', body),
    onSuccess: (work) => {
      queryClient.setQueryData(workDetailKey(work.id), work);
      queryClient.invalidateQueries({ queryKey: worksListKey });
    },
  });
}

export function useUpdateWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ workId, body }: { workId: string; body: WorkUpdate }) =>
      api.put<Work>(`/admin/works/${workId}`, body),
    onSuccess: (work) => {
      queryClient.setQueryData(workDetailKey(work.id), work);
      queryClient.invalidateQueries({ queryKey: worksListKey });
    },
  });
}

export function useDeleteWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workId: string) => api.delete<void>(`/admin/works/${workId}`),
    onSuccess: (_data, workId) => {
      // 삭제된 작품의 상세 캐시는 되살아날 이유가 없으니 제거(무효화 아님).
      queryClient.removeQueries({ queryKey: workDetailKey(workId) });
      queryClient.invalidateQueries({ queryKey: worksListKey });
    },
  });
}

export function useUploadCover() {
  const queryClient = useQueryClient();
  return useMutation({
    // 백엔드 POST /admin/works/{id}/cover는 UploadFile 파라미터명이 `image`라
    // 폼 필드 이름을 그대로 맞춰야 한다(FastAPI가 이름으로 바인딩).
    mutationFn: ({ workId, file }: { workId: string; file: File }) => {
      const formData = new FormData();
      formData.append('image', file);
      // json을 undefined로 두면 shared api.post가 Content-Type을 붙이지 않는다 -
      // FormData는 브라우저가 boundary 포함 Content-Type을 자동 설정해야 하므로 필수.
      return api.post<Work>(`/admin/works/${workId}/cover`, undefined, { body: formData });
    },
    onSuccess: (work) => {
      queryClient.setQueryData(workDetailKey(work.id), work);
      queryClient.invalidateQueries({ queryKey: worksListKey });
    },
  });
}
