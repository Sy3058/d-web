import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SampleImageManager } from './SampleImageManager';
import type { CommissionItem } from '../../types';

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const { api } = await import('../../lib/api');

function makeItem(overrides: Partial<CommissionItem> = {}): CommissionItem {
  const keys = overrides.sample_image_keys ?? ['a.webp', 'b.webp'];
  return {
    id: 'c1',
    title: '카드',
    description: null,
    price_text: '50,000원~',
    duration_text: null,
    sample_image_keys: keys,
    sample_images: keys.map((key) => ({ key, url: `https://cdn.example/${key}` })),
    is_open: true,
    sort_order: 0,
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    ...overrides,
  };
}

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('SampleImageManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('오른쪽 이동은 이웃과 자리를 바꾼 sample_image_keys를 PUT한다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeItem());
    renderWithClient(<SampleImageManager item={makeItem()} />);

    fireEvent.click(screen.getAllByRole('button', { name: '오른쪽으로 이동' })[0]);

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [path, body] = vi.mocked(api.put).mock.calls[0];
    expect(path).toBe('/admin/commission-items/c1');
    // PR1 인계 계약: 재배열 PUT은 sample_image_keys 기준(sample_images가 아니다).
    expect(body).toEqual({ sample_image_keys: ['b.webp', 'a.webp'] });
  });

  it('삭제는 확인 후 해당 키를 뺀 sample_image_keys를 PUT한다', async () => {
    vi.mocked(api.put).mockResolvedValueOnce(makeItem());
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithClient(<SampleImageManager item={makeItem()} />);

    fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0]);

    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [, body] = vi.mocked(api.put).mock.calls[0];
    expect(body).toEqual({ sample_image_keys: ['b.webp'] });
  });

  it('삭제 확인을 취소하면 PUT을 보내지 않는다', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithClient(<SampleImageManager item={makeItem()} />);

    fireEvent.click(screen.getAllByRole('button', { name: '삭제' })[0]);

    expect(api.put).not.toHaveBeenCalled();
  });

  it('10장에 도달하면 이미지 추가 버튼이 비활성화된다', () => {
    const fullItem = makeItem({
      sample_image_keys: Array.from({ length: 10 }, (_, i) => `img-${i}.webp`),
    });
    renderWithClient(<SampleImageManager item={fullItem} />);

    expect(screen.getByRole('button', { name: '이미지 추가' })).toBeDisabled();
  });

  it('9장이면 이미지 추가 버튼이 아직 활성 상태다', () => {
    // 위 케이스만 두면 "항상 비활성" 구현도 통과한다 - 경계 바로 아래를 함께 고정한다.
    const nearLimit = makeItem({
      sample_image_keys: Array.from({ length: 9 }, (_, i) => `img-${i}.webp`),
    });
    renderWithClient(<SampleImageManager item={nearLimit} />);

    expect(screen.getByRole('button', { name: '이미지 추가' })).toBeEnabled();
  });

  it('업로드는 multipart(FormData, 필드명 image)로 전송된다', async () => {
    vi.mocked(api.post).mockResolvedValueOnce(makeItem());
    renderWithClient(<SampleImageManager item={makeItem({ sample_image_keys: [] })} />);

    const file = new File(['x'], 'sample.jpg', { type: 'image/jpeg' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [path, json, init] = vi.mocked(api.post).mock.calls[0];
    expect(path).toBe('/admin/commission-items/c1/images');
    expect(json).toBeUndefined();
    const body = (init as RequestInit).body as FormData;
    expect(body.get('image')).toBe(file);
  });
});
