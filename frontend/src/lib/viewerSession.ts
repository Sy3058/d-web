import { getMe } from './auth';
import { isLoggedIn } from './viewer';

// 표시용 힌트는 복구 시도만 결정한다. 공용 API의 refresh 정책을 포함한 getMe의
// 결과와 오류를 그대로 사용한다. 최종 401만 익명으로 계속하고 복구 장애는 전파한다.
export async function restoreViewerSession(cookieString: string): Promise<void> {
  if (isLoggedIn(cookieString)) await getMe();
}
