# Frontend 지침

- 이 디렉터리 작업에는 루트 `AGENTS.md`와 이 파일을 함께 적용한다.
- Astro 페이지·SSR/SSG·`prerender`·env·라우팅·설정·통합 작업 전에 `docs/guides/GUIDE_ASTRO.md`를 읽고, 버전 민감한 API는 Astro 공식 문서에서 재확인한다.
- `.astro`는 정적 콘텐츠와 레이아웃에, React island는 실제 클라이언트 상호작용에만 사용한다.
- 인증이 필요한 클라이언트 요청은 `credentials: "include"`를 사용한다. JWT localStorage 저장을 금지한다.
- 로그인별 개인 데이터를 공유 캐시되는 SSR HTML에 넣지 않는다. 개인 데이터는 인증된 클라이언트 요청 또는 명시적인 비공개 SSR 응답으로 처리한다.
- 뷰어 콘텐츠는 서버가 허용 범위를 확정해 발급한 URL만 사용하며, 유료 구간 키가 미구매 응답에 섞이지 않게 한다.
- 검증은 `pnpm --filter frontend astro check`, `pnpm --filter frontend test`, `pnpm --filter frontend build`를 변경 범위에 맞게 실행한다.
- 리뷰 시 `docs/reviews/CODE_REVIEW_FE.md`와 `docs/reviews/GUIDE_REVIEW.md`를 읽는다.
