import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SiteTextEditor } from './SiteTextEditor';
import type { SiteText } from '../../types';

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../../lib/api');

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('SiteTextEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('행 없음(updated_at=null)이면 "아직 저장된 적 없음"을 보여준다', async () => {
    const empty: SiteText = { key: 'landing_intro', body: '', updated_at: null };
    vi.mocked(api.get).mockResolvedValueOnce(empty);

    renderWithClient(<SiteTextEditor slotKey="landing_intro" label="랜딩 소개" help="" />);

    await waitFor(() => expect(screen.getByText('아직 저장된 적 없음')).toBeInTheDocument());
  });

  it('빈 문자열로 저장할 수 있다 (존 접기)', async () => {
    const existing: SiteText = {
      key: 'commission_notes',
      body: '기존 문구',
      updated_at: '2026-08-01T00:00:00Z',
    };
    vi.mocked(api.get).mockResolvedValueOnce(existing);
    vi.mocked(api.put).mockResolvedValueOnce({
      key: 'commission_notes',
      body: '',
      updated_at: '2026-08-05T00:00:00Z',
    });

    renderWithClient(<SiteTextEditor slotKey="commission_notes" label="커미션 유의사항" help="" />);

    await waitFor(() => expect(screen.getByDisplayValue('기존 문구')).toBeInTheDocument());
    fireEvent.change(screen.getByDisplayValue('기존 문구'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/site-texts/commission_notes', { body: '' }),
    );
  });
});
