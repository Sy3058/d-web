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
export type EpisodeImageUrl = components['schemas']['EpisodeImageUrl'];

// 본문(TipTap/ProseMirror JSON 문서). 백엔드 content는 dict[str, Any]라 codegen이
// 열린 레코드로 뽑는다 - 에디터는 TipTap의 JSONContent로 다루므로 경계에서 캐스팅한다.
export type ContentDoc = components['schemas']['AdminEpisodeRead']['content'];
