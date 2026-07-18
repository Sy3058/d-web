import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkForm } from './WorkForm';

describe('WorkForm', () => {
  it('기본값은 비공개(is_published=false)로 제출된다', async () => {
    const onSubmit = vi.fn();
    render(<WorkForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />);

    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '테스트 작품' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const [data] = onSubmit.mock.calls[0];
    expect(data.is_published).toBe(false);
  });

  it('공개 상태를 공개로 바꾸면 is_published=true로 제출된다', async () => {
    const onSubmit = vi.fn();
    render(<WorkForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />);

    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '테스트 작품' } });
    // select 값은 문자열이고 스키마는 boolean이라, Controller의 양방향 변환까지 함께 검증한다.
    fireEvent.change(screen.getByRole('combobox', { name: /공개 상태/ }), {
      target: { value: 'true' },
    });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const [data] = onSubmit.mock.calls[0];
    expect(data.is_published).toBe(true);
  });

  it('defaultValues.is_published을 그대로 반영한다 (수정 폼)', async () => {
    const onSubmit = vi.fn();
    render(
      <WorkForm
        defaultValues={{ title: '기존 작품', is_published: true }}
        onSubmit={onSubmit}
        isPending={false}
        error={null}
        submitLabel="저장"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const [data] = onSubmit.mock.calls[0];
    expect(data.is_published).toBe(true);
  });
});
