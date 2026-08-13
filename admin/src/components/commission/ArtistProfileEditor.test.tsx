import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ArtistProfile } from '../../types';
import { ArtistProfileEditor } from './ArtistProfileEditor';

vi.mock('../../lib/api', async () => ({
  ...(await vi.importActual<typeof import('../../lib/api')>('../../lib/api')),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock('../common/ImageCropModal', () => ({
  ImageCropModal: ({ onComplete }: { onComplete: (file: File) => void }) => (
    <button
      type="button"
      onClick={() => onComplete(new File(['cropped'], 'profile.jpg', { type: 'image/jpeg' }))}
    >
      테스트 크롭 완료
    </button>
  ),
}));

const { api } = await import('../../lib/api');

function renderWithClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('ArtistProfileEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('서버 프로필을 표시하고 빈 링크는 null로 저장한다', async () => {
    const profile: ArtistProfile = {
      name: '도군',
      profile_image_url: null,
      twitter_url: 'https://twitter.com/',
      postype_url: 'https://www.postype.com/',
    };
    vi.mocked(api.get).mockResolvedValueOnce(profile);
    vi.mocked(api.put).mockResolvedValueOnce({ ...profile, name: '새 작가명', postype_url: null });

    renderWithClient(<ArtistProfileEditor />);

    await waitFor(() => expect(screen.getByLabelText('작가명')).toHaveValue('도군'));
    fireEvent.change(screen.getByLabelText('작가명'), { target: { value: '새 작가명' } });
    fireEvent.change(screen.getByLabelText('Postype URL'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '프로필 저장' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/admin/artist-profile', {
        name: '새 작가명',
        twitter_url: 'https://twitter.com/',
        postype_url: null,
      }),
    );
  });

  it('프로필 이미지를 multipart로 업로드한다', async () => {
    const profile: ArtistProfile = {
      name: '도군',
      profile_image_url: null,
      twitter_url: null,
      postype_url: null,
    };
    vi.mocked(api.get).mockResolvedValueOnce(profile);
    vi.mocked(api.post).mockResolvedValueOnce({
      ...profile,
      profile_image_url: 'https://assets.example.com/artist-profile/new.webp',
    });

    renderWithClient(<ArtistProfileEditor />);
    await waitFor(() => expect(screen.getByText('프로필 이미지 업로드')).toBeInTheDocument());
    fireEvent.click(screen.getByText('프로필 이미지 업로드'));
    fireEvent.click(screen.getByText('테스트 크롭 완료'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, body, options] = vi.mocked(api.post).mock.calls[0];
    expect(url).toBe('/admin/artist-profile/image');
    expect(body).toBeUndefined();
    const uploaded = (options?.body as FormData).get('image') as File;
    expect(uploaded.name).toBe('profile.jpg');
    expect(uploaded.type).toBe('image/jpeg');
  });

  it('http(s)가 아닌 외부 링크는 저장하지 않는다', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      name: '도군',
      profile_image_url: null,
      twitter_url: null,
      postype_url: null,
    });

    renderWithClient(<ArtistProfileEditor />);

    await waitFor(() => expect(screen.getByLabelText('Twitter URL')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Twitter URL'), {
      target: { value: 'javascript:alert(1)' },
    });
    fireEvent.click(screen.getByRole('button', { name: '프로필 저장' }));

    expect(
      await screen.findByText('올바른 http:// 또는 https:// URL을 입력해 주세요.'),
    ).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();
  });
});
