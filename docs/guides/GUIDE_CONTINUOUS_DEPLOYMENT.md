# Continuous Deployment 운영 가이드

이 문서는 현재 저장소의 CD 코드와 사용자 승인 설계를 설명한다. 코드는 준비되어 있지만 실제 VPS 적용, Cloudflare Tunnel 설정, SSH 키 등록, GitHub 환경 활성화는 사용자가 수동으로 수행해야 하며 현재 외부 활성화 완료로 보지 않는다.

## 배포 경계

| Git ref | 환경 | GitHub 환경 | 기본 상태 |
| --- | --- | --- | --- |
| `develop` push | `staging` | `staging` | `STAGING_DEPLOY_ENABLED=false` |
| `release` push | `production` | `production` | `PRODUCTION_DEPLOY_ENABLED=false` |

PR, `main`, 태그와 작업 브랜치는 배포하지 않는다. 각 앱 이미지는 전체 commit SHA 태그를 사용하고, 서버는 해당 SHA가 대상 통합 브랜치의 현재 HEAD인지 확인한다. 배포 job은 branch-policy, backend, frontend, admin job이 모두 성공한 뒤에만 실행된다.

워크플로우는 `.github/workflows/ci.yml`의 opt-in 조건에서 `.github/workflows/deploy.yml`을 호출한다. 두 환경은 별도 GitHub Environment, 별도 DB volume, 별도 secret 파일, 별도 R2 설정, 별도 Docker project와 edge network를 사용한다. Caddy만 공용 edge로 80/443을 열고, 앱과 PostgreSQL은 각 환경의 내부 네트워크에 둔다.

## GitHub 설정

Repository Variables에는 배포 flag만 등록한다.

- `STAGING_DEPLOY_ENABLED`: 정확히 `true`일 때만 `develop` 배포를 허용한다.
- `PRODUCTION_DEPLOY_ENABLED`: 정확히 `true`일 때만 `release` 배포를 허용한다.

각 GitHub Environment의 Variables에는 해당 환경의 `SSH_HOST`, `SSH_USER`, `SSH_PORT`, `API_HOST`를 별도로 등록한다.

Environment Secrets에는 다음을 등록한다. 값 자체는 문서나 로그에 복사하지 않는다. GHCR 이미지는 기본 private이므로 서버가 pull할 때 사용할 GitHub Packages read 권한도 별도로 준비한다.

- `SSH_PRIVATE_KEY`: 강제 명령 전용 배포 키의 개인키
- `SSH_KNOWN_HOSTS`: 검증한 호스트 키
- `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`: Cloudflare Access service token

staging과 production은 각각 별도 GitHub Environment와 별도 배포 키를 사용한다. `GITHUB_TOKEN`은 workflow의 GHCR push에만 쓰이며, 서버 pull을 위해 장기 PAT를 저장소 파일에 넣지 않는다. 서버의 `docker login ghcr.io` 절차와 read:packages 자격증명 배치는 실제 서버 bootstrap에서 수동으로 정한다.

`API_HOST`는 `prepare-deployment.sh`가 scheme, path, private IP, localhost를 거부한다. `PUBLIC_API_URL`과 `VITE_API_URL`에는 이 값으로 만든 공개 HTTPS URL만 빌드 인자로 들어간다.

## 서버 디렉터리와 기존 자산 보존

배포 루트는 `~/d-web-deploy`이며 실제 운영 사용자가 소유하고 권한 700이어야 한다. 기존 `root`, `source`, `backend.env`, `deploy.env`를 삭제하거나 덮어쓰지 않는다. 새 구조는 다음과 같다.

```text
~/d-web-deploy/
  repository.url
  source.git/                    # bare Git mirror
  staging/
    deploy.env                   # 600, Git 밖
    backend.env                  # 600, Git 밖
    releases/<full-sha>/
    jobs/<full-sha>/
    current.sha
    previous.sha
  production/                    # staging과 같은 구조
  backups/staging/               # 700
  backups/production/            # 700
  edge/                          # shared Caddy env와 compose 작업 위치
  bin/                           # forced-command 배포 스크립트
```

기존 staging 데이터는 보존한다. edge compose의 외부 volume 이름은 기본적으로 `dweb-staging_caddy_data`, `dweb-staging_caddy_config`이며 기존 volume을 재생성하거나 삭제하지 않는다. staging runtime의 기존 `dweb-staging_postgres_data`도 같은 project 이름으로 계속 사용한다. production은 `dweb-production_postgres_data`와 별도 환경 파일을 사용한다. R2 버킷과 backend secret은 두 환경에서 공유하지 않는다.

서버의 `sy3058` 사용자는 현재 Docker group에 없을 수 있다. `sudo docker`로 기존 명령을 수행하고, 사용자가 승인한 서버 maintenance 창에 다음을 수동 실행한 뒤 재접속한다.

