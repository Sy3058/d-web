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
    is_published: false,
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

// 예약 검증은 미래 시각만 통과하므로 now+ahead를 datetime-local 로컬 문자열로 만든다.
function futureLocalInput(msAhead: number): string {
  const d = new Date(Date.now() + msAhead);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
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

  it('이미지 드롭: 에디터에 파일을 드롭하면 파일 입력과 같은 경로로 업로드·삽입된다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode({ id: 'e1' }));
    vi.mocked(api.post).mockResolvedValueOnce(makeEpisode({ id: 'e1', image_keys: ['k1'] }));
    const { container } = renderEditor({ initialWorkId: 'w1' });

    await screen.findByRole('button', { name: '이미지' });
    const file = new File(['x'], 'p.png', { type: 'image/png' });
    fireEvent.drop(screen.getByTestId('editor-dropzone'), {
      dataTransfer: { files: [file], types: ['Files'] },
    });

    await waitFor(() =>
      expect(container.querySelector('img')?.getAttribute('src')).toBe('blob:preview'),
    );
    // 드롭도 업로드 엔드포인트로 이미지를 올린다(draft 생성 1 + 이미지 1).
    expect(vi.mocked(api.post).mock.calls[1][0]).toBe('/admin/works/w1/episodes/e1/images');
  });

  it('발행하기: 모달에서 즉시 공개하면 is_published=true PUT 후 목록으로 이동', async () => {
    const episode = makeEpisode({
      id: 'e1',
      title: '1화',
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

  it('발행하기: 예약 공개하면 published_at만 PUT하고 is_published는 싣지 않는다', async () => {
    const episode = makeEpisode({
      id: 'e1',
      title: '1화',
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '본문' }] }],
      },
    });
    vi.mocked(api.put).mockResolvedValueOnce(makeEpisode({ id: 'e1' }));
    const { container } = renderEditor({ episode });

    fireEvent.click(await screen.findByRole('button', { name: '발행하기' }));
    fireEvent.click(await screen.findByRole('button', { name: '예약 공개' }));

    const dtInput = await waitFor(() => {
      const el = container.querySelector('input[type="datetime-local"]');
      if (!el) throw new Error('datetime input not shown');
      return el as HTMLInputElement;
    });
    const future = futureLocalInput(60 * 60 * 1000);
    fireEvent.change(dtInput, { target: { value: future } });

    fireEvent.click(screen.getByRole('button', { name: '예약하기' }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalled());
    const [putPath, putBody] = vi.mocked(api.put).mock.calls[0] as [
      string,
      Record<string, unknown>,
    ];
    expect(putPath).toBe('/admin/works/w1/episodes/e1');
    expect(putBody.published_at).toBe(new Date(future).toISOString());
    expect(putBody).not.toHaveProperty('is_published');
    expect(navigateMock).toHaveBeenCalledWith({
      to: '/works/$workId/episodes',
      params: { workId: 'w1' },
    });
  });

  it('발행하기: 예약인데 과거 시각이면 검증에 막혀 PUT하지 않고 에러를 보여준다', async () => {
    const episode = makeEpisode({
      id: 'e1',
      title: '1화',
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '본문' }] }],
      },
    });
    const { container } = renderEditor({ episode });

    fireEvent.click(await screen.findByRole('button', { name: '발행하기' }));
    fireEvent.click(await screen.findByRole('button', { name: '예약 공개' }));

    const dtInput = await waitFor(() => {
      const el = container.querySelector('input[type="datetime-local"]');
      if (!el) throw new Error('datetime input not shown');
      return el as HTMLInputElement;
    });
    fireEvent.change(dtInput, { target: { value: futureLocalInput(-60 * 60 * 1000) } });

    fireEvent.click(screen.getByRole('button', { name: '예약하기' }));

    expect(await screen.findByText('미래 시각을 선택해 주세요.')).toBeInTheDocument();
    expect(vi.mocked(api.put)).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('제목 없이 임시저장하면 저장을 막고 제목 작성을 안내한다', async () => {
    renderEditor({ initialWorkId: 'w1' });
    await screen.findByRole('button', { name: '이미지' });

    fireEvent.click(screen.getByRole('button', { name: '임시저장' }));

    expect(await screen.findByText('제목을 작성해 주세요.')).toBeInTheDocument();
    expect(vi.mocked(api.post)).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('제목 없이 발행하려 하면 모달을 열지 않고 제목 작성을 안내한다', async () => {
    const episode = makeEpisode({
      id: 'e1',
      content: {
        type: 'doc',
        content: [{ type: 'paragraph', content: [{ type: 'text', text: '본문' }] }],
      },
    });
    renderEditor({ episode });

    fireEvent.click(await screen.findByRole('button', { name: '발행하기' }));

    expect(await screen.findByText('제목을 작성해 주세요.')).toBeInTheDocument();
    // 모달 전용 '공개 시점'이 없으면 모달이 열리지 않은 것.
    expect(screen.queryByText('공개 시점')).toBeNull();
  });
});
