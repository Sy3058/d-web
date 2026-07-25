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

  // #84 - 연재 상태 변경 시 공개 상태 "기본값" 연동. 강제가 아니고, 자동으로 켜는 방향
  // (연재중->공개)은 두지 않는다 - 숨기는 방향만 연동한다.

  it('연재 상태를 준비중으로 바꾸면 공개 상태가 비공개로 따라간다', async () => {
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

    fireEvent.change(screen.getByRole('combobox', { name: /연재 상태/ }), {
      target: { value: 'preparing' },
    });
    // UI가 즉시 따라 바뀌고(사용자에게 보이는 기본값 전환), 제출값도 일치해야 한다.
    expect((screen.getByRole('combobox', { name: /공개 상태/ }) as HTMLSelectElement).value).toBe(
      'false',
    );
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    // status도 함께 본다 - is_published만 단언하면 register 래핑이 RHF의 change 핸들러를
    // 삼켜 status가 갱신되지 않는 회귀를 이 파일 어디서도 잡지 못한다.
    expect(onSubmit.mock.calls[0][0].status).toBe('preparing');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(false);
  });

  it('연재중으로 바꿔도 공개 상태를 자동으로 켜지 않는다', async () => {
    const onSubmit = vi.fn();
    render(
      <WorkForm
        defaultValues={{ title: '기존 작품', status: 'preparing', is_published: false }}
        onSubmit={onSubmit}
        isPending={false}
        error={null}
        submitLabel="저장"
      />,
    );

    fireEvent.change(screen.getByRole('combobox', { name: /연재 상태/ }), {
      target: { value: 'ongoing' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].status).toBe('ongoing');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(false);
  });

  it('등록 폼에서 연재 상태를 왕복해도 새 작품은 비공개로 남는다', async () => {
    // 등록 폼 기본값은 status=ongoing + 비공개다. 연동이 연재중->공개까지 했을 때는
    // 상태를 골랐다 되돌리기만 해도 회차 없는 새 작품이 공개로 생성됐다(리뷰에서 실측).
    const onSubmit = vi.fn();
    render(<WorkForm onSubmit={onSubmit} isPending={false} error={null} submitLabel="등록" />);

    fireEvent.change(screen.getByLabelText(/제목/), { target: { value: '새 작품' } });
    const statusSelect = screen.getByRole('combobox', { name: /연재 상태/ });
    fireEvent.change(statusSelect, { target: { value: 'preparing' } });
    fireEvent.change(statusSelect, { target: { value: 'ongoing' } });
    fireEvent.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].is_published).toBe(false);
  });

  it('연동 후 공개 상태를 수동으로 되돌리면 그 값이 제출된다', async () => {
    // 연동은 기본값일 뿐 강제가 아니라는 #84의 중심 주장. 준비중+공개(커밍순 티저)를
    // 만들 수 있어야 한다.
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

    fireEvent.change(screen.getByRole('combobox', { name: /연재 상태/ }), {
      target: { value: 'preparing' },
    });
    fireEvent.change(screen.getByRole('combobox', { name: /공개 상태/ }), {
      target: { value: 'true' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].status).toBe('preparing');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(true);
  });

  // 아래 두 케이스는 짝이다. 공개->공개만 두면 "무조건 공개"로 바뀌는 회귀를, 비공개->
  // 비공개만 두면 "무조건 비공개"로 바뀌는 회귀를 각각 놓친다(시작값=기대값이라 어느
  // 구현이든 통과한다). 양방향을 함께 고정해야 "건드리지 않는다"가 검증된다.

  it('완결로 바꿀 때 공개 상태를 건드리지 않는다 (공개 유지)', async () => {
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

    fireEvent.change(screen.getByRole('combobox', { name: /연재 상태/ }), {
      target: { value: 'completed' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].status).toBe('completed');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(true);
  });

  it('휴재로 바꿀 때 공개 상태를 건드리지 않는다 (비공개 유지)', async () => {
    const onSubmit = vi.fn();
    render(
      <WorkForm
        defaultValues={{ title: '기존 작품', is_published: false }}
        onSubmit={onSubmit}
        isPending={false}
        error={null}
        submitLabel="저장"
      />,
    );

    fireEvent.change(screen.getByRole('combobox', { name: /연재 상태/ }), {
      target: { value: 'hiatus' },
    });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].status).toBe('hiatus');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(false);
  });

  it('초기 로드에서는 연동이 발화하지 않는다 (준비중+공개 = 커밍순 티저 보존)', async () => {
    const onSubmit = vi.fn();
    render(
      <WorkForm
        defaultValues={{ title: '커밍순', status: 'preparing', is_published: true }}
        onSubmit={onSubmit}
        isPending={false}
        error={null}
        submitLabel="저장"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].status).toBe('preparing');
    expect(onSubmit.mock.calls[0][0].is_published).toBe(true);
  });
});
