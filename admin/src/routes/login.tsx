import { useState } from 'react';
import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router';
import type { LoginInput } from '@d-web/shared';
import { LoginForm } from '../components/auth/LoginForm';
import { TotpEnroll } from '../components/auth/TotpEnroll';
import { TotpInput } from '../components/auth/TotpInput';
import { describeAuthError, isSessionExpired } from '../lib/api';
import { meQueryOptions, useAdminLogin, useAdminLoginTotp } from '../hooks/useAuth';
import type { TotpInput as TotpInputValue } from '../lib/validation';
import type { UserRead } from '../types';

export const Route = createFileRoute('/login')({
  beforeLoad: async ({ context }) => {
    // 이미 유효한 owner 세션이면 로그인 폼을 다시 보여줄 이유가 없다.
    // 실패(미인증)는 이 화면의 정상 경로라 그대로 진행한다.
    let user: UserRead | null;
    try {
      user = await context.queryClient.fetchQuery(meQueryOptions);
    } catch {
      user = null;
    }
    if (user?.role === 'owner') {
      throw redirect({ to: '/' });
    }
  },
  component: LoginPage,
});

type Stage = 'credentials' | 'totp' | 'totp_setup';

const EXPIRED_NOTICE = '로그인 대기 시간이 만료됐습니다. 처음부터 다시 로그인해 주세요.';

function LoginPage() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<Stage>('credentials');
  const [notice, setNotice] = useState<string | null>(null);
  const login = useAdminLogin();
  const loginTotp = useAdminLoginTotp();

  // 1->2단계 운반용 pending 서명쿠키는 10분이면 만료된다. 그 뒤 코드를 제출하면 401이
  // 오는데, 단계를 그대로 두면 사용자는 영영 통과 못 하는 폼에 갇힌다(새로고침 외 탈출구
  // 없음) - 1단계로 되돌리고 이유를 알린다.
  const resetToCredentials = () => {
    setStage('credentials');
    setNotice(EXPIRED_NOTICE);
  };

  const handleCredentials = (data: LoginInput) => {
    setNotice(null);
    login.mutate(data, {
      onSuccess: (res) => {
        // stage==='complete'(신뢰 기기라 TOTP 생략, 이미 인증 쿠키 발급됨)는 렌더링
        // 대상이 아니라 즉시 이탈 신호 - 로컬 Stage 타입에도 포함하지 않는다.
        if (res.stage === 'complete') {
          navigate({ to: '/' });
          return;
        }
        setStage(res.stage);
      },
    });
  };

  const handleTotp = (data: TotpInputValue) => {
    loginTotp.mutate(data, {
      onSuccess: () => navigate({ to: '/' }),
      onError: (err) => {
        if (isSessionExpired(err)) resetToCredentials();
      },
    });
  };

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4">
      <h1 className="text-2xl font-bold">관리자 로그인</h1>
      {notice && <p className="text-sm text-amber-700">{notice}</p>}
      {stage === 'credentials' && (
        <LoginForm
          onSubmit={handleCredentials}
          isPending={login.isPending}
          error={login.isError ? describeAuthError(login.error) : null}
        />
      )}
      {stage === 'totp' && (
        <TotpInput
          onSubmit={handleTotp}
          isPending={loginTotp.isPending}
          error={loginTotp.isError ? describeAuthError(loginTotp.error) : null}
        />
      )}
      {stage === 'totp_setup' && (
        <TotpEnroll onComplete={() => navigate({ to: '/' })} onExpired={resetToCredentials} />
      )}
    </main>
  );
}
