# M3 F3 FE 구매자 뷰어 진입

## 범위

PR #144의 viewer-bootstrap API를 독자 뷰어에 연결한다. 공개 작품·회차는 기존 SSR 메타와 60초 공유 캐시를 유지한다. 공개 catalog에서 작품이나 회차를 찾지 못한 경우에는 일반 비공개 구매일 수 있으므로 메타 없는 client-only 셸에서 세션 복구와 bootstrap 인가를 수행한다. 결제 UI·구매 목록·환불은 후속 범위다.

BE·FE 브랜치는 분리한다. 이 작업은 `fe/feat/m3-viewer-entry-f3`이며 BE 서비스·스키마·생성 타입은 변경하지 않는다.

## SSR과 개인 메타 경계

`works/[id]/[publicId].astro`는 공개 조회에 성공한 회차의 기존 Viewer 셸을 유지한다. 회차를 찾지 못하면 `work`를 비우고 generic 제목과 `ViewerEntry`의 경로 식별자만 직렬화한다. 이 셸은 존재나 구매 여부를 확정하지 않는 HTTP 200/no-store다. 비공개 작품·회차·이웃 제목, 내부 episode UUID, 구매 여부와 presigned URL은 SSR HTML에 넣지 않는다.

SSR은 쿠키를 공개 catalog로 전달하지 않으며 bootstrap·인증·본문 API도 호출하지 않는다. `ViewerEntry`의 `useEffect`가 브라우저에서만 `document.cookie`의 힌트를 읽고 세션 복구 후 no-store bootstrap을 호출한다. bootstrap의 404는 메타 없는 찾을 수 없음 UI로 끝나며 Viewer와 content 요청을 시작하지 않는다. 셸 200을 구매 인가 성공으로 사용하지 않는다.

잘못된 8자리 public ID는 API 조회 없이 404/no-store다. catalog의 5xx·네트워크 장애는 구매 fallback으로 바꾸지 않는다. `applyCatalogCache`는 error와 빈 결과가 함께 있어도 503/no-store를 우선하여 기존 503→404 오분류를 수정했다. 공용 helper를 사용하는 다른 공개 페이지에도 같은 장애 분류가 적용된다.

## 세션 복구와 본문 연결

`restoreViewerSession`은 표시용 `login_hint`가 있을 때 기존 `getMe`와 공용 API wrapper를 사용한다. access 만료의 401은 공용 refresh·인증 재시도를 마친 뒤 bootstrap 또는 content를 요청한다. 최종 401의 익명 결과가 전문 권한을 만들지는 않는다. 실제 구매·환경·문서 권한과 전문 서명은 계속 BE의 중앙 정책과 F2 발급 경계가 결정한다.

리뷰에서 `me 401 → refresh 503/네트워크 실패`도 원래 401로 바뀌어 구매자가 찾을 수 없음이나 preview로 오인되는 Major를 확인했다. 공용 wrapper는 refresh의 401만 세션 종료로 처리하고 그 외 오류를 그대로 전파한다. 복구 장애 때 bootstrap·본문을 요청하지 않고 오류 UI에서 명시적으로 재시도한다. 공용 in-flight Promise는 실패 뒤에도 해제하며, 기존 동시 요청 공유·탭 간 직렬화·1회 재시도 정책을 유지한다. 이 변경은 FE 진입의 직접 의존성인 `packages/shared`에 적용하며 BE 쿠키 보완과 분리한다.

bootstrap 성공 후 전달받은 UUID와 허용된 네비로 기존 Viewer를 mount한다. `initialSessionReady`는 직전에 끝낸 복구를 최초 content 요청에만 재사용하는 최적화다. 회차 전환·재시도·이미지 URL 재발급에서는 현재 쿠키로 다시 복구한다. 공개 경로의 Viewer도 최초 content 전에 effect 안에서 복구하여 만료 access 때문에 구매자가 preview에 머물지 않게 한다.

ViewerEntry는 경로에 key를 부여하고 이전 요청의 늦은 결과를 폐기한다. 공개 Viewer도 세션 복구 중 unmount되면 content를 요청하지 않는다. 다른 회차의 본문·메타를 새 경로에 표시하지 않는다. 개인 상태나 토큰을 영속 클라이언트 저장소에 추가하지 않는다.

## 검증

2026-11-09 최종 FE 자동 gate:

