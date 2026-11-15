import { Menu } from '@base-ui/react/menu';
import { type ReactNode, useState } from 'react';

interface ActionsMenuProps {
  /** 목록의 행마다 메뉴를 구분하는 접근성 이름. */
  label: string;
  width?: string;
  children: (close: () => void) => ReactNode;
}

export const ACTION_ITEM_CLASS = 'admin-menu-item';

/** 포털 배치, 키보드 이동과 포커스 복귀는 Base UI Menu가 관리한다. */
export function ActionsMenu({ label, width = 'w-32', children }: ActionsMenuProps) {
  const [open, setOpen] = useState(false);

  return (
    <Menu.Root open={open} onOpenChange={setOpen}>
      <Menu.Trigger
        className="admin-control admin-control-ghost admin-control-icon text-lg leading-none"
        aria-label={label}
      >
        ···
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner className="z-50" sideOffset={4} align="end">
          <Menu.Popup className={`admin-menu-popup ${width}`} aria-label={label}>
            {children(() => setOpen(false))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
