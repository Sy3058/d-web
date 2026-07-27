import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EpisodeList } from './EpisodeList';
import type { Episode } from '../../types';

// 목록은 라우터에서 Link만 쓴다 - 렌더 검증에 라우터 전체가 필요 없다.
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
}));

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../../lib/api');

function makeEpisode(overrides: Partial<Episode>): Episode {
  return {
    id: 'e1',
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
    image_keys: [],
    is_published: false,
    published_at: null,
    created_at: '2026-07-15T00:00:00Z',
    updated_at: '2026-07-15T00:00:00Z',
    ...overrides,
  };
}

function renderList(episodes: Episode[], basePrice?: number) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <EpisodeList workId="w1" episodes={episodes} basePrice={basePrice} />
    </QueryClientProvider>,
  );
}

/** 해당 회차의 "···" 메뉴를 연다. 항목은 열기 전엔 DOM에 없다. */
function openMenu(episodeNo: number) {
  fireEvent.click(screen.getByRole('button', { name: `${episodeNo}화 관리 메뉴` }));
}

describe('EpisodeList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('공개/예약/임시저장 상태와 가격(무료·기본가 금액·지정가)을 구분해 보여준다', () => {
    renderList(
      [
        makeEpisode({ id: 'e1', episode_no: 1, is_published: true, published_at: '2026-07-01T00:00:00Z', is_free: true }),
        makeEpisode({ id: 'e2', episode_no: 2, published_at: '2026-08-01T00:00:00Z' }),
        makeEpisode({ id: 'e3', episode_no: 3, price: 1000 }),
      ],
      2000,
    );

    expect(screen.getByText('공개')).toBeInTheDocument();
    expect(screen.getByText('예약')).toBeInTheDocument();
    expect(screen.getByText('임시저장')).toBeInTheDocument();
    expect(screen.getByText('무료')).toBeInTheDocument();
    // price NULL 회차는 실제 기본가 금액으로 풀어 보여준다.
    expect(screen.getByText('2,000원')).toBeInTheDocument();
    expect(screen.getByText('1,000원')).toBeInTheDocument();
  });

  it('기본가가 아직 로딩 전이면 price NULL 회차를 "기본가"로 폴백 표기한다', () => {
    renderList([makeEpisode({ id: 'e2', episode_no: 2, published_at: '2026-08-01T00:00:00Z' })]);
    expect(screen.getByText('기본가')).toBeInTheDocument();
  });

  it('에피소드가 없으면 빈 상태 안내를 보여준다', () => {
    renderList([]);
    expect(screen.getByText(/아직 에피소드가 없습니다/)).toBeInTheDocument();
  });

  it('편집본(draft)이 있는 회차에 임시저장본 배지를 붙인다(#86)', () => {
    renderList([
      makeEpisode({
        id: 'e1',
        is_published: true,
        published_at: '2026-07-01T00:00:00Z',
        draft: { title: '고친 제목', subtitle: null, content: { type: 'doc', content: [] } },
      }),
      makeEpisode({ id: 'e2', episode_no: 2 }),
    ]);
    expect(screen.getAllByText('임시저장본')).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// 액션 메뉴 - 비공개 전환 / 삭제 (#85)
// ---------------------------------------------------------------------------

describe('EpisodeList 액션 메뉴 (#85)', () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    confirmSpy = vi.spyOn(window, 'confirm');
  });

  afterEach(() => {
    confirmSpy.mockRestore();
  });

  // 아래 두 케이스는 짝이다. 공개 회차만 확인하면 "항상 노출"로 바뀌는 회귀를, 비공개
  // 회차만 확인하면 "항상 숨김"으로 바뀌는 회귀를 각각 놓친다.
  it('공개 회차에는 비공개 전환 항목이 뜬다', async () => {
    renderList([
      makeEpisode({ id: 'e1', is_published: true, published_at: '2026-07-01T00:00:00Z' }),
    ]);
    openMenu(1);
    expect(screen.getByRole('button', { name: '비공개로 전환' })).toBeInTheDocument();
  });

  it('이미 비공개인 회차에는 비공개 전환 항목이 뜨지 않는다', async () => {
    renderList([makeEpisode({ id: 'e1', is_published: false })]);
    openMenu(1);
    expect(screen.queryByRole('button', { name: '비공개로 전환' })).not.toBeInTheDocument();
    // 삭제는 상태와 무관하게 항상 있어야 한다 - 메뉴 자체가 안 열린 걸 통과로 오인하지 않게.
    expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();
  });

  it('비공개 전환은 is_published:false만 보낸다 (content 동봉 금지 - #86 409 회피)', async () => {
    vi.mocked(api.put).mockResolvedValue(undefined as never);
    renderList([
      makeEpisode({
        id: 'e1',
        is_published: true,
        published_at: '2026-07-01T00:00:00Z',
        content: { type: 'doc', content: [{ type: 'paragraph' }] },
      }),
    ]);

    openMenu(1);
    fireEvent.click(screen.getByRole('button', { name: '비공개로 전환' }));

    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    // 본문(content)이 한 글자라도 실리면 서버가 공개 회차 발행본 보호로 409를 낸다.
    expect(api.put).toHaveBeenCalledWith('/admin/works/w1/episodes/e1', { is_published: false });
  });

  it('삭제 확인 창에서 취소하면 요청을 보내지 않는다', async () => {
    confirmSpy.mockReturnValue(false);
    renderList([makeEpisode({ id: 'e1' })]);

    openMenu(1);
    fireEvent.click(screen.getByRole('button', { name: '삭제' }));

    expect(confirmSpy).toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('삭제를 확인하면 DELETE를 보내고, 번호 소진을 미리 알린다', async () => {
    confirmSpy.mockReturnValue(true);
    vi.mocked(api.delete).mockResolvedValue(undefined as never);
    renderList([makeEpisode({ id: 'e1', episode_no: 3, title: '3화 제목' })]);

    openMenu(3);
    fireEvent.click(screen.getByRole('button', { name: '삭제' }));

    // 번호가 소진돼 되돌릴 수 없다는 건 누르기 전에 알아야 한다(#85 결정).
    expect(confirmSpy.mock.calls[0][0]).toContain('다시 쓸 수 없습니다');
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/admin/works/w1/episodes/e1'),
    );
  });

  it('삭제가 진행 중이면 다른 회차의 삭제 항목도 잠근다 (종류 단위 직렬화)', async () => {
    confirmSpy.mockReturnValue(true);
    // 영원히 안 끝나는 인플라이트 - 잠금은 응답이 오기 전 상태에서 검증해야 한다.
    vi.mocked(api.delete).mockReturnValue(new Promise(() => {}) as never);
    renderList([
      makeEpisode({ id: 'e1', episode_no: 1 }),
      makeEpisode({ id: 'e2', episode_no: 2, is_published: true, published_at: '2026-07-01T00:00:00Z' }),
    ]);

    openMenu(1);
    fireEvent.click(screen.getByRole('button', { name: '삭제' }));

    // 훅 옵저버는 가장 최근 mutate 하나만 추적한다 - 두 번째 발사를 허용하면 앞선 요청의
    // 실패 표시(isError)가 유실되고 잠금이 새 행으로 옮겨간다(#85 리뷰 실측). 그래서
    // 행 단위가 아니라 종류 단위로 잠근다. (1화 메뉴는 클릭 시 닫혔으니 아래는 2화 항목이다.)
    openMenu(2);
    await waitFor(() => expect(screen.getByRole('button', { name: '삭제' })).toBeDisabled());
    // 종류가 다른 액션(비공개 전환)은 별개 훅 인스턴스라 간섭이 없어 잠그지 않는다.
    expect(screen.getByRole('button', { name: '비공개로 전환' })).not.toBeDisabled();
  });

  it('메뉴 바깥을 클릭하면 닫힌다', async () => {
    renderList([makeEpisode({ id: 'e1' })]);
    openMenu(1);
    expect(screen.getByRole('button', { name: '삭제' })).toBeInTheDocument();

    // 컴포넌트는 click이 아니라 mousedown을 듣는다 - 항목을 누르는 도중(mousedown 시점)에
    // 닫히면 click이 사라진 요소로 가서 액션이 발화하지 않기 때문.
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('button', { name: '삭제' })).not.toBeInTheDocument();
  });
});
