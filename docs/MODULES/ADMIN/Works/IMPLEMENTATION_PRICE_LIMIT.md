# Admin 가격 정수 상한 (M3 Q2)

구현일: 2026-11-11

서버 가격 DTO가 PostgreSQL Integer 상한을 강제하는 계약에 맞춰 관리자 입력도
0 이상 2,147,483,647 이하의 정수만 제출한다. 클라이언트 검증은 입력 피드백이며
최종 가격 검증과 구매 금액 결정은 서버가 담당한다.

## 변경

- `admin/src/lib/validation.ts`의 `PRICE_MAX`를 작품 기본가와 회차 발행 판매가 스키마에서 공유한다.
- `WorkForm`과 `PublishModal`의 숫자 입력에 같은 상한을 지정한다. 기존 `noValidate`와 Zod 검증 흐름을 유지해 초과 입력에 한국어 필드 오류를 표시한다.
- 작품 등록 기본가 500원, 수정 폼의 기존 가격, 회차 가격을 비웠을 때 `null`로 작품 기본가를 상속하는 계약은 유지한다.
- 공개 시점, 판매 상태, 결제 intent 정책은 변경하지 않는다.

## 검증

2026-11-11 `/tmp/d-web-admin-price-limit`에서 확인했다.

- 집중 폼 테스트: 2파일 14개 통과. 작품 등록·수정과 발행 모달의 상한 초과 제출 차단·한국어 오류, 경계값 제출, 회차 가격 null 상속을 검증한다.
- `pnpm --filter admin lint`: 통과.
- `pnpm --filter admin test`: 21파일 119개 통과. 실행 root는 해당 worktree의 `admin`이다.
- `pnpm --filter admin build`: TypeScript 및 Vite production build 통과.

브라우저 실기능 확인은 사용자 확인 대상으로 남긴다.
