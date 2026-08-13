import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useEffect, useRef } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ImageCropModal } from './ImageCropModal';

vi.mock('react-easy-crop', () => {
  function MockCropper({
    onCropComplete,
  }: {
    onCropComplete: (area: unknown, pixels: object) => void;
  }) {
    const fired = useRef(false);
    useEffect(() => {
      if (fired.current) return;
      fired.current = true;
      onCropComplete({}, { x: 0, y: 0, width: 100, height: 100 });
    }, [onCropComplete]);
    return <div>크롭 영역</div>;
  }

  return { default: MockCropper };
});

vi.mock('../../lib/cropImage', () => ({
  getCroppedImageFile: vi.fn(() =>
    Promise.resolve(new File(['cropped'], 'profile.jpg', { type: 'image/jpeg' })),
  ),
}));

describe('ImageCropModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = vi.fn(() => 'blob:raw-image');
    URL.revokeObjectURL = vi.fn();
  });

  it('비동기 완료 작업 중 중복 실행과 닫기를 막는다', async () => {
    let resolveUpload!: () => void;
    const upload = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveUpload = resolve;
        }),
    );
    const close = vi.fn();

    render(
      <ImageCropModal
        title="프로필 이미지 설정"
        aspect={1}
        cropShape="round"
        outputFileName="profile.jpg"
        onClose={close}
        onComplete={upload}
      />,
    );

    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['raw'], 'raw.png', { type: 'image/png' })] },
    });
    fireEvent.click(screen.getByRole('button', { name: '다음' }));
    const complete = await screen.findByRole('button', { name: '완료' });
    await waitFor(() => expect(complete).toBeEnabled());

    fireEvent.click(complete);
    fireEvent.click(complete);

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '처리 중...' }));
    expect(upload).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '처리 중...' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '닫기' })).toBeDisabled();

    resolveUpload();
    await waitFor(() => expect(screen.getByRole('button', { name: '완료' })).toBeEnabled());
    expect(close).not.toHaveBeenCalled();
  });
});
