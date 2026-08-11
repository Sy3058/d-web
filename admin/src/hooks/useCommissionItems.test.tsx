import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useDeleteCommissionItem,
  useUpdateCommissionItem,
  useUploadCommissionSample,
} from './useCommissionItems';
import type { CommissionItem } from '../types';

vi.mock('../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../lib/api');

const ITEM_ID = 'c1';
const OTHER_ITEM_ID = 'c2';

function makeItem(id: string): CommissionItem {
  return {
    id,
    title: '카드',
    description: null,
    price_text: '50,000원~',
    duration_text: null,
    sample_image_keys: [],
    sample_images: [],
    is_open: true,
    sort_order: 0,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
  };
}

// 키를 훅에서 import하지 않고 리터럴로 고정한다 - useWorks.test.tsx와 같은 이유(키 구조 자체가
// 검증 대상 - 목록 키가 상세 키의 prefix가 되면 무관한 상세 캐시까지 재요청된다).
const LIST_KEY = ['admin', 'commission', 'list'];
const detailKey = (id: string) => ['admin', 'commission', 'detail', id];

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useCommissionItems 캐시 키', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(LIST_KEY, [makeItem(ITEM_ID), makeItem(OTHER_ITEM_ID)]);
    queryClient.setQueryData(detailKey(ITEM_ID), makeItem(ITEM_ID));
    queryClient.setQueryData(detailKey(OTHER_ITEM_ID), makeItem(OTHER_ITEM_ID));
  });

  it('카드 수정(is_open 토글 등)은 목록만 무효화하고 무관한 카드의 상세 캐시는 건드리지 않는다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeItem(ITEM_ID));

    const { result } = renderHook(() => useUpdateCommissionItem(), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate({ itemId: ITEM_ID, body: { is_open: false } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(detailKey(OTHER_ITEM_ID))?.isInvalidated).toBe(false);
  });

  it('카드 삭제는 그 카드의 상세 캐시만 제거하고 목록을 무효화한다', async () => {
    vi.mocked(api.delete).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteCommissionItem(), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate(ITEM_ID);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData(detailKey(ITEM_ID))).toBeUndefined();
    expect(queryClient.getQueryData(detailKey(OTHER_ITEM_ID))).toBeDefined();
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
  });
});

describe('useUploadCommissionSample', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  });

  it('샘플 이미지를 multipart(FormData)로 보내며 JSON 본문을 쓰지 않는다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeItem(ITEM_ID));
    const file = new File(['x'], 'sample.jpg', { type: 'image/jpeg' });

    const { result } = renderHook(() => useUploadCommissionSample(), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate({ itemId: ITEM_ID, file });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [path, json, init] = vi.mocked(api.post).mock.calls[0];
    expect(path).toBe(`/admin/commission-items/${ITEM_ID}/images`);
    // json이 undefined여야 shared api가 Content-Type을 붙이지 않는다(useWorks.useUploadCover와 같은 이유).
    expect(json).toBeUndefined();
    const body = (init as RequestInit).body as FormData;
    // 필드명은 백엔드 UploadFile 파라미터명(image)과 일치해야 FastAPI가 바인딩한다.
    expect(body.get('image')).toBe(file);
  });
});
