import { z } from 'zod';
import { WORK_STATUS_VALUES } from './workStatus';

// 백엔드 schemas/work.py TAG_NAME_MAX와 같은 값. TagInput의 maxLength도 이걸 쓴다.
export const TAG_NAME_MAX = 50;

// 이메일/비번 스키마는 @d-web/shared의 loginSchema를 재사용(F1 LoginForm에서 직접 import).
// 여기서는 관리자 화면 전용(TOTP 코드) 스키마만 정의.

export const totpSchema = z.object({
  code: z.string().regex(/^[0-9]{6}$/, '6자리 숫자를 입력해 주세요.'),
  remember_device: z.boolean(),
});

export type TotpInput = z.infer<typeof totpSchema>;

// 백엔드 WorkCreate/WorkUpdate(backend/src/schemas/work.py) 검증 범위와 동일하게 맞춘다.
// 클라 검증은 UX 보조이고, 최종 강제는 서버(422).
export const workSchema = z.object({
  title: z.string().min(1, '제목을 입력해 주세요.').max(200, '제목은 200자 이하여야 합니다.'),
  synopsis: z.string(),
  // error(타입 에러 문구)를 지정하지 않으면 입력란을 비웠을 때 RHF의 valueAsNumber가 넘기는
  // NaN이 zod의 영문 기본 메시지("expected number, received NaN")로 그대로 노출된다.
  episode_base_price: z
    .number({ error: '숫자를 입력해 주세요.' })
    .int('정수만 입력해 주세요.')
    .min(0, '0 이상이어야 합니다.'),
  bundle_discount_rate: z
    .number({ error: '숫자를 입력해 주세요.' })
    .min(0, '0~1 사이 값이어야 합니다.')
    .max(1, '0~1 사이 값이어야 합니다.'),
  status: z.enum(WORK_STATUS_VALUES),
  is_published: z.boolean(),
  tag_names: z.array(z.string().min(1).max(TAG_NAME_MAX)),
});

export type WorkInput = z.infer<typeof workSchema>;

// 발행하기 모달 전용 검증. 회차번호는 서버가 자동 할당(입력 없음), 제목/부제는 캔버스 인라인,
// is_free는 서버가 유료 경계에서 파생 - 그래서 사용자가 입력하는 값은 판매가·공개 시점뿐이다.
// 판매가는 유료 분량이 있을 때만 노출되고, 비우면 작품 기본가를 쓴다(null 전송).
// mode=now = is_published:true 즉시 공개, mode=schedule = published_at만 전송(E1 스케줄러 대기).
export const episodePublishSchema = z
  .object({
    mode: z.enum(['now', 'schedule']),
    price: z
      .number({ error: '숫자를 입력해 주세요.' })
      .int('정수만 입력해 주세요.')
      .min(0, '0 이상이어야 합니다.')
      .nullable(),
    // datetime-local 값(로컬 naive 문자열). 예약 모드일 때만 의미 - 제출 시 offset 포함 ISO로 변환.
    publishedAt: z.string().nullable(),
  })
  .superRefine((val, ctx) => {
    if (val.mode !== 'schedule') return;
    if (!val.publishedAt) {
      ctx.addIssue({ code: 'custom', path: ['publishedAt'], message: '공개 일시를 선택해 주세요.' });
      return;
    }
    // 과거 시각은 서버가 다음 tick에 즉시 공개해 "지금 공개"와 구분이 안 되므로 미래만 허용한다.
    if (new Date(val.publishedAt).getTime() <= Date.now()) {
      ctx.addIssue({ code: 'custom', path: ['publishedAt'], message: '미래 시각을 선택해 주세요.' });
    }
  });

export type EpisodePublishInput = z.infer<typeof episodePublishSchema>;
