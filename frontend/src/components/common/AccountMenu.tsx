import { Menu } from '@base-ui/react/menu';
import { useLayoutEffect, useState } from 'react';
import { api } from '../../lib/api';

interface Props {
  compact?: boolean;
  visible?: boolean;
}

const itemClass =
  'flex min-h-11 cursor-pointer items-center rounded-control px-3 text-sm outline-none data-highlighted:bg-hover data-disabled:pointer-events-none data-disabled:opacity-50';

export default function AccountMenu({ compact = false, visible = true }: Props) {
  const [nickname, setNickname] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useLayoutEffect(() => {
    const updateLoginHint = () => {
      const hint = document.cookie.split(';').map((entry) => entry.trim())
        .find((entry) => entry.startsWith('login_hint='));
      try {
        setNickname(hint ? decodeURIComponent(hint.slice('login_hint='.length)) : '');
      } catch {
        setNickname('');
      }
      setOpen(false);
    };
    updateLoginHint();
    window.addEventListener('focus', updateLoginHint);
    return () => window.removeEventListener('focus', updateLoginHint);
  }, [visible]);

  async function handleLogout() {
    if (loading) return;
    setLoading(true);
    try {
      await api.post('/auth/logout', {});
    } catch {
      // 기존 로그아웃 버튼과 같이 실패한 요청 뒤에도 홈으로 이동한다.
    } finally {
      window.location.href = '/';
    }
  }

  const triggerClass = `inline-flex min-h-11 min-w-11 max-w-[25vw] shrink-0 items-center justify-center rounded-control px-2 font-medium text-ink hover:bg-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink cursor-pointer ${compact ? 'text-xs' : 'text-sm'}`;

  if (!nickname) {
    return (
      <a href="/auth/login" className={triggerClass} aria-label="로그인 화면으로 이동" data-astro-reload>
        로그인
      </a>
    );
  }

  return (
    <Menu.Root open={open && visible} onOpenChange={setOpen}>
      <Menu.Trigger className={triggerClass} aria-label={`${nickname} 계정 메뉴`}>
        <span className="truncate">{nickname}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={6} className="z-[60]">
          <Menu.Popup className="min-w-40 rounded-control border border-line bg-paper p-1 shadow-lg outline-none">
            <Menu.LinkItem href="/my" className={`${itemClass} text-ink`} data-astro-reload closeOnClick>
              마이페이지
            </Menu.LinkItem>
            <Menu.LinkItem href="/my/purchases" className={`${itemClass} text-ink`} data-astro-reload closeOnClick>
              구매내역
            </Menu.LinkItem>
            <Menu.LinkItem href="/my/settings" className={`${itemClass} text-ink`} data-astro-reload closeOnClick>
              설정
            </Menu.LinkItem>
            <Menu.Separator className="my-1 h-px bg-line" />
            <Menu.Item className={`${itemClass} text-danger`} disabled={loading} onClick={() => void handleLogout()}>
              {loading ? '처리 중...' : '로그아웃'}
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
