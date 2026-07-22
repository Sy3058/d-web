// 공개 SSR 페이지의 Cache-Control 정책(M2 결정 3)을 한 곳에 모은다.
// - 성공: public, max-age=60 (Caddy/브라우저가 60초 캐시)
// - 5xx 등 일시 장애·404: no-store (일시 장애가 캐시에 눌러붙거나, 예약 공개 전 404가
//   캐시돼 공개 후에도 404를 보는 걸 막는다)
// 페이지마다 직접 세팅하면 정책이 갈라지므로(그룹 F 뷰어 셸도 같은 규칙) 여기서만 관리한다.
// response 타입은 Astro.response(ResponseInit & { readonly headers: Headers })에 맞춰
// status를 optional로 둔다.
export function applyCatalogCache(
  response: { status?: number; headers: Headers },
  outcome: { error?: boolean; notFound?: boolean },
): void {
  if (outcome.error || outcome.notFound) {
    if (outcome.notFound) response.status = 404;
    response.headers.set('Cache-Control', 'no-store');
  } else {
    response.headers.set('Cache-Control', 'public, max-age=60');
  }
}
