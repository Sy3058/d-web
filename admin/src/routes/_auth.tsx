import { createFileRoute, Outlet, redirect } from '@tanstack/react-router';
import { meQueryOptions } from '../hooks/useAuth';
import type { UserRead } from '../types';

export const Route = createFileRoute('/_auth')({
  beforeLoad: async ({ context }) => {
    // 세션이 무효(401)거나 권한이 부족(reader)해 로그인 화면으로 돌려보낼 때는 캐시된
    // 유저 정보까지 비운다. 안 그러면 useMe 구독 화면이 이전 로그인 상태로 남고, 다음에
    // 다른 계정으로 로그인해도 직전 계정 데이터가 잠깐 비친다. useLogout과 동일한 이유로
    // clear를 쓴다: setQueryData(key, undefined)는 TanStack이 no-op으로 무시한다.
    const bounceToLogin = () => {
      context.queryClient.clear();
      return redirect({ to: '/login' });
    };

    let user: UserRead;
    try {
      // ensureQueryData가 아니라 fetchQuery다: ensureQueryData는 캐시가 있으면
      // staleTime과 무관하게 그 값을 그대로 반환해(query-core queryClient.js) 만료·강등된
      // 세션도 통과시킨다. fetchQuery는 staleTime(0)을 존중해 매 진입 시 서버에 되묻는다.
      user = await context.queryClient.fetchQuery(meQueryOptions);
    } catch {
      // 401뿐 아니라 500·네트워크 오류(TypeError)도 여기로 떨어져 만료와 동일 취급된다 - 개선 #97
      throw bounceToLogin();
    }
    // 인증(로그인됨)과 인가(owner 권한)는 별개 체크 - reader도 /auth/me는 200을 받으므로
    // role 확인 없이 통과시키면 일반 계정이 관리자 화면에 들어온다.
    if (user.role !== 'owner') {
      throw bounceToLogin();
    }
  },
  component: () => <Outlet />,
});
