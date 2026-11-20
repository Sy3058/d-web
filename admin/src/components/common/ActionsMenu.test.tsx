import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { WorkActionsMenu } from '@/components/works/WorkActionsMenu';
import { CommissionActionsMenu } from '@/components/commission/CommissionActionsMenu';

describe('ActionsMenu', () => {
  it('키보드로 항목을 이동하고 Escape로 닫으면 트리거로 포커스를 돌린다', async () => {
    render(<WorkActionsMenu onEdit={vi.fn()} onDelete={vi.fn()} isDeleting={false} />);
    const trigger = screen.getByRole('button', { name: '작품 관리 메뉴' });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
    const edit = await screen.findByRole('menuitem', { name: '수정' });
    await waitFor(() => expect(edit).toHaveFocus());
    fireEvent.keyDown(edit, { key: 'ArrowDown' });
    const remove = screen.getByRole('menuitem', { name: '삭제' });
    await waitFor(() => expect(remove).toHaveFocus());
    fireEvent.keyDown(remove, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it('포털의 커미션 항목을 선택하면 메뉴를 닫고 콜백을 한 번 실행한다', async () => {
    const onEdit = vi.fn();
    const { container } = render(
      <CommissionActionsMenu onEdit={onEdit} onDelete={vi.fn()} isDeleting={false} />,
    );
    fireEvent.click(screen.getByRole('button', { name: '커미션 카드 관리 메뉴' }));
    const menu = screen.getByRole('menu');
    expect(container).not.toContainElement(menu);
    fireEvent.click(screen.getByRole('menuitem', { name: '수정' }));
    expect(onEdit).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('바깥 클릭으로 메뉴를 닫는다', async () => {
    render(<WorkActionsMenu onEdit={vi.fn()} onDelete={vi.fn()} isDeleting={false} />);
    fireEvent.click(screen.getByRole('button', { name: '작품 관리 메뉴' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });

  it('진행 중인 삭제 항목은 비활성화하고 수정은 허용한다', () => {
    const onDelete = vi.fn();
    render(<WorkActionsMenu onEdit={vi.fn()} onDelete={onDelete} isDeleting />);
    fireEvent.click(screen.getByRole('button', { name: '작품 관리 메뉴' }));
    const remove = screen.getByRole('menuitem', { name: '삭제 중...' });
    expect(remove).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('menuitem', { name: '수정' })).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(remove);
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});
