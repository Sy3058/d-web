import { getMe } from './auth';

// 브라우저와 API가 서로 다른 호스트일 수 있어 document.cookie의 표시용 힌트는
// 인증 판정에 쓰지 않는다. HttpOnly 쿠키를 받는 API 응답만 세션의 원천이다.
export async function restoreViewerSession(): Promise<boolean> {
  return (await getMe()) !== null;
}
