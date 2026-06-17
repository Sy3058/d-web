import { z } from 'zod';

export const loginSchema = z.object({
  email: z.email('유효한 이메일을 입력해 주세요.'),
  password: z.string().min(8, '비밀번호는 8자 이상이어야 합니다.'),
});

export type LoginInput = z.infer<typeof loginSchema>;

// 백엔드 SignupRequest 정책과 동일하게 맞춘다(8~128 + 영문·숫자·특수 각 1, nickname 1~50).
// 클라 검증은 UX 보조이고, 최종 강제는 서버(422).
export const signupSchema = z.object({
  email: z.email('유효한 이메일을 입력해 주세요.'),
  password: z
    .string()
    .min(8, '비밀번호는 8자 이상이어야 합니다.')
    .max(128, '비밀번호는 128자 이하여야 합니다.')
    .regex(/[A-Za-z]/, '영문을 1자 이상 포함해야 합니다.')
    .regex(/[0-9]/, '숫자를 1자 이상 포함해야 합니다.')
    .regex(/[^A-Za-z0-9]/, '특수문자를 1자 이상 포함해야 합니다.'),
  nickname: z.string().min(1, '닉네임을 입력해 주세요.').max(50, '닉네임은 50자 이하여야 합니다.'),
});

export type SignupInput = z.infer<typeof signupSchema>;
