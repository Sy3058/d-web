import { z } from 'zod';

// 이메일/비번 스키마는 @d-web/shared의 loginSchema를 재사용(F1 LoginForm에서 직접 import).
// 여기서는 관리자 화면 전용(TOTP 코드) 스키마만 정의.

export const totpSchema = z.object({
  code: z.string().regex(/^[0-9]{6}$/, '6자리 숫자를 입력해 주세요.'),
  remember_device: z.boolean(),
});

export type TotpInput = z.infer<typeof totpSchema>;
