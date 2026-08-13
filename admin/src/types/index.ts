// 이 파일은 손으로 고치지 않는다 - `api.gen.ts`(openapi-typescript 생성물) 위에 얹는
// 얇은 별칭 레이어일 뿐이다. `components['schemas'][...]` 같은 중첩 경로 대신 기존
// 코드가 쓰던 이름을 그대로 유지해 호출부 변경 없이 codegen을 도입한다.
//
// 백엔드 스키마(backend/src/schemas, models)가 바뀌면:
//   pnpm --filter admin generate:types
// 를 돌려 api.gen.ts를 재생성한 뒤, 여기 별칭이 여전히 맞는지 확인할 것.

import type { components } from './api.gen';

export type Role = components['schemas']['RoleEnum'];
export type UserRead = components['schemas']['UserRead'];
export type AdminLoginResponse = components['schemas']['AdminLoginResponse'];
export type TotpSetupResponse = components['schemas']['TotpSetupResponse'];

export type Tag = components['schemas']['TagRead'];
export type WorkStatus = components['schemas']['WorkStatus'];
export type Work = components['schemas']['WorkRead'];
export type WorkCreate = components['schemas']['WorkCreate'];
export type WorkUpdate = components['schemas']['WorkUpdate'];

// AdminEpisodeRead의 Admin 접두사는 독자 라우터 오용 방지용(백엔드 명명) -
// admin SPA 안에서는 전부 관리자 문맥이라 짧은 이름으로 쓴다.
export type Episode = components['schemas']['AdminEpisodeRead'];
export type EpisodeCreate = components['schemas']['EpisodeCreate'];
export type EpisodeUpdate = components['schemas']['EpisodeUpdate'];
// 편집본 봉투(#86) - 공개 회차의 임시저장은 content 대신 이걸 PUT한다.
export type EpisodeDraft = components['schemas']['EpisodeDraft'];
export type EpisodeImageUrl = components['schemas']['EpisodeImageUrl'];

// 본문(TipTap/ProseMirror JSON 문서). 백엔드 content는 dict[str, Any]라 codegen이
// 열린 레코드로 뽑는다 - 에디터는 TipTap의 JSONContent로 다루므로 경계에서 캐스팅한다.
export type ContentDoc = components['schemas']['AdminEpisodeRead']['content'];

// PR2 인계 계약(IMPLEMENTATION_COMMISSION_API.md): 재배열·삭제 PUT은 sample_image_keys 기준,
// 렌더는 sample_images(key·URL 쌍) 기준.
export type CommissionItem = components['schemas']['AdminCommissionItemRead'];
export type CommissionItemCreate = components['schemas']['CommissionItemCreate'];
export type CommissionItemReorder = components['schemas']['CommissionItemReorder'];
export type CommissionItemUpdate = components['schemas']['CommissionItemUpdate'];
export type CommissionSampleImage = components['schemas']['CommissionSampleImage'];

export type SiteTextKey = components['schemas']['SiteTextSlotKey'];
export type SiteText = components['schemas']['SiteTextRead'];
export type SiteTextUpdate = components['schemas']['SiteTextUpdate'];
export type ArtistProfile = components['schemas']['ArtistProfileRead'];
export type ArtistProfileUpdate = components['schemas']['ArtistProfileUpdate'];
