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
