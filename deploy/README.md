# VPS 배포와 Continuous Deployment 설정

`compose.yml`은 저장소 루트의 로컬 Compose와 합치지 않고 단독으로 사용한다. 이 문서는 수동 bootstrap과 현재 CD의 서버 계약을 설명한다. `develop`은 staging, `release`는 production에 매핑되며 opt-in flag는 기본 off다. 실제 VPS·Cloudflare Tunnel·GitHub secret 활성화는 아직 완료하지 않았다. 전체 CD 절차는 [Continuous Deployment 운영 가이드](../docs/guides/GUIDE_CONTINUOUS_DEPLOYMENT.md)를 참조한다.

아래의 기존 단일 staging 수동 절차는 legacy `source`와 `deploy.env`를 보존해야 하는 초기 운영 경로다. 자동 CD를 활성화할 때는 `source.git`와 `staging`·`production`·`edge` 구조 및 환경별 파일을 사용하는 [CD 운영 가이드](../docs/guides/GUIDE_CONTINUOUS_DEPLOYMENT.md)의 계약을 우선한다. 기존 파일과 volume을 자동으로 이동하거나 삭제하지 않는다.

## 현재 경계

- staging 배포 대상은 CI를 통과한 같은 저장소 `develop` 커밋이고 production 배포 대상은 CI를 통과한 `release` 커밋이다. 작업 브랜치와 `main`은 서버에서 실행하지 않는다.
- 세 앱 이미지를 같은 전체 커밋 SHA로 태그한다. `RELEASE_SHA`는 임의 버전 이름이 아니라 실제 `git rev-parse HEAD` 결과다.
- 외부 공개 포트는 Caddy의 TCP 80/443뿐이다. PostgreSQL·API·Astro·관리자 nginx는 컨테이너 네트워크로 통신한다.
- `ENV=production`은 Secure 쿠키를 켜기 위한 실행 설정이다. 결제는 별개이며 `PAYMENT_ENVIRONMENT=test`를 고정하고 신규 결제는 기본 차단한다.
- edge Caddy는 staging과 production이 공유하며 환경별 external network의 alias로 앱을 찾는다. 공개 포트는 80/443뿐이다. Cloudflare Tunnel SSH 경로와 공개 HTTPS 활성화는 수동 설정 전까지 미완료다.
- 원고 R2 버킷은 비공개로 유지한다. 원고를 앱 이미지나 서버의 공개 디렉터리에 복사하지 않는다.

2026-11-23 Astro 이미지 경로 취약점 `GHSA-r3h5-4585-7x3w` 수정은 PR #163으로 develop에 병합됐다. 이 배포 브랜치도 해당 커밋과 `astro@7.4.7` 잠금을 반영했다. 수정된 코드가 포함된 release로 새 이미지를 빌드해야 실제 서버에 적용된다. `@astrojs/node`만 업데이트해서는 해결되지 않는다. [공식 공지](https://github.com/withastro/astro/security/advisories/GHSA-r3h5-4585-7x3w).

## 서버 파일 배치

```text
~/d-web-deploy/                 # 운영 사용자 소유, 권한 700
  source.git/                  # bare mirror
  staging/                     # deploy.env/backend.env/releases/jobs/state
  production/                  # staging과 별도 secret/DB/R2
  backups/staging/             # DB dump, 권한 700
  backups/production/
  edge/                        # shared Caddy
```

기존 `root`, `source`, `backend.env`, `deploy.env`와 legacy volume `dweb-staging_postgres_data`, `dweb-staging_caddy_data`, `dweb-staging_caddy_config`는 삭제·덮어쓰지 않는다. 새 CD 구조는 `source.git`, `staging`, `production`, `backups`, `edge`만 추가한다.

최초 clone·release 전환은 해당 변경의 PR 병합 및 release 승격, 그 SHA의 CI 성공 확인 뒤 수행한다. 저장소 URL과 운영값은 공개 문서에 고정하지 않는다. 원격 release 변경을 fetch한 뒤 실행할 커밋을 확인하고 detached 상태로 고정한다. 변경된 파일이 있다면 전환 전에 원인을 확인하고 보존한다.

