import { Menu } from '@base-ui/react/menu';
import { ACTION_ITEM_CLASS, ActionsMenu } from '@/components/common/ActionsMenu';

interface CommissionActionsMenuProps {
  onEdit: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

export function CommissionActionsMenu({
  onEdit,
  onDelete,
  isDeleting,
}: CommissionActionsMenuProps) {
  return (
    <ActionsMenu label="커미션 카드 관리 메뉴">
      {(close) => (
        <>
          <Menu.Item
            render={<button type="button" />}
            nativeButton
            onClick={() => {
              close();
              onEdit();
            }}
            className={ACTION_ITEM_CLASS}
          >
            수정
          </Menu.Item>
          <Menu.Item
            render={<button type="button" />}
            nativeButton
            disabled={isDeleting}
            onClick={() => {
              close();
              onDelete();
            }}
            className={`${ACTION_ITEM_CLASS} text-red-600`}
          >
            {isDeleting ? '삭제 중...' : '삭제'}
          </Menu.Item>
        </>
      )}
    </ActionsMenu>
  );
}
