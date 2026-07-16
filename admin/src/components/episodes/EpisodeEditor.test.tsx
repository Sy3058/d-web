import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EpisodeEditor } from './EpisodeEditor';
import type { Episode, Work } from '../../types';

const navigateMock = vi.fn();
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigateMock }));

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../../lib/api');

function makeWork(): Work {
  return {
    id: 'w1',
    author_id: 'u1',
    title: '작품A',
    synopsis: null,
    cover_image: null,
    episode_base_price: 1000,
    bundle_discount_rate: '0.000',
    status: 'ongoing',
    tags: [],
    episode_count: 0,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
  };
}

function makeEpisode(overrides: Partial<Episode> = {}): Episode {
  return {
    id: 'e1',
    work_id: 'w1',
    episode_no: 1,
    title: '무제',
    subtitle: null,
    thumbnail: null,
    price: null,
    is_free: true,
    content: { type: 'doc', content: [] },
    image_keys: [],
    is_published: false,
    published_at: null,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}

function renderEditor(props: Parameters<typeof EpisodeEditor>[0] = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <EpisodeEditor {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  navigateMock.mockReset();
  // 작품 목록(시리즈 드롭다운)과 image-urls를 URL로 구분해 응답.
  vi.mocked(api.get).mockImplementation((path: string) =>
    Promise.resolve((path === '/admin/works' ? [makeWork()] : []) as never),
  );
  URL.createObjectURL = vi.fn(() => 'blob:preview');
  URL.revokeObjectURL = vi.fn();
});

describe('EpisodeEditor', () => {
  it('유료 경계는 삽입 없이 항상 본문에 떠 있다', async () => {
    renderEditor({ initialWorkId: 'w1' });
    expect(await screen.findByText(/여기부터 유료/)).toBeInTheDocument();
    // 삽입 버튼은 없어졌다(항상 존재하므로).
    expect(screen.queryByRole('button', { name: '유료 경계' })).toBeNull();
  });

  it('임시저장: draft 생성(제목 실림) → 본문 PUT(content 포함·is_published/image_keys 미포함) → 편집 라우트로 이동', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode({ id: 'e1' }));
    vi.mocked(api.put).mockResolvedValueOnce(makeEpisode({ id: 'e1' }));
    renderEditor({ initialWorkId: 'w1' });

    await screen.findByRole('button', { name: '이미지' });
    fireEvent.change(screen.getByPlaceholderText(/제목/), { target: { value: '1화 제목' } });
    fireEvent.click(screen.getByRole('button', { name: '임시저장' }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalled());

    const [createPath, createBody] = vi.mocked(api.post).mock.calls[0] as [
      string,
      Record<string, unknown>,
    ];
    expect(createPath).toBe('/admin/works/w1/episodes');
    expect(createBody.title).toBe('1화 제목');

    const [putPath, putBody] = vi.mocked(api.put).mock.calls[0] as [
      string,
      Record<string, unknown>,
    ];
    expect(putPath).toBe('/admin/works/w1/episodes/e1');
    expect(putBody).toHaveProperty('content');
    expect(putBody).not.toHaveProperty('is_published');
    expect(putBody).not.toHaveProperty('image_keys');
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/works/$workId/episodes/$episodeId',
      params: { workId: 'w1', episodeId: 'e1' },
    });
  });

  it('글로벌 진입: 작품 선택 전엔 저장·발행 비활성, 선택하면 활성화', async () => {
    renderEditor();
    await screen.findByRole('button', { name: '이미지' });

    expect((screen.getByRole('button', { name: '임시저장' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole('button', { name: '발행하기' }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(screen.getByText(/시리즈\(작품\)를 선택하세요/)).toBeInTheDocument();

    await screen.findByRole('option', { name: '작품A' });
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'w1' } });

    await waitFor(() =>
      expect((screen.getByRole('button', { name: '임시저장' }) as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  });

  it('이미지 삽입: 업로드 후 본문에 optimistic blob으로 이미지가 나타난다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode({ id: 'e1' }));
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode({ id: 'e1', image_keys: ['k1'] }));
    const { container } = renderEditor({ initialWorkId: 'w1' });

    await screen.findByRole('button', { name: '이미지' });
    const file = new File(['x'], 'p.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('image-input'), { target: { files: [file] } });

    await waitFor(() =>
      expect(container.querySelector('img')?.getAttribute('src')).toBe('blob:preview'),
    );
  });

  it('발행하기: 모달에서 즉시 공개하면 is_published=true PUT 후 목록으로 이동', async () => {
    const episode = makeEpisode({
      id: 'e1',
      content: {
        type: 'doc',
        content: [
          { type: 'paragraph', content: [{ type: 'text', text: '본문' }] },
          { type: 'paywall' },
        ],
      },
    });
    vi.mocked(api.put).mockResolvedValueOnce(makeEpisode({ id: 'e1', is_published: true }));
    renderEditor({ episode });

    fireEvent.click(await screen.findByRole('button', { name: '발행하기' }));
    // 모달의 발행하기 버튼(취소와 구분: 모달 안 두 번째 발행하기)
    const publishButtons = await screen.findAllByRole('button', { name: '발행하기' });
    fireEvent.click(publishButtons[publishButtons.length - 1]);

    await waitFor(() => expect(navigateMock).toHaveBeenCalled());
    const [putPath, putBody] = vi.mocked(api.put).mock.calls[0] as [
      string,
      Record<string, unknown>,
    ];
    expect(putPath).toBe('/admin/works/w1/episodes/e1');
    expect(putBody.is_published).toBe(true);
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/works/$workId/episodes',
      params: { workId: 'w1' },
    });
  });
});