```bash
cd ~/d-web-deploy/source
git status --short
git fetch origin
git switch --detach origin/release
git rev-parse HEAD
```

## 환경 파일 준비

아직 파일이 없는 최초 준비에서만 예시를 복사한다. 기존 운영 파일은 덮어쓰지 않는다.

```bash
cd ~/d-web-deploy
cp -n source/deploy/.env.example deploy.env
cp -n source/deploy/backend/.env.example backend.env
chmod 600 deploy.env backend.env
mkdir -p backups
chmod 700 backups
```

`deploy.env`에서 다음 값을 채운다.

- `RELEASE_SHA`: 위에서 확인하고 CI 성공을 검증한 전체 SHA. `IMAGE_PREFIX`와 함께 앱 이미지 이름을 만든다.
- `APP_HOST`, `ADMIN_HOST`, `API_HOST`: 같은 등록가능도메인 아래의 서로 다른 1단계 호스트. `https://`나 `/`를 넣지 않는다.
- `ACME_EMAIL`: 인증서 발급 연락용 이메일.
- `POSTGRES_PASSWORD`: `openssl rand -hex 32`로 생성한 값. DB URL에 직접 들어가므로 이 예시는 hex 문자만 사용한다. 값 변경만으로 기존 DB 볼륨의 비밀번호가 바뀌지는 않는다.
- `BACKEND_ENV_FILE`: 서버 `backend.env`의 절대 경로. `~`를 넣지 않는다.

`backend.env`의 `JWT_SECRET`, `PASSWORD_PEPPER`, `TOKEN_PEPPER`는 각각 별도의 `openssl rand -hex 48` 결과를 사용한다. `TOTP_ENCRYPTION_KEY`는 Fernet 규격인 무작위 32바이트의 URL-safe base64 문자열이다. 서버에서는 다음 명령으로 만들 수 있다.

```bash
openssl rand -base64 32 | tr '+/' '-_'
```

생성한 비밀값을 채팅·로그·Git에 넣지 않는다. R2, Resend, OAuth, PortOne 값은 서버에서 직접 입력한다. 스토리지·메일·OAuth 설정이 없어도 앱 부팅은 가능하지만 해당 기능은 준비 완료가 아니다. 발신 도메인 인증과 OAuth callback 등록도 필요하다. 현재 첫 테스트 환경에서 `PAYMENTS_ACCEPT_NEW=false`를 유지하며, 공개 주소·테스트 Store·채널·웹훅을 모두 검증하기 전에는 켜지 않는다.

`DATABASE_URL`, 공개 base URL, 실행 환경과 결제 환경은 Compose가 설정한다. `backend.env`에서 중복 설정하지 않는다. `PUBLIC_API_URL`과 `VITE_API_URL`은 **빌드 시** API 공개 주소로 들어가고 `API_INTERNAL_URL=http://api:8000`은 Astro SSR 실행 시에만 주입한다. 도메인이 바뀌면 frontend/admin 이미지를 다시 빌드한다.

## 첫 실행 순서

아래 함수는 현재 서버 셸에만 등록한다. sudo로 실행하는 Docker에도 Compose 파일·환경 파일의 절대 경로를 전달한다.

```bash
dc() {
  sudo docker compose \
    --env-file "$HOME/d-web-deploy/deploy.env" \
    -f "$HOME/d-web-deploy/source/deploy/compose.yml" "$@"
}
```

1. 필수 변수와 파일 경로를 검사한다. `config`의 전체 출력에는 DB 비밀번호 등이 포함되므로 `--quiet`만 사용한다.

   ```bash
   dc config --quiet
   ```

2. 앞서 확인한 release SHA가 환경 파일의 `RELEASE_SHA`와 일치하고 그 커밋의 CI가 성공했는지 확인한다. 공개 실행 전 위 보안 항목까지 해결한 뒤 이미지를 빌드한다. 이 단계는 레지스트리 없이 서버에서 세 이미지를 만드는 첫 수동 배포용이다.

   ```bash
   dc build --pull api frontend admin
   dc run --rm --no-deps caddy caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile --validate
   ```