- `pnpm --filter frontend lint` 통과.
- `pnpm --filter frontend astro check`: 73 files, 오류·경고 0. 기존 `buildWorksUrl` 미사용 hint 1개 유지.
- `pnpm --filter frontend test`: **17 files, 162 passed**. 실제 Viewer와 raw fetch 응답을 조합해 세션 복구→bootstrap→full 이미지·네비 렌더, 비구매 404의 content 요청 0, 공개 구매 refresh, 게스트·stale hint preview, 오류 재시도, 회차 변경·이미지 재발급과 늦은 응답 격리를 검증했다. 리뷰 회귀 4개는 refresh 503·네트워크 장애 전파와 후속 복구, 공개·비공개 오류 UI 및 재시도를 포함한다.
- `pnpm --filter frontend build` 통과. 기존 Sentry auth token 미설정으로 소스맵 업로드를 건너뛰는 경고와 Astro transitions sourcemap 경고 유지.
- 빌드 후 `pnpm --filter frontend test:ssr`: **6 passed**. Node adapter의 실제 HTTP 응답에서 공개 캐시, 비공개·공개 목록 누락 회차의 메타 없는 셸, 503 분류, 무효 ID와 SSR 쿠키·개인 API 요청 없음을 검증한다. 외부 서비스 대신 임시 로컬 API를 사용하며 종료 시 서버를 닫는다. 로컬 실행 환경에 따라 loopback listen 권한이 필요하다.
- 공용 wrapper 수정의 영향 검증: Admin lint·115개 테스트·build 통과.
- CI Frontend job의 기존 build·Vitest 뒤에 같은 `test:ssr` 명령을 추가했다. 이 FE 브랜치는 아직 commit·push하지 않아 원격 CI 결과는 없다.
- `git diff --check`, 변경 파일 U+2014 금지, 문서 상대 링크 검사로 마감한다. 에이전트는 브라우저를 실행하지 않았다.

2026-11-10 로컬 확인: 사용자가 테스트 구매 계정으로 공개 회차의 무료·유료 텍스트와 이미지가 모두 보이는 것을 확인했다. 같은 회차를 일반 비공개로 전환한 뒤 공개 목록에서 숨겨지는 동작도 확인했다. API 검증에서는 공개 catalog 제외, 비구매 bootstrap·content 404, 기존 구매자 bootstrap 200과 content full을 확인했다. 테스트 구매와 비공개 전환은 개발 DB 데이터이며 PR 코드에 포함하지 않는다. 모바일 화면·비공개 진입의 브라우저 전체 흐름·실제 결제창은 별도 확인 대상이다. 구매 내역 UI와 비공개 구매 회차의 내역 직접 링크는 M3 후속으로 기록했다.

Astro의 응답 상태·온디맨드 렌더링은 [공식 API 문서](https://docs.astro.build/en/reference/api-reference/)와 [공식 SSR 가이드](https://docs.astro.build/en/guides/on-demand-rendering/)를 확인했다. dependency·환경변수·배포 구성은 변경하지 않는다.

## 분리한 BE 후속

현재 `/auth/refresh`의 쿠키 청소는 M3 결정 5와 구현이 다르다. missing/InvalidToken 401은 쿠키를 지우지 않고 TokenReuse 경로도 주입된 Response를 수정한 뒤 HTTPException을 던져 헤더 전달이 보장되지 않는다. 공용 API wrapper의 오류 분류는 이 FE 변경에서 보완했으며 refresh의 최종 401만 인증 실패로 처리한다.

사용자 지시대로 FE를 먼저 완료했다. 이후 승인된 `be/fix/refresh-cookie-cleanup` 별도 worktree에서 BE 보완도 구현·검증했으며 아직 미커밋·미머지다. 이 FE 브랜치의 Backend 원본은 바꾸지 않았다. 기존 stale hint 회귀는 쿠키 삭제가 없는 입력을 유지한다. 현재 stale hint가 남으면 공개 preview 뒤 진행도 요청·추가 refresh가 발생할 수 있음을 실제 동작대로 단언한다. 비공개 미인가 응답에는 메타·본문을 노출하지 않는다. 이 FE 변경만으로 쿠키 3종 삭제를 구현했다고 표시하지 않는다. 별도 BE 보완은 실제 ASGI Set-Cookie·DB 테스트 13개와 Backend 전체 1,045개가 통과했다. FE에는 그 삭제 응답을 브라우저가 적용했을 때 진행도 요청·추가 refresh 없이 preview로 끝나는 호환성 테스트도 추가했다. F 그룹 전체 완료로 판정하지 않는다.
