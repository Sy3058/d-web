import { useState, useEffect } from 'react';
import { getMe, type User } from '../../lib/auth';

export default function NavUser() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    if (sessionStorage.getItem('session') === 'out') {
      setUser(null);
      return;
    }
    getMe()
      .then(u => {
        if (!u) sessionStorage.setItem('session', 'out');
        setUser(u);
      })
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) return null;

  if (!user) {
    return (
      <a
        href="/auth/login"
        className="text-sm font-medium text-ink tracking-wider hover:underline underline-offset-4"
      >
        로그인
      </a>
    );
  }

  return (
    <a
      href="/my"
      className="text-sm font-medium text-ink tracking-wider hover:underline underline-offset-4"
    >
      {user.nickname}
    </a>
  );
}
