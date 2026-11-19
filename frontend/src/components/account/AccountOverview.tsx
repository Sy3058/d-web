import type { User } from '../../lib/auth';
import { ghostControl } from '../ui/controlStyles';
import { safeProfileImageUrl } from './profileUtils';

export default function AccountOverview({ user }: { user: User }) {
  const profileImage = safeProfileImageUrl(user.profile_image);

  return (
    <div className="space-y-12">
      <section aria-labelledby="profile-heading">
        <h2 id="profile-heading" className="mb-5 border-b border-line pb-3 text-sm font-medium text-ink">프로필</h2>
        <div className="flex items-center gap-3 sm:gap-5">
          <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-full bg-hover text-xl text-muted">
            {profileImage ? (
              <img src={profileImage} alt="프로필 이미지" width="80" height="80" className="h-full w-full object-cover" referrerPolicy="no-referrer" />
            ) : <span aria-label="기본 프로필 이미지">{user.nickname.slice(0, 1)}</span>}
          </div>
          <div className="min-w-0 flex-1">
            <p className="mb-1 text-xs text-muted">닉네임</p>
            <p className="break-words text-sm text-ink">{user.nickname}</p>
          </div>
          <a href="/my/profile" className={`${ghostControl} shrink-0 border border-line`} data-astro-reload>프로필 수정</a>
        </div>
      </section>
      <section aria-labelledby="security-heading">
        <h2 id="security-heading" className="mb-5 border-b border-line pb-3 text-sm font-medium text-ink">계정 보안</h2>
        <div className="mb-7">
          <h3 className="mb-1 text-sm font-medium text-ink">이메일</h3>
          <p className="break-all text-sm text-muted">{user.email}</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-ink">비밀번호</h3>
          {user.role === 'owner' ? (
            <p className="text-sm text-muted">관리자 계정은 이 화면에서 비밀번호를 변경할 수 없어요.</p>
          ) : user.has_password ? (
            <a href="/my/password" className={`${ghostControl} border border-line`} data-astro-reload>비밀번호 변경</a>
          ) : <p className="text-sm text-muted">소셜 로그인으로 관리 중</p>}
        </div>
      </section>
    </div>
  );
}
