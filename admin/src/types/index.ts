// ⚠️ 수기 동기화 타입 - 백엔드와의 드리프트를 컴파일러가 잡아주지 못한다.
// admin/CLAUDE.md는 이 파일을 openapi-typescript 산출물로 규정하나 F1에서는 codegen
// 파이프라인 도입을 미뤘다(F2 전 도입). 그때까지 아래 스키마가 바뀌면 이 파일도 함께
// 고칠 것 - 특히 RoleEnum 값이 바뀌면 _auth.tsx의 role 가드가 조용히 오작동한다.
// 원본: backend/src/models/user.py(RoleEnum, UserRead), backend/src/schemas/auth.py

export type Role = 'reader' | 'owner' | 'moderator';

export interface UserRead {
  id: string;
  email: string;
  nickname: string;
  profile_image: string | null;
  is_email_verified: boolean;
  role: Role;
  created_at: string;
}

export interface AdminLoginResponse {
  stage: 'totp' | 'totp_setup' | 'complete';
}

export interface TotpSetupResponse {
  otpauth_uri: string;
}