```bash
sudo usermod -aG docker sy3058
```

현재 셸에 즉시 반영됐다고 가정하지 않는다. 로그아웃 후 SSH 재접속 뒤 `id -nG`와 `docker version`을 사용자가 확인한다. 이 문서에서 Docker group 변경을 자동화하지 않는다.

### 새 CD 구조 bootstrap

현재 `source`에는 옛 release 코드가 있을 수 있으므로 새 CD 커밋이 develop에 병합된 뒤에만 source를 갱신한다. 변경이 있으면 중단하고 보존한다. 아래 확인 후 확정 SHA를 checkout한다.

```bash
cd ~/d-web-deploy/source
git status --short
git fetch --no-tags origin develop
# 위 status가 비어 있고, 아래 SHA가 CI 성공한 새 CD 커밋일 때만:
git switch --detach <verified-develop-sha>
git rev-parse HEAD
```

기존 파일을 덮어쓰지 않고 디렉터리와 새 파일만 만든다. 아래 명령은 서버에서 검토 후 사용자가 실행한다.

```bash
cd ~/d-web-deploy
mkdir -p staging/{releases,jobs} production/{releases,jobs} backups/{staging,production} edge bin
chmod 700 staging production backups backups/staging backups/production edge bin
printf '%s\n' 'https://github.com/OWNER/REPOSITORY.git' > repository.url
chmod 600 repository.url
install -m 750 source/deploy/scripts/dispatch.sh bin/dispatch.sh
install -m 750 source/deploy/scripts/deploy.sh bin/deploy.sh
install -m 750 source/deploy/scripts/run-job.sh bin/run-job.sh
cp -n source/deploy/edge.yml edge/edge.yml
cp -n source/deploy/edge.Caddyfile edge/edge.Caddyfile
cp -n source/deploy/edge.env.example edge/edge.env
cp -n source/deploy/environments/staging.env.example staging/deploy.env
cp -n source/deploy/environments/production.env.example production/deploy.env
chmod 600 staging/deploy.env production/deploy.env edge/edge.env
```

`OWNER/REPOSITORY`와 환경 파일의 공개 host, image prefix, absolute `BACKEND_ENV_FILE`은 실제 값으로 사용자가 채운다. 기존 `source`, `backend.env`, `deploy.env`는 유지하고 새 환경 파일만 채운다. 각 환경의 `backend.env`도 별도로 만들고 600으로 설정한다. `dispatch.sh`는 `SSH_ORIGINAL_COMMAND`를 직접 처리하므로 별도 deploy wrapper를 만들지 않는다.

staging의 DB 비밀번호는 기존 volume 생성 때 사용한 값을 유지한다. 기존 `backend.env`를 staging 파일의 출발점으로 쓰되 URL을 staging 주소로 바꾼다. production은 네 인증 키, DB 비밀번호, R2 버킷과 버킷 한정 접근 키를 새로 만든다. DB 연결 문자열에 들어갈 비밀번호는 긴 랜덤 hex처럼 URL 인코딩 문제를 피할 수 있는 값을 사용한다. production은 staging의 사용자·작품 데이터를 자동으로 복제하지 않는다.

GitHub Environment의 허용 배포 브랜치도 staging은 `develop`, production은 `release`로 제한한다. GitHub 환경의 `API_HOST`와 VPS의 해당 환경 `API_HOST`가 같아야 이미지 검증이 통과한다. OAuth 콘솔에는 각 환경 API의 콜백을, Resend와 PortOne 테스트 설정에는 각 환경의 URL을 맞춘다. 현재 결제 설정은 두 환경 모두 `test`, 신규 결제 차단이 기본이다.

## 최초 edge 전환

Cloudflare Access와 Tunnel 등록은 계정·서버 운영값을 요구하므로 사용자가 수동으로 수행한다. staging과 production 각각에 Self-hosted Access application과 별도 service token을 만든다. 각 application은 SSH published route를 `ssh://localhost:22`로 outbound tunnel에 연결한다. 이 경로는 기존 UFW 정책을 바꾸지 않는다. 개인 SSH 키 로그인은 유지하고, CI에는 staging·production용 별도 배포 키 두 개를 등록한다.

Cloudflare의 SSH published application은 [SSH over Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ssh-cloudflared-authentication/) 절차를, service token은 [Service Tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/) 공식 문서를 따른다. Access application별 Service Auth와 별도 token을 사용해 identity provider prompt 우회를 허용하지 않는다.

