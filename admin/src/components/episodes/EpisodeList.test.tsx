import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { EpisodeList } from './EpisodeList';
import type { Episode } from '../../types';

// 목록은 라우터에서 Link만 쓴다 - 렌더 검증에 라우터 전체가 필요 없다.
vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
}));

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

describe('EpisodeList', () => {
  it('공개/예약/임시저장 상태와 가격(무료·기본가 금액·지정가)을 구분해 보여준다', () => {
    render(
      <EpisodeList
        workId="w1"
        basePrice={2000}
        episodes={[
          makeEpisode({ id: 'e1', episode_no: 1, is_published: true, published_at: '2026-07-01T00:00:00Z', is_free: true }),
          makeEpisode({ id: 'e2', episode_no: 2, published_at: '2026-08-01T00:00:00Z' }),
          makeEpisode({ id: 'e3', episode_no: 3, price: 1000 }),
        ]}
      />,
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
    render(
      <EpisodeList
        workId="w1"
        episodes={[makeEpisode({ id: 'e2', episode_no: 2, published_at: '2026-08-01T00:00:00Z' })]}
      />,
    );
    expect(screen.getByText('기본가')).toBeInTheDocument();
  });

  it('에피소드가 없으면 빈 상태 안내를 보여준다', () => {
    render(<EpisodeList workId="w1" episodes={[]} />);
    expect(screen.getByText(/아직 에피소드가 없습니다/)).toBeInTheDocument();
  });

  it('편집본(draft)이 있는 회차에 임시저장본 배지를 붙인다(#86)', () => {
    render(
      <EpisodeList
        workId="w1"
        episodes={[
          makeEpisode({
            id: 'e1',
            is_published: true,
            published_at: '2026-07-01T00:00:00Z',
            draft: { title: '고친 제목', subtitle: null, content: { type: 'doc', content: [] } },
          }),
          makeEpisode({ id: 'e2', episode_no: 2 }),
        ]}
      />,
    );
    expect(screen.getAllByText('임시저장본')).toHaveLength(1);
  });
});
