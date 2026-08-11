import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CommissionList } from './CommissionList';
import type { CommissionItem } from '../../types';

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api, ApiError } = await import('../../lib/api');

function makeItem(id: string, sortOrder: number): CommissionItem {
  return {
    id,
    title: `카드 ${id}`,
    description: null,
    price_text: '50,000원~',
    duration_text: null,
    sample_image_keys: [],
    sample_images: [],
    is_open: true,
    sort_order: sortOrder,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
  };
}

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('CommissionList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('아래로 이동은 맞바꾼 카드 전량 ID를 컬렉션 PUT 한 건으로 보낸다', async () => {
    const items = [makeItem('a', 0), makeItem('b', 1)];
    vi.mocked(api.put).mockResolvedValue([items[1], items[0]]);
    renderWithClient(<CommissionList items={items} />);

    fireEvent.click(screen.getAllByRole('button', { name: '아래로 이동' })[0]);

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/commission-items', {
        item_ids: ['b', 'a'],
      }),
    );
    expect(api.put).toHaveBeenCalledTimes(1);
  });

  it('첫 카드는 위로 이동 버튼이 비활성화, 마지막 카드는 아래로 이동 버튼이 비활성화된다', () => {
    const items = [makeItem('a', 0), makeItem('b', 1)];
    renderWithClient(<CommissionList items={items} />);

    const upButtons = screen.getAllByRole('button', { name: '위로 이동' });
    const downButtons = screen.getAllByRole('button', { name: '아래로 이동' });
    expect(upButtons[0]).toBeDisabled();
    expect(downButtons[1]).toBeDisabled();
    // 반대쪽이 enabled인 것까지 봐야 "전부 비활성" 구현도 통과하는 판별력 0을 피한다.
    expect(downButtons[0]).toBeEnabled();
    expect(upButtons[1]).toBeEnabled();
  });

  it('원자 재정렬 PUT이 실패하면 에러를 표시하고 추가 요청을 보내지 않는다', async () => {
    vi.mocked(api.put).mockRejectedValueOnce(new ApiError(409, '{"detail":"목록이 바뀌었습니다"}'));
    const items = [makeItem('a', 0), makeItem('b', 1)];
    renderWithClient(<CommissionList items={items} />);

    fireEvent.click(screen.getAllByRole('button', { name: '아래로 이동' })[0]);

    await waitFor(() => expect(screen.getByText(/처리하지 못했습니다/)).toBeInTheDocument());
    expect(api.put).toHaveBeenCalledTimes(1);
  });

  it('마감 처리 버튼은 is_open=false를 PUT한다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeItem('a', 0));
    renderWithClient(<CommissionList items={[makeItem('a', 0)]} />);

    fireEvent.click(screen.getByRole('button', { name: '마감 처리' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/commission-items/a', { is_open: false }),
    );
  });
});