- TODO: 실제 staging/production Access hostname과 tunnel ID를 계정에서 생성한다.
- TODO: 두 CI 공개키를 `authorized_keys`에 각각 `restrict,command="/home/sy3058/d-web-deploy/bin/dispatch.sh staging"` 및 production 명령으로 등록한다. `dispatch.sh`가 `SSH_ORIGINAL_COMMAND`를 직접 처리하므로 wrapper는 설치하지 않는다.
- TODO: 검증한 VPS 공개 host key를 Cloudflare hostname으로 접속할 때도 같은 서버 host key로 확인해 `SSH_KNOWN_HOSTS`에 등록한다. 별도 Cloudflare host key를 가정하지 않는다. 개인 SSH 키와 CI 키를 혼용하지 않는다.
- TODO: GitHub Environment 변수와 secret을 등록하고 Repository Variables의 flag는 staging부터 수동으로 켠다.

이 절은 아래 "최초 bootstrap"의 두 환경 내부 기동을 마친 뒤 실행한다. edge 전환 전 두 환경의 앱·migration이 정상인지, 여섯 공개 hostname의 DNS가 VPS를 가리키는지 확인한다. 최초 전환에는 점검 시간이 생기며, production 초기 콘텐츠 설정까지 서비스 준비가 끝난 것으로 보지 않는다. 실행 전 현재 서버 디렉터리와 기존 인증서 volume을 확인한다. 아래 블록은 사전 검증이나 다운로드가 실패하면 기존 Caddy를 중지하지 않는다.

```bash
(
set -e
cd ~/d-web-deploy/edge
if ! docker network inspect dweb-staging-edge >/dev/null 2>&1; then docker network create dweb-staging-edge; fi
if ! docker network inspect dweb-production-edge >/dev/null 2>&1; then docker network create dweb-production-edge; fi
docker compose --env-file edge.env -f edge.yml config --quiet
docker volume inspect dweb-staging_caddy_data dweb-staging_caddy_config >/dev/null
docker compose --env-file edge.env -f edge.yml pull caddy
# 실제 점유 컨테이너가 정확히 dweb-staging-caddy-1인 경우에만 새 edge 전에 중지한다.
if docker ps --format '{{.Names}}' | grep -Fxq dweb-staging-caddy-1; then docker stop dweb-staging-caddy-1; fi
docker compose --env-file edge.env -f edge.yml up -d --wait --wait-timeout 180
)
```

`edge.env`는 `deploy/edge.env.example`에서 복사해 Git 밖에 만들며 실제 host와 ACME email만 사용자가 입력한다. 저장소 파일명은 `deploy/edge.yml`과 `deploy/edge.Caddyfile`이다. edge 위치는 `~/d-web-deploy/edge`로 고정한다.

기존 `dweb-staging-caddy-1`이 80/443을 점유하면 먼저 해당 컨테이너만 `docker stop dweb-staging-caddy-1`으로 중지한 뒤 새 edge를 올린다. 새 edge가 실패하면 새 edge 컨테이너만 `docker compose ... down`으로 중지하고 기존 Caddy를 `docker start dweb-staging-caddy-1`로 다시 기동한다. 이는 DB rollback이 아니며 Caddy 인증서·DB volume을 삭제하지 않는다. 실행 전 `docker ps --format '{{.Names}} {{.Ports}}'`로 실제 컨테이너를 확인하고, 이름이 다르면 명령 대상을 추측하지 않는다.

## 자동 배포 흐름

1. `develop` 또는 `release`에 승인된 push가 발생하거나 `workflow_dispatch`를 수동 실행한다. 두 경우 모두 repository flag가 `true`여야 한다.
2. 공통 CI가 네 개의 필수 job을 통과한다.
3. opt-in flag와 matching branch 조건을 확인한다.
4. pinned cloudflared를 checksum 검증 후 설치한다.
5. GHCR에 `/<environment>/<service>:<full-sha>` 이미지 세 개를 빌드·push한다.
6. SSH는 `StrictHostKeyChecking=yes`, `IdentitiesOnly=yes`, `ProxyCommand=cloudflared access ssh`로 연결하고 `deploy <full-sha>`만 전달한다.
7. 서버 `deploy.sh`가 branch HEAD, source mirror, compose project, 환경 격리, 이미지 revision/API URL을 검증한다.
8. commit SHA별 이미지를 digest로 고정하고 DB backup, migration, healthcheck 순서로 기동한다.

배포는 환경별 concurrency와 서버의 공용 lock으로 직렬화된다. SSH 연결이나 CI monitor가 끊겨도 분리된 worker는 migration을 계속 수행하며, 같은 SHA의 작업이 실행 중이면 해당 worker에 붙는다. 이미 완료한 SHA를 다시 배포 요청하면 과거 성공 기록을 재사용하지 않고 현재 branch HEAD 검증부터 실제 배포·healthcheck까지 다시 실행한다. 따라서 현재 HEAD가 아닌 과거 SHA 재실행은 실패하고, 현재 SHA 재실행도 백업·migration과 짧은 API 중단을 동반한다. 실패·재부팅으로 남은 상태는 실제 worker lock을 확인해 재시도한다. `status <full-sha>`는 과거 job 결과 조회이며 현재 실행 버전·건강 상태 확인을 대신하지 않는다. 상세 로그는 서버의 `<environment>/jobs/<full-sha>/job.log`에서 운영자가 확인하고 로그 원문을 공개하지 않는다.

