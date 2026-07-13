import { createFileRoute, Outlet, redirect } from '@tanstack/react-router';
import { meQueryOptions } from '../hooks/useAuth';
import type { UserRead } from '../types';

export const Route = createFileRoute('/_auth')({
  beforeLoad: async ({ context }) => {
    let user: UserRead;
    try {
      // ensureQueryData가 아니라 fetchQuery다: ensureQueryData는 캐시가 있으면
      // staleTime과 무관하게 그 값을 그대로 반환해(query-core queryClient.js) 만료·강등된
      // 세션도 통과시킨다. fetchQuery는 staleTime(0)을 존중해 매 진입 시 서버에 되묻는다.
      user = await context.queryClient.fetchQuery(meQueryOptions);
    } catch {
      throw redirect({ to: '/login' });
    }
    // 인증(로그인됨)과 인가(owner 권한)는 별개 체크 - reader도 /auth/me는 200을 받으므로
    // role 확인 없이 통과시키면 일반 계정이 관리자 화면에 들어온다.
    if (user.role !== 'owner') {
      throw redirect({ to: '/login' });
    }
  },
  component: () => <Outlet />,
});