3. 서비스를 기동한다. PostgreSQL 준비 → 일회성 `migrate`의 `alembic upgrade head` 성공 → API 준비 → Caddy 순서다. 마이그레이션이 실패하면 API·공개 프록시는 새로 시작하지 않는다. 단일 API 프로세스로 내부 스케줄러를 유지한다.

   ```bash
   dc up -d --no-build --wait --wait-timeout 180
   dc ps -a
   ```

   API의 `/`와 frontend favicon 검사는 프로세스 상태 확인이다. DB 스키마 적용은 migrate 결과로 확인하며, SSR·로그인·콘텐츠의 실제 동작까지 보장하지 않는다. 빈 DB에서는 관리자에서 `landing_intro` 등 초기 사이트 문구를 저장하기 전 홈이 의도적으로 503·no-store를 반환할 수 있다. 작품 목록 API와 SSR `/works` 연결을 별도로 확인하고 홈 503을 readiness 실패와 혼동하지 않는다.

4. 사용자 브라우저에서 세 주소의 인증서·로그인·관리자 권한·무료/구매 구간을 확인한다. 결제 테스트는 설정 검증 뒤 별도로 수행한다. Caddy `/data` 볼륨은 인증서 저장소이므로 삭제하지 않는다.

오류가 나면 `dc ps -a`, `dc logs --tail 100 migrate`, `dc logs --tail 100 caddy` 등 해당 서비스만 확인한다. 로그 공유 전 개인정보와 토큰·URL 쿼리가 없는지 확인한다. Caddy access log는 이 설정에서 켜지 않는다. `up` 실패는 성공으로 취급하지 않으며, 기존 실행 중 컨테이너까지 자동으로 중단·복구된다고 가정하지 않는다.

## 이후 배포와 복구

반복 배포에서는 새 release 소스와 SHA를 준비하고 새 이미지를 빌드한 뒤, 마이그레이션 전 아래 순서를 따른다. 배포 작업은 한 명이 직렬로 수행하며 동시에 다른 셸에서 `up`이나 migration을 실행하지 않는다.

```bash
dc stop caddy frontend admin api
```

쓰기 작업을 멈춘 뒤 DB를 백업한다. 셸의 리다이렉션은 sy3058로 실행되므로 제한된 backups 디렉터리에 저장된다.

```bash
umask 077
dc exec -T postgres pg_dump -U dweb -d dweb -Fc > "$HOME/d-web-deploy/backups/before-deploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

덤프 명령 성공과 파일 크기를 확인하고, DB 복구 검증 및 별도 R2 백업까지 준비한 뒤 다시 `dc up -d --no-build --wait --wait-timeout 180`을 실행한다. 백업 실패 시 migration으로 넘어가지 않는다. 첫 배포 전에는 복구 가능한 사용자 데이터가 없지만 운영 데이터를 넣기 전에는 별도 백업·복구 검증이 필요하다.

직전 SHA 이미지와 환경 파일 변경 이력을 비밀 저장소에 보존한다. 실패 시 `RELEASE_SHA`를 이전 검증 SHA로 복원하고 이미 존재하는 이미지를 사용해 앱을 재기동할 수 있지만, **이미지 복구는 DB migration을 되돌리지 않는다**. 적용된 스키마와 이전 코드의 호환성이 확인되지 않았다면 서비스를 중지하고 DB 복구 또는 forward fix를 판단한다. `docker compose down -v`로 DB·인증서 볼륨을 삭제하지 않는다.

## 남은 자동화

- release CI 성공에 연결한 GHCR 이미지 발행·VPS 배포와 SSH 호스트 키 검증
- 자동 배포 직렬화, 백업 실패 차단, 실패 시 서비스/DB 복구 판단
- R2 DB 백업과 복구 검증, 모니터링

공식 참고: [Compose 서비스](https://docs.docker.com/reference/compose-file/services/), [Caddy 자동 HTTPS](https://caddyserver.com/docs/automatic-https), [Docker와 방화벽](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
