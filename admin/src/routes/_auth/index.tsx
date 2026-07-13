import { useEffect } from 'react';
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { describeAuthError } from '../../lib/api';
import { useLogout, useMe } from '../../hooks/useAuth';

export const Route = createFileRoute('/_auth/')({
  component: Dashboard,
});

function Dashboard() {
  const navigate = useNavigate();
  const { data: user, isError: meFailed } = useMe();
  const logout = useLogout();

  // 가드(beforeLoad)는 라우트 진입 때만 돈다. 머무는 동안 세션이 만료되면(access 15분)
  // useMe가 401로 실패하는데, useQuery는 마지막 성공 데이터를 계속 들고 있어 화면이
  // 로그인 상태처럼 남는다 - 그때는 로그인 화면으로 돌려보낸다.
  useEffect(() => {
    if (meFailed) {
      navigate({ to: '/login' });
    }
  }, [meFailed, navigate]);

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSuccess: () => navigate({ to: '/login' }),
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-2xl font-bold">관리자 페이지</h1>
      {user && <p className="text-gray-500">{user.nickname}님, 환영합니다.</p>}
      <button
        onClick={handleLogout}
        disabled={logout.isPending}
        className="rounded border border-gray-300 px-3 py-2 disabled:opacity-50"
      >
        {logout.isPending ? '로그아웃 중...' : '로그아웃'}
      </button>
      {logout.isError && (
        <p className="text-sm text-red-600">
          로그아웃하지 못했습니다. {describeAuthError(logout.error)}
        </p>
      )}
    </main>
  );
}
