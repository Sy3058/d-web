import { useState } from 'react';
import { api, ApiError } from '../../lib/api';

export default function LogoutButton() {
  const [loading, setLoading] = useState(false);

  async function handleLogout() {
    setLoading(true);
    try {
      await api.post('/auth/logout', {});
    } catch (err) {
      if (!(err instanceof ApiError)) {
        // 네트워크 오류도 로그아웃으로 처리
      }
    } finally {
      window.location.href = '/';
    }
  }

  return (
    <button
      type="button"
      onClick={handleLogout}
      disabled={loading}
      className="text-sm text-muted underline underline-offset-4 hover:text-ink disabled:opacity-50"
    >
      {loading ? '처리 중...' : '로그아웃'}
    </button>
  );
}
