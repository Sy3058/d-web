import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PublishModal } from './PublishModal';

describe('PublishModal 가격 검증', () => {
  function setup() {
    const onPublish = vi.fn();
    render(
      <PublishModal
        workName="작품"
        images={[]}
        defaultThumbnail={null}
        defaultPrice={800}
        hasPaidContent
        canPublish
        isLive={false}
        saving={false}
        error={null}
        onCancel={vi.fn()}
        onPublish={onPublish}
      />,
    );
    return { onPublish, price: screen.getByRole('spinbutton', { name: /판매가/ }) };
  }

  it('상한 초과는 한국어 오류로 제출을 막고 경계값은 허용한다', async () => {
    const { onPublish, price } = setup();
    expect(price).toHaveAttribute('max', '2147483647');
    fireEvent.change(price, { target: { value: '2147483648' } });
    fireEvent.click(screen.getByRole('button', { name: '발행하기' }));
    expect(await screen.findByText('가격은 2,147,483,647원 이하여야 합니다.')).toBeInTheDocument();
    expect(onPublish).not.toHaveBeenCalled();

    fireEvent.change(price, { target: { value: '2147483647' } });
    fireEvent.click(screen.getByRole('button', { name: '발행하기' }));
    await waitFor(() => expect(onPublish).toHaveBeenCalledTimes(1));
    expect(onPublish).toHaveBeenCalledWith({ thumbnail: null, price: 2_147_483_647, publishedAt: null });
  });

  it('기존 판매가를 비우면 작품 기본가 상속을 위한 null을 제출한다', async () => {
    const { onPublish, price } = setup();
    fireEvent.change(price, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: '발행하기' }));
    await waitFor(() => expect(onPublish).toHaveBeenCalledTimes(1));
    expect(onPublish).toHaveBeenCalledWith({ thumbnail: null, price: null, publishedAt: null });
  });
});
