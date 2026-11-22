# develop/release 전환과 첫 VPS 배포

2026-11-22 사용자 결정. 작업은 develop에서 시작하고 release에 승격한 코드만 배포한다. 이 문서는 로컬 준비와 실제 GitHub·서버 반영 상태를 구분한다.

## 현재 준비 상태

| 항목 | 상태 |
| --- | --- |
| 도메인 | Cloudflare 서비스 도메인 구매·Active 사용자 확인(실제 값은 로컬 기록) |
| VPS | OVHcloud VPS-1 2027 싱가포르 구매 사용자 확인, 2 vCore·4GB·40GB·Ubuntu 26.04 견적 |
| 공인 IP·SSH | 공인 IPv4는 2026-11-22 사용자 확인, 실제 값은 로컬 세션 기록에 보관. 기본 사용자·SSH 접속은 미검증 |
| GitHub | 공개 저장소, default main, 원격 main만 존재. main protected, merge commit 비활성·squash 활성 |
| 전환 작업 브랜치 | 2026-11-22 사용자 확인 후 최신 origin/main에서 common/chore/develop-release 생성. 기존 미커밋 변경 보존, 원격 추적 미설정 |
| 로컬 변경 | develop/release CI·PR 경로 검사·직접 push 차단 훅 준비 |
| 원격 전환 | develop/release 생성·기본 브랜치·merge 설정·보호 규칙 변경 미수행 |
| 배포 | 배포용 Compose/Caddy·이미지 발행·CD·DNS·HTTPS·실서버 검증 미수행 |

서버 비밀번호·SSH 개인키·API secret을 채팅이나 저장소에 넣지 않는다. 서버 IP와 공개 도메인만으로 준비할 수 있는 범위를 먼저 진행한다.

이 저장소는 public이다. 문서와 설정 예시는 example.com·환경변수 이름을 사용하고, 실제 배포 주소·SSH 사용자 등 운영값은 공개 문서에 고정하지 않는다. 도메인·공인 IP 자체는 인증 비밀이 아니지만 버전 관리할 필요가 없는 운영값은 로컬 운영 기록이나 서버·CI 설정으로 관리한다. 비밀번호·개인키·DB 접속 자격증명·JWT/TOTP/결제 secret은 로컬 학습 기록에도 넣지 않고 GitHub Secrets 또는 접근 제한된 서버 환경 파일로 관리한다. gitignore는 이미 추적된 파일이나 과거 commit에서 정보를 제거하지 않으므로 commit 전 diff를 확인한다.

## 브랜치 흐름

```text
origin/develop에서 작업 브랜치 생성
  → 작업 PR → develop (squash merge, CI 통과)
  → develop에서 release로 승격 PR (일반 merge commit, CI 통과)
  → release 커밋 CI 통과 → 해당 SHA 배포 (CD는 후속 구현)
```

- 일반 작업 브랜치명은 기존 `{be|fe|admin|common}/{type}/{description}`을 유지한다.
- release 대상 PR은 같은 저장소의 develop만 허용한다. 포크 저장소의 develop이나 작업 브랜치에서 직접 승격하지 않는다.
- hotfix도 최신 develop에서 시작하고 같은 PR 경로를 따른다. release에서 따로 수정하거나 승인 없이 cherry-pick하지 않는다.
- 승격에는 develop에 누적된 변경 전체가 들어간다. 미완성 기능은 작업 브랜치에 남기거나 승인된 비활성 설정을 사용한다.
- release는 결제 환경 이름이 아니다. 첫 VPS의 `PAYMENT_ENVIRONMENT=test`를 유지하고 작가 실결제 전환은 M7에서 별도로 수행한다.
- GitHub의 squash 버튼은 작업 PR에, merge commit 버튼은 develop → release에 사용한다. 장기 브랜치를 반복 squash하면 이미 승격한 커밋이 이후 PR에 다시 나타날 수 있다.

## 최초 전환 순서

아래 GitHub 변경과 commit/push는 실행 전 구체적인 diff·메시지·대상을 사용자에게 확인받는다. 이 문서 작성 자체가 실행 완료를 뜻하지 않는다.

