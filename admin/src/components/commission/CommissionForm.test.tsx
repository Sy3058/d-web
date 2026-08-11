import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommissionForm } from './CommissionForm';

describe('CommissionForm', () => {
  it('필수값을 채우면 기본값(is_open=true)으로 제출된다', async () => {
    const onSubmit = vi.fn();
    render(
      <CommissionForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />,
    );

    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '캐릭터 커미션' } });
    fireEvent.change(screen.getByLabelText(/가격 표기/), { target: { value: '50,000원~' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const [data] = onSubmit.mock.calls[0];
    expect(data.title).toBe('캐릭터 커미션');
    expect(data.price_text).toBe('50,000원~');
    expect(data.is_open).toBe(true);
  });

  it('슬롯 상태를 마감으로 바꾸면 is_open=false로 제출된다', async () => {
    const onSubmit = vi.fn();
    render(
      <CommissionForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />,
    );

    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '캐릭터 커미션' } });
    fireEvent.change(screen.getByLabelText(/가격 표기/), { target: { value: '50,000원~' } });
    // select 값은 문자열이고 스키마는 boolean이라, Controller의 양방향 변환까지 함께 검증한다
    // (WorkForm is_published 회귀와 같은 함정 - MISTAKES 폼 섹션).
    fireEvent.change(screen.getByRole('combobox', { name: /슬롯 상태/ }), {
      target: { value: 'false' },
    });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].is_open).toBe(false);
  });

  it('defaultValues.is_open=false을 아무 조작 없이 제출해도 그대로 유지된다 (수정 폼)', async () => {
    // WorkForm과 같은 회귀 케이스: register+setValueAs만 쓰면 서버가 false를 줘도 select가
    // 첫 옵션(true)으로 뜨는 함정이 있다(MISTAKES 폼 섹션) - 무조작 제출로 초기 반영을 고정한다.
    const onSubmit = vi.fn();
    render(
      <CommissionForm
        defaultValues={{ title: '기존 카드', price_text: '오마카세', is_open: false }}
        onSubmit={onSubmit}
        isPending={false}
        error={null}
        submitLabel="저장"
      />,
    );

    // 렌더된 select 값까지 단언한다 - 제출값만 보면 시작값(false)=기대값(false)이라 판별력이 없다.
    // 변이 실험 실측: select의 value 바인딩을 빼면 폼 상태는 false인데 화면만 '접수 중'으로 뜨는
    // 회귀가 생기는데, 제출값 단언만으로는 이 케이스가 green으로 통과했다. 회귀의 증상 자체가
    // "서버는 마감인데 화면은 접수 중"이므로 UI 값이 판별 지점이다.
    expect((screen.getByRole('combobox', { name: /슬롯 상태/ }) as HTMLSelectElement).value).toBe(
      'false',
    );
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].is_open).toBe(false);
  });

  it('제목이 비어 있으면 제출되지 않는다', async () => {
    const onSubmit = vi.fn();
    render(
      <CommissionForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />,
    );

    fireEvent.change(screen.getByLabelText(/가격 표기/), { target: { value: '50,000원~' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(screen.getByText('제목을 입력해 주세요.')).toBeInTheDocument());
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