백업에 실패하면 migration을 시작하지 않는다. migration에 실패하면 API가 중지된 채 남을 수 있으며 `current.sha`는 성공한 마지막 SHA를 유지한다. 이미지 rollback은 DB migration rollback이 아니므로 forward fix 또는 백업 복구를 별도로 판단한다. `backups`, `releases`, 이미지 용량을 주기적으로 확인하고, 두 환경이 공유하는 Docker에서 일괄 `prune`이나 volume 삭제를 실행하지 않는다.

## 활성화 순서와 수동 비활성화

### 최초 bootstrap (기존 단일 Caddy에서 두 환경으로 전환)

첫 설정에서는 아직 staging 공개 주소를 새 edge가 서비스하지 않으므로 브라우저 검증을 production 내부 기동의 선행조건으로 두지 않는다. 점검 시간에 다음 순서로 진행하고, 중간 단계에 실패하면 다음 단계로 넘어가지 않는다. 준비 중에는 다른 merge·승격을 하지 않는다.

1. 두 flag를 미설정 또는 `false`로 유지한 채 새 CD 커밋을 develop에 merge한다. 이 문서의 서버 파일·환경 파일·Tunnel·키·GitHub Environment·GHCR pull 설정을 준비한다. staging과 production의 결제는 `test`, 신규 결제 차단을 유지한다.
2. staging flag만 임시로 `true`로 바꾸고 develop에서 CI를 `workflow_dispatch`로 실행한다. CI와 배포 worker가 끝난 뒤 staging 컨테이너 health, migration, 백업 파일을 VPS에서 확인한다. 이 단계는 내부 확인이며 새 staging URL의 브라우저 검증은 아직 요구하지 않는다. 완료 후 staging flag를 다시 `false`로 둔다.
3. 같은 저장소 develop → release를 일반 merge commit으로 승격한다. production flag는 아직 `false`이므로 승격 push는 CI만 실행한다. production flag를 임시로 `true`로 바꾸고 release에서 CI를 수동 실행해 production을 내부 기동한다. CI·worker 완료와 컨테이너 health, migration, 백업을 확인한 뒤 production flag를 다시 `false`로 둔다.
4. 두 환경이 내부에서 정상 기동한 상태에서 위 "최초 edge 전환" 절차를 실행한다. 이제 새 staging 주소와 production 주소가 shared Caddy에 연결된다. 이 최초 전환 전에는 새 주소의 정상 접속을 완료조건으로 삼지 않는다.
5. 사용자가 두 환경의 HTTPS·쿠키 로그인·관리자·R2 동작을 브라우저에서 확인한다. production owner와 콘텐츠 설정도 완료한다. 실패하면 두 flag를 꺼 둔 채 복구하고, proxy 복구를 DB rollback으로 간주하지 않는다.
6. 브라우저 확인과 초기 데이터 준비가 끝난 뒤 staging 자동 배포 flag를 켠다. production 자동 배포도 운영 준비 확인 후 켠다. 그 전까지는 정상 기동만으로 운영 활성화 완료를 표시하지 않는다.

### 이후 정기 배포

staging flag가 켜져 있으면 develop의 CI 성공 후 staging이 갱신된다. 사용자가 staging을 확인한 뒤 같은 저장소 develop → release를 일반 merge commit으로 승격하면 production flag가 켜진 경우 해당 release의 CI 성공 후 production이 갱신된다. 최초 bootstrap의 임시 flag 전환이나 edge 교체를 정기 배포마다 반복하지 않는다.

자동 배포를 비활성화하려면 해당 Repository Variable을 `false`로 바꾼다. 이미 실행 중인 workflow·worker는 이 변경만으로 중단되지 않으므로 별도로 상태를 확인한다.

production 최초 배포는 staging과 별도 빈 DB volume과 backend secret을 사용한다. owner 계정, 작품·에피소드, 사이트 문구와 R2 연결을 별도로 초기화해야 하며 healthcheck green만으로 서비스 기능 완료로 판정하지 않는다. 사용자가 브라우저와 관리자에서 초기화·로그인·콘텐츠·결제 전 상태를 확인한다.

구체적인 서버 명령과 앱 초기 배포는 [deploy README](../../deploy/README.md), 코드 계약과 검증 항목은 [Continuous Deployment 구현 문서](../MODULES/INFRA/DockerCompose/IMPLEMENTATION_CONTINUOUS_DEPLOYMENT.md)를 따른다.
