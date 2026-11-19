import { useEffect, useState } from 'react';
import { getMe, type User } from '../../lib/auth';
import { ghostControl } from '../ui/controlStyles';
import AccountOverview from './AccountOverview';
import PasswordEditor from './PasswordEditor';
import ProfileEditor from './ProfileEditor';

type AccountPage = 'overview' | 'profile' | 'password' | 'settings';
type SessionState =
  | { status: 'loading' | 'anonymous' | 'error' }
  | { status: 'authenticated'; user: User };

export function AccountSettings() {
  return (
    <>
      <h2 className="text-sm font-medium mb-2">알림 설정</h2>
      <p className="text-sm text-muted">알림 설정 기능은 준비 중이에요.</p>
    </>
  );
}

export default function AccountSessionRecovery({ page }: { page: AccountPage }) {
  const [state, setState] = useState<SessionState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;

    void getMe().then(
      (user) => {
        if (active) setState(user ? { status: 'authenticated', user } : { status: 'anonymous' });
      },
      () => {
        if (active) setState({ status: 'error' });
      },
    );

    return () => { active = false; };
  }, [attempt]);

  if (state.status === 'authenticated') {
    switch (page) {
      case 'overview': return <AccountOverview user={state.user} />;
      case 'profile': return <ProfileEditor initialUser={state.user} />;
      case 'password': return <PasswordEditor initialUser={state.user} />;
      case 'settings': return <AccountSettings />;
    }
  }

  if (state.status === 'error') {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-muted">일시적인 오류로 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.</p>
        <button type="button" className={ghostControl} onClick={() => {
          setState({ status: 'loading' });
          setAttempt((count) => count + 1);
        }}>다시 시도</button>
      </div>
    );
  }

  if (state.status === 'anonymous') {
    return (
      <div className="space-y-3">
        <p role="status" className="text-sm text-muted">계정 정보를 보려면 로그인해 주세요.</p>
        <a href="/auth/login" className={ghostControl} data-astro-reload>로그인</a>
      </div>
    );
  }

  return <p role="status" className="text-sm text-muted">로그인 확인 중...</p>;
}
