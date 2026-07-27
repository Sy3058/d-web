import { ACTION_ITEM_CLASS, ActionsMenu } from '../common/ActionsMenu';

interface WorkActionsMenuProps {
  onEdit: () => void;
  onDelete: () => void;
  isDeleting: boolean;
}

export function WorkActionsMenu({ onEdit, onDelete, isDeleting }: WorkActionsMenuProps) {
  return (
    <ActionsMenu label="작품 관리 메뉴">
      {(close) => (
        <>
          <button
            type="button"
            onClick={() => {
              close();
              onEdit();
            }}
            className={ACTION_ITEM_CLASS}
          >
            수정
          </button>
          {/* 요청이 끝나기 전에 다시 눌러 같은 작품에 DELETE를 중복 발사하지 않도록 잠근다. */}
          <button
            type="button"
            disabled={isDeleting}
            onClick={() => {
              close();
              onDelete();
            }}
            className={`${ACTION_ITEM_CLASS} text-red-600`}
          >
            {isDeleting ? '삭제 중...' : '삭제'}
          </button>
        </>
      )}
    </ActionsMenu>
  );
}
