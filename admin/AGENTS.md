# Admin 지침

- 이 디렉터리 작업에는 루트 `AGENTS.md`와 이 파일을 함께 적용한다.
- 인증 상태는 HttpOnly 쿠키와 메모리 상태로 처리한다. JWT나 TOTP를 localStorage 등 영속 클라이언트 저장소에 넣지 않는다.
- 클라이언트 라우트 가드는 UX 보조일 뿐이다. 실제 owner 권한과 상태 전이는 백엔드가 검증해야 한다.
- API 타입의 진실은 `src/types/api.gen.ts`이며 직접 편집하지 않는다. 백엔드 스키마 변경 후 `pnpm --filter admin generate:types`로 재생성한다.
- 이미지는 R2에 직접 올리지 않는다. draft 생성 후 백엔드 multipart 단건 업로드·변환 경로를 사용한다.
- 순수 메타 수정 PUT에 `is_published`를 에코하지 않는다. 예약은 `published_at`만 보내고, 공개 회차 임시저장은 `draft` 봉투를 사용한다.
- 검증은 `pnpm --filter admin lint`, `pnpm --filter admin test`, `pnpm --filter admin build`를 변경 범위에 맞게 실행한다.
- 리뷰 시 `docs/reviews/CODE_REVIEW_ADMIN.md`, `docs/reviews/GUIDE_REVIEW.md`와 관련 구현 문서를 함께 확인한다. 체크리스트가 최신 결정과 충돌하면 `docs/DECISIONS.md`와 구현 문서를 우선한다.
