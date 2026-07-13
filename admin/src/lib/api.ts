import { createApi, ApiError, extractDetail } from '@d-web/shared';
export { ApiError, extractDetail } from '@d-web/shared';

// 환경변수 이름은 .env / .env.example의 VITE_API_URL과 정확히 일치해야 한다.
// (VITE_API_BASE_URL로 오타나면 프로덕션에서 조용히 아래 dev 폴백으로 떨어져
//  관리자 SPA가 사용자 브라우저의 localhost를 호출하게 된다.)
export const api = createApi(import.meta.env.VITE_API_URL ?? 'http://localhost:8000');

/** 관리자 로그인/2FA 엔드포인트 공용 에러 문구.
 *
 * 응답이 온 실패(401/400/429)는 HTTPException detail에 완결된 한국어 메시지가 실려 온다.
 * 반면 백엔드 다운·CORS 차단 등은 fetch가 TypeError로 reject하므로 ApiError가 아니다 -
 * 이 둘을 구분하지 않으면 네트워크 장애가 "요청 오류"로 뭉뚱그려져 원인 파악이 막힌다.
 */
export function describeAuthError(err: unknown): string {
  if (err instanceof ApiError) {
    return extractDetail(err) ?? '요청 처리 중 오류가 발생했습니다.';
  }
  return '서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요.';
}

/** pending 서명쿠키(10분) 만료 등으로 로그인 단계를 처음부터 다시 밟아야 하는 실패인지. */
export function isSessionExpired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
