import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useDeleteWork, useUpdateWork, useUploadCover } from './useWorks';
import type { Work } from '../types';

vi.mock('../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../lib/api');

const WORK_ID = 'w1';
const OTHER_WORK_ID = 'w2';

function makeWork(id: string): Work {
  return {
    id,
    author_id: 'u1',
    title: '작품',
    synopsis: null,
    cover_image: null,
    episode_base_price: 500,
    bundle_discount_rate: '0.000',
    status: 'ongoing',
    tags: [],
    episode_count: 0,
    created_at: '2026-07-14T00:00:00Z',
    updated_at: '2026-07-14T00:00:00Z',
  };
}

// 키를 훅에서 import하지 않고 리터럴로 고정한다 - 키 구조 자체가 검증 대상이기 때문.
// 목록 키가 상세 키의 prefix가 되면(과거 ['admin','works'] 구조) 목록 하나를 무효화할 때
// 화면 밖 상세 캐시까지 싹 재요청된다.
const LIST_KEY = ['admin', 'works', 'list'];
const detailKey = (id: string) => ['admin', 'works', 'detail', id];

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useWorks 캐시 키', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(LIST_KEY, [makeWork(WORK_ID), makeWork(OTHER_WORK_ID)]);
    queryClient.setQueryData(detailKey(WORK_ID), makeWork(WORK_ID));
    queryClient.setQueryData(detailKey(OTHER_WORK_ID), makeWork(OTHER_WORK_ID));
  });

  it('작품 수정은 목록만 무효화하고 무관한 작품의 상세 캐시는 건드리지 않는다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeWork(WORK_ID));

    const { result } = renderHook(() => useUpdateWork(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate({ workId: WORK_ID, body: { title: '새 제목' } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(detailKey(OTHER_WORK_ID))?.isInvalidated).toBe(false);
  });

  it('작품 삭제는 그 작품의 상세 캐시만 제거하고 목록을 무효화한다', async () => {
    vi.mocked(api.delete).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteWork(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate(WORK_ID);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(detailKey(WORK_ID))).toBeUndefined();
    expect(queryClient.getQueryData(detailKey(OTHER_WORK_ID))).toBeDefined();
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
  });
});

describe('useUploadCover', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  it('표지를 multipart(FormData)로 보내며 JSON 본문을 쓰지 않는다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeWork(WORK_ID));
    const file = new File(['x'], 'cover.jpg', { type: 'image/jpeg' });

    const { result } = renderHook(() => useUploadCover(), { wrapper: makeWrapper(queryClient) });
    result.current.mutate({ workId: WORK_ID, file });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [path, json, init] = vi.mocked(api.post).mock.calls[0];
    expect(path).toBe(`/admin/works/${WORK_ID}/cover`);
    // json이 undefined여야 shared api가 Content-Type을 붙이지 않는다 - 붙이면 브라우저가
    // multipart boundary를 넣지 못해 백엔드가 파일을 파싱하지 못한다.
    expect(json).toBeUndefined();
    const body = (init as RequestInit).body as FormData;
    // 필드명은 백엔드 UploadFile 파라미터명(image)과 일치해야 FastAPI가 바인딩한다.
    expect(body.get('image')).toBe(file);
  });
});