1. 기존 미커밋 변경을 보존하고 현재 브랜치·PR 상태를 확인한다. develop이 없을 때만 최신 origin/main을 기준으로 전환 작업 브랜치를 만든다. 이미 병합된 작업 브랜치의 변경을 reset하거나 버리지 않는다.
2. CI·훅·문서 전환 PR을 main에 반영한다. CI의 main PR·push 트리거는 이 최초 전환을 위한 호환 경로다. 아직 존재하지 않는 develop만 검사하도록 바꿔 전환 PR이 검사 없이 병합되지 않게 한다.
3. 전환 PR이 반영된 최신 main의 **같은 커밋**에서 원격 develop과 release를 생성한다. 로컬 훅을 일상적으로 우회하지 않고, 승인받은 GitHub UI/API 생성 절차를 사용한다. 원래 main과 태그는 삭제하거나 이름을 바꾸지 않는다.
4. GitHub Settings에서 기본 브랜치를 develop으로 바꾸고 `Allow merge commits`와 `Allow squash merging`을 모두 허용한다. rebase merge는 사용하지 않는다.
5. develop/release에 PR 병합·required status checks(`branch-policy`, `backend`, `frontend`, `admin`)·force push 및 삭제 금지를 설정한다. release는 merge commit이 필요하므로 linear history를 요구하지 않는다. 저장소 설정상 통합 브랜치가 자동 삭제되지 않도록 확인한다. 자기 PR을 혼자 승인할 수 없으므로 필수 타인 승인 수는 협업 인원에 맞춰 결정한다.
6. main 보호는 유지하고 이후 신규 작업·배포 대상으로 사용하지 않는다. 새 기본 브랜치와 전환 결과를 확인한 뒤 main CI 호환 트리거 제거 여부를 정한다. 기존 열려 있는 PR이 있다면 develop으로 base를 변경하고 diff·CI를 다시 확인한다.
7. fetch 후 새 작업은 origin/develop에서 분기한다. `.githooks/pre-push`는 main/develop/release의 생성·수정·삭제를 모두 막는 로컬 보조 방어다. GitHub 보호 규칙은 따로 설정해야 하며 PR 검사 코드 변경도 리뷰한다.

예시 명령은 전환 완료·사용자 브랜치 생성 확인 뒤 실행한다. 현재 작업 변경을 들고 임의로 checkout하지 않는다.

```bash
git fetch origin
git switch -c be/feat/example origin/develop
# 작업·검사·승인된 commit/push 후 PR base는 develop
```

현재 연결된 GitHub 도구는 main의 protected 여부까지만 읽었고, 보호 세부 API는 관리 권한 부족으로 403이었다. GitHub 설정 화면 또는 적절한 관리 권한으로 실제 규칙을 확인해야 한다.

## 서버와 공개 주소 준비

1. 공인 IPv4는 사용자에게 확인했다. OVHcloud 제공 완료 안내에서 기본 사용자·키 등록 또는 초기 접속 절차를 확인한다. 서버 접속·프로비저닝·재시작은 현재 상태와 대상 확인 뒤 수행한다.
2. 작업용 비root 사용자의 SSH 키 접속을 확인한 뒤 root·비밀번호 SSH를 차단한다. 방화벽은 TCP 22(관리자 IP), 80/443(공개 요청)을 허용하고 DB 5432·API 8000을 공인 인터페이스에 노출하지 않는다. Docker 포트 공개가 호스트 방화벽 규칙을 우회할 수 있으므로 Compose 포트와 방화벽을 함께 확인한다.
3. Docker·Compose와 배포 디렉터리, 서버 전용 환경 설정을 준비한다. 기존 로컬 compose의 기본 DB 비밀번호와 localhost URL을 공개 서버에 재사용하지 않는다. backend 컨테이너 비root 실행도 준비한다.
4. 아래 이름은 첫 테스트용 **제안**이며 아직 DNS를 생성하지 않았다. 확인한 서버 IPv4로 A 레코드를 만들고, IPv6 제공·라우팅을 검증하기 전에는 AAAA를 만들지 않는다.

| 서비스 | 공개 주소 제안 |
| --- | --- |
| 독자 사이트 | `https://staging.example.com` |
| 관리자 | `https://staging-admin.example.com` |
| API | `https://staging-api.example.com` |

처음에는 DNS only + Caddy의 공개 HTTPS 인증서로 확인한다. 세 주소를 같은 등록가능도메인 아래 둬 현재 HttpOnly 쿠키의 same-site 조건을 유지한다. 1단계 서브도메인 제안은 이후 Cloudflare Universal SSL을 사용할 때의 기본 인증서 범위도 고려했다. 정식 root/admin/api 주소와 테스트·운영 DB/secret은 M7에서 분리한다.

