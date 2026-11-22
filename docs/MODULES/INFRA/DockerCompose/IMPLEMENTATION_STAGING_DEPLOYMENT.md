# IMPLEMENTATION - 첫 VPS 스테이징 배포 구성

2026-11-23. M0 D3/D4의 설정 준비다. 실제 VPS 실행·공개 HTTPS·release 승격과 CI/CD 자동화는 완료하지 않았다.

## 변경과 이유

- `deploy/compose.yml`은 로컬 Compose와 독립된 `dweb-staging` 프로젝트다. API·DB·frontend·admin 포트를 publish하지 않고 Caddy TCP 80/443만 공개한다. 로컬 포트 매핑이 merge로 남는 문제를 피한다.
- `release`의 전체 SHA로 세 앱 이미지를 구분한다. 첫 수동 기동은 서버에서 동일 소스를 빌드하며, 빌드·승격·CI 성공 확인은 [배포 절차](../../../../deploy/README.md)에 명시한다. SHA 문자열이나 CI 결과를 Compose 자체가 검증하지는 않는다.
- PostgreSQL healthy 뒤 같은 API 이미지의 일회성 `migrate`가 `alembic upgrade head`를 실행한다. `service_completed_successfully`가 아니면 API는 시작하지 않는다. 단일 API 프로세스로 기존 내부 스케줄러를 유지한다.
- API Dockerfile에 Alembic 설정·migration을 넣고 `USER app`을 적용했다. root가 설치한 가상환경에서 uvicorn을 직접 실행해 비root 런타임의 uv sync·cache 쓰기를 피한다.
- frontend/admin 공개 API URL은 Docker build ARG로 주입한다. Astro SSR만 `API_INTERNAL_URL=http://api:8000`을 실행 시 사용한다. 비밀값을 빌드 ARG로 전달하지 않는다.
- backend secret은 저장소 밖의 `backend.env`, Compose 변수는 저장소 밖의 `deploy.env`에서 읽는다. `.env.*`와 `*.env`도 Docker context에서 제외한다. 루트 ignore와 backend 전용 ignore 모두 적용했다.
- `ENV=production`으로 Secure 쿠키를 사용하고 결제 provenance는 `test`로 고정한다. 신규 결제는 기본 false이며 별도 검증 전에는 켜지 않는다.
- Caddy는 환경변수 호스트와 이메일로 자동 HTTPS를 구성한다. API로 전달하는 XFF는 실제 peer 주소로 덮어쓴다. Cloudflare 프록시 신뢰 설정은 추가하지 않았다. 최초 DNS only 조건이다.
- Caddy는 127.0.0.1:2019 관리 API로 readiness를 검사한다. 공개 호스트와 다른 localhost 요청의 HTTPS 리다이렉트·인증서에 의존하지 않는다. 관리자 nginx는 IPv4 loopback으로 검사해 localhost가 ::1로 해석되는 실패를 피한다.
- 인증서·DB는 named volume에 보존하고 로그는 크기·파일 수를 제한한다. 인증용 URL 쿼리의 노출을 줄이기 위해 Caddy access log는 활성화하지 않았다.

## 검증

- backend format/lint 통과, pytest 1,248개 통과.
- frontend lint/check/test/build 통과, 테스트 377개. 기존 unused import hint와 sourcemap·Sentry token 경고는 남아 있다.
- admin lint/test/build 통과, 테스트 139개.
- 더미 host·secret으로 세 Docker 이미지를 실제 빌드했다. 실 운영값은 사용하지 않았다.
- Compose 렌더와 외부 포트·migration 의존성·테스트 결제 모드·공개/내부 API 주소를 검사했다. 필수 변수 7종을 각각 제거했을 때 렌더 실패를 확인했다.
- 기존 로컬 DB와 별도 프로젝트·볼륨에서 migration exit 0과 `f2a7b8c9d0e1 (head)`, API UID 999, 세 앱 healthy를 확인했다. 내부 `/works` API와 SSR `/works`는 200이었다.
- 빈 DB 홈의 503·no-store는 `landing_intro` 초기 저장 전 동작이다. 이 응답을 프로세스 readiness로 사용하지 않는다.
- Caddy adapt/validate와 별도 network none 컨테이너의 내부 readiness를 확인했다. 최종 Compose 검증에서는 Caddy의 네트워크·공개 포트를 override로 제거하고 전체 `up --wait` 성공과 5개 상시 서비스 healthy·migration exit 0을 확인했다. 공인 DNS에 인증서를 발급하거나 VPS를 변경하는 검증은 하지 않았다.

## 남은 작업

- Astro `GHSA-r3h5-4585-7x3w`는 PR #163의 develop 병합 커밋 `afbb889`와 `astro@7.4.7` 잠금을 이 배포 브랜치에 반영했다. release 승격과 새 이미지의 실제 배포 반영은 후속이다.
- 사용자 승인 후 commit/push·develop PR·release 승격, 해당 SHA CI 결과 확인.
- VPS에 release 소스와 제한된 환경 파일 준비, 공개 HTTPS·브라우저 로그인·콘텐츠·테스트 결제 확인.
- 레지스트리, CI 성공 후 이미지 발행·배포 자동화, DB R2 백업·복구 및 모니터링.

문서의 수동 백업·이미지 복구는 아직 실제 사용자 데이터로 검증하지 않았다. 스키마 migration은 forward-only이며 이전 이미지로 바꿔도 DB가 되돌아가지 않는다.

## Astro 수정 통합 후 재검증 (2026-11-23)

- 미커밋 배포 설정을 백업하고 Git autostash로 보존한 상태에서 `origin/develop`의 `afbb889`까지 fast-forward했다. 마일스톤 문서 충돌 한 곳은 보안 수정과 서버 준비 기록을 모두 유지해 해결했다. autostash와 파일 백업은 복구용으로 보존했다.
- 같은 잠금 파일의 CI·깨끗한 worktree·Docker는 통과했지만 기존 로컬 설치의 hidden-hoist Zod 링크가 4.6.7을 가리켜 앱의 4.4.3 schema와 충돌했다. 기존 node_modules를 백업하고 frozen offline 설치로 재구성해 해결했다. 의존성·애플리케이션 코드 우회 수정은 하지 않았다.
- 통합 상태의 frontend lint/check/test/build(377개), admin lint/test/build(139개)가 통과했다. 세 배포 이미지를 더미 공개 API 주소로 다시 빌드했고, 실제 frontend 이미지의 HTTP SSR·보안 회귀 검사 20개가 통과했다.
- 외부 포트와 Caddy 외부 네트워크를 차단한 임시 프로젝트에서 빈 DB migration exit 0과 다섯 상시 서비스 healthy를 다시 확인했다. 실제 VPS 배포·공개 인증서·쿠키 로그인은 아직 미검증이다.
