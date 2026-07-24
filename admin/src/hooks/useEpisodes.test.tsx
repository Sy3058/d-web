import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useUpdateEpisode, useUploadEpisodeImage } from './useEpisodes';
import type { Episode } from '../types';

vi.mock('../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../lib/api')>('../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../lib/api');

function makeEpisode(id: string, imageKeys: string[] = []): Episode {
  return {
    id,
    work_id: 'w1',
    episode_no: 1,
    title: '1화',
    subtitle: null,
    thumbnail: null,
    thumbnail_url: null,
    price: null,
    is_free: false,
    content: { type: 'doc', content: [] },
    draft: null,
    image_keys: imageKeys,
    is_published: false,
    published_at: null,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
  };
}

// useWorks.test와 같은 이유로 키를 리터럴로 고정한다 - 키 구조(비prefix)가 검증 대상.
const listKey = (workId: string) => ['admin', 'episodes', 'list', workId];
const imageUrlsKey = (workId: string, episodeId: string) => [
  'admin',
  'episodes',
  'image-urls',
  workId,
  episodeId,
];

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useEpisodes 캐시 키', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(listKey('w1'), [makeEpisode('e1')]);
    queryClient.setQueryData(listKey('w2'), [makeEpisode('e2')]);
    queryClient.setQueryData(imageUrlsKey('w1', 'e1'), []);
  });

  it('에피소드 수정은 해당 작품 목록만 무효화하고 다른 작품·미리보기 캐시는 건드리지 않는다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeEpisode('e1'));

    const { result } = renderHook(() => useUpdateEpisode('w1'), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate({ episodeId: 'e1', body: { title: '새 제목' } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(listKey('w1'))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(listKey('w2'))?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(imageUrlsKey('w1', 'e1'))?.isInvalidated).toBe(false);
  });
});

describe('useUploadEpisodeImage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('페이지를 multipart(FormData) 필드명 image로 보내며 JSON 본문을 쓰지 않는다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode('e1', ['k1']));
    const file = new File(['x'], 'page1.png', { type: 'image/png' });
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });

    const { result } = renderHook(() => useUploadEpisodeImage('w1'), {
      wrapper: makeWrapper(queryClient),
    });
    result.current.mutate({ episodeId: 'e1', file });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [path, json, init] = vi.mocked(api.post).mock.calls[0];
    expect(path).toBe('/admin/works/w1/episodes/e1/images');
    // json이 undefined여야 shared api가 Content-Type을 붙이지 않는다(useWorks 표지와 동일 계약).
    expect(json).toBeUndefined();
    const body = (init as RequestInit).body as FormData;
    expect(body.get('image')).toBe(file);
  });
});