5. backend의 APP_BASE_URL/ADMIN_BASE_URL/API_BASE_URL, frontend 빌드의 PUBLIC_API_URL, admin 빌드의 VITE_API_URL을 공개 주소로 맞춘다. frontend SSR의 API_INTERNAL_URL은 컨테이너 내부 API 주소로 분리한다. 비밀값을 PUBLIC_/VITE_ 빌드 변수로 넣지 않는다.
6. 공개 주소에 맞춰 OAuth 콜백, 메일 링크와 PortOne 테스트 웹훅을 등록한다. 제안 기준 결제 복귀는 `https://staging.example.com/payments/return`, 웹훅은 `https://staging-api.example.com/payments/webhooks/portone`이다.

## release 배포 구현 계획

아래는 후속 구현할 CD 계약이다. 현재 CI 파일은 검사만 하며 이미지 발행·SSH 배포·마이그레이션을 하지 않는다.

- 배포 시작은 **release push + 해당 커밋 CI 성공**으로 제한한다. develop/main/PR/태그 이벤트에서는 배포 job과 운영 secret을 사용하지 않는다.
- CI 성공에 의존하는 이미지 빌드·배포 단계를 구성하고 모든 앱을 같은 release 커밋 SHA로 식별한다. 이동 가능한 latest 태그만으로 배포 버전을 결정하지 않는다.
- 레지스트리는 GHCR을 우선 후보로 두되 아직 설정하지 않았다. 저장소가 공개라고 이미지까지 자동으로 공개하지 않고, 공개 범위·최소 권한을 먼저 결정한다.
- 최초 배포는 SSH 호스트 키를 검증하고 별도 배포 사용자를 사용한다. 키·서버 환경 파일은 안전한 서버 설정 또는 GitHub secret으로 등록하며 저장소에 commit하지 않는다.
- 배포를 직렬화하고 진행 중인 DB 마이그레이션을 새 실행으로 임의 중단하지 않는다. DB 백업과 `alembic upgrade head` 후 healthcheck로 확인한다. 실패 시 이전 이미지로 복구할 수 있어야 하며 DB는 forward-only 원칙상 이미지 복구만으로 되돌아간다고 가정하지 않는다.
- 2 vCore·4GB 서버는 무중단을 약속하지 않고, 첫 테스트 환경은 짧은 중단을 허용하는 안을 우선 검토한다. 실제 중단·복구 절차는 배포 구현 때 확정한다.
- DB 덤프를 별도 R2 백업 버킷에 보관하고 복구를 검증한다. 표지 공개 버킷과 유료·미공개 원고 비공개 버킷을 섞지 않는다.
- 첫 공개 전 기존 의존성 보안 점검의 확인 필요 항목도 실제 배포 버전·기능 조건에 맞춰 확인한다.

## 완료 확인

- [ ] develop에서 작업 브랜치 생성 → develop PR CI 통과
- [ ] 같은 저장소 develop → release PR CI 통과, 작업 브랜치·포크 develop → release 거부
- [ ] GitHub 기본 브랜치·merge commit·두 통합 브랜치 보호 규칙 실제 반영
- [ ] release의 검증된 SHA로만 배포, 실제 서버의 실행 버전 확인
- [ ] DB 마이그레이션·healthcheck·백업 복구 확인
- [ ] 세 공개 주소의 HTTPS와 쿠키 로그인 확인
- [ ] 사용자가 카드·카카오페이·토스페이 테스트와 모바일 복귀·구매 권한·환불 흐름 확인

정적 검사·단위/통합 테스트는 에이전트가, 브라우저 실기능 확인은 사용자가 수행한다. Playwright E2E는 추가하지 않는다.

## 공식 참고

- [GitHub 기본 브랜치 변경](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/changing-the-default-branch)
- [장기 브랜치 squash merge 주의](https://docs.github.com/en/pull-requests/reference/pull-request-merges#squashing-and-merging-a-long-running-branch)
- [GitHub 보호 브랜치](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [GitHub Actions 이벤트](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [Cloudflare Universal SSL 인증서 범위](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/)
- [Docker Ubuntu 설치와 방화벽 제한](https://docs.docker.com/engine/install/ubuntu/)
