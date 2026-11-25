# Continuous Deployment 구현 및 검증

## 범위와 상태

현재 브랜치의 CD 변경은 `develop`을 staging, `release`를 production으로 매핑하는 GitHub Actions reusable workflow와 서버 실행 스크립트를 준비한다. 실제 VPS, Cloudflare Tunnel, SSH forced command, GitHub Environment와 opt-in flag는 아직 외부 활성화하지 않았다. 이 문서는 구현 계약과 수동 활성화 조건을 기록하며 서버 secret을 포함하지 않는다.

## 구성

- `.github/workflows/ci.yml`: 네 개의 CI job 성공 후 `STAGING_DEPLOY_ENABLED` 또는 `PRODUCTION_DEPLOY_ENABLED`가 정확히 `true`일 때만 deploy job 호출
- `.github/workflows/deploy.yml`: 환경별 branch/ref 검사, pinned cloudflared, GHCR build/push, known-hosts 고정 SSH, Cloudflare Access service token ProxyCommand
- `scripts/prepare-deployment.sh`: 배포 환경과 ref, full SHA, 공개 `API_HOST`, image prefix 산출
- `deploy/scripts/dispatch.sh`: SSH original command를 `deploy|status <40자리 SHA>`로 제한하고 환경별 job을 직렬 실행
- `deploy/scripts/deploy.sh`: source bare mirror, branch HEAD, compose isolation, edge alias, volume, image label/digest, backup/migration/healthcheck 검증
- `deploy/runtime.yml`: staging/production runtime compose. PostgreSQL는 project default network만, 앱은 환경별 external edge network에 alias로 연결
- `deploy/edge.yml`와 `deploy/edge.Caddyfile`: 두 환경이 공유하는 단일 Caddy edge. 공개 포트는 80/443뿐이다.

## 환경 격리 계약

| 항목 | staging | production |
| --- | --- | --- |
| branch | `develop` | `release` |
| Compose project | `dweb-staging` | `dweb-production` |
| edge network | `dweb-staging-edge` | `dweb-production-edge` |
| image namespace | `ghcr.io/<owner>/<repo>/staging` | `ghcr.io/<owner>/<repo>/production` |
| DB volume | `dweb-staging_postgres_data` | `dweb-production_postgres_data` |
| payment | `test`, 신규 결제 기본 차단 | 사용자 승인 전 `test`, 신규 결제 기본 차단 |

legacy staging volume `dweb-staging_postgres_data`와 `dweb-staging_caddy_data`, `dweb-staging_caddy_config`는 보존한다. production은 별도 volume과 secret을 사용한다. 인증 키, DB 비밀번호, R2 bucket과 접근 키의 환경 간 중복은 서버가 거부한다. R2 사용 시 생략된 bucket 이름도 backend 기본값을 적용해 비교한다. OAuth/PortOne/Resend는 환경별 콜백·사용 범위를 운영자가 별도로 설정하며 코드가 자격증명 분리를 자동으로 검증하지는 않는다.

## 서버 bootstrap 계약

`~/d-web-deploy`는 운영 사용자 소유이며 700이다. `source.git`, `staging`, `production`, `backups`, `edge`를 새로 사용하고, 기존 `root`, `source`, `backend.env`, `deploy.env`는 삭제·덮어쓰지 않는다. `deploy.sh`는 repository URL을 public GitHub HTTPS 형식으로 제한하고 release directory와 state path의 symlink를 거부한다.

Docker group이 없는 `sy3058`에서는 최초로 `sudo docker`를 사용한다. group 변경은 사용자 수동 승인·재접속 대상이며 CD가 실행하지 않는다.

```bash
sudo usermod -aG docker sy3058
# 로그아웃 후 SSH 재접속
id -nG
docker version
```

새 CD 트리는 `bin/dispatch.sh`, `bin/deploy.sh`, `bin/run-job.sh` 세 스크립트를 `install -m 750`으로 설치한다. `repository.url`은 기존 파일을 덮어쓰지 않는 최초 bootstrap에서만 작성하고, `deploy/environments/staging.env.example`와 `production.env.example`를 각각 새 환경 파일로 `cp -n`한다. 기존 `root`, `source`, `backend.env`, `deploy.env`는 유지한다. `dispatch.sh`가 `SSH_ORIGINAL_COMMAND`를 직접 처리하므로 deploy wrapper는 두지 않는다.

edge 전환은 기존 external network와 volume을 확인한 뒤에만 수행한다. `dweb-staging-caddy-1`이 포트를 점유하면 해당 컨테이너만 중지하고 새 shared edge를 기동한다. 실패 시 새 edge만 중지하고 기존 Caddy를 재기동하며 DB·인증서 volume은 삭제하지 않는다. network는 `inspect`가 실패한 경우에만 `create`한다. 저장소 파일은 `deploy/edge.yml`, `deploy/edge.Caddyfile`이며 edge 작업 위치는 `~/d-web-deploy/edge`다.

## GitHub 활성화 계약

각 Environment에 staging·production별 별도 `SSH_PRIVATE_KEY`, `SSH_KNOWN_HOSTS`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`을 secret으로 등록한다. `SSH_HOST`, `SSH_USER`, `SSH_PORT`, `API_HOST`는 environment variable이다. `STAGING_DEPLOY_ENABLED`와 `PRODUCTION_DEPLOY_ENABLED`는 Environment variable이 아니라 Repository Variables이며 기본적으로 `false` 또는 미설정이다. 최초에는 staging, release 순서로 각 flag를 임시 활성화해 수동 CI로 내부 기동하고 완료 후 다시 끈다. 두 환경 내부 health 확인 후 edge 전환·브라우저 검증을 거쳐 정기 자동 배포를 활성화한다. 구체적인 최초·정기 절차는 [운영 가이드](../../../guides/GUIDE_CONTINUOUS_DEPLOYMENT.md#활성화-순서와-수동-비활성화)를 따른다. GHCR가 private이면 서버의 read:packages 로그인 자격증명도 별도 bootstrap 대상이다.

배포 키는 `authorized_keys`의 `restrict,command="/home/sy3058/d-web-deploy/bin/dispatch.sh staging"`와 production용 별도 명령으로 제한하고 agent forwarding, port forwarding, TTY를 허용하지 않는다. 두 환경은 각각 Self-hosted Access application과 별도 service token을 사용하며 published SSH route는 `ssh://localhost:22` outbound tunnel이다. 이 경로는 UFW 변경 없이 기존 개인 SSH 키 로그인을 유지한다. known hosts에는 검증한 VPS 공개 host key를 Cloudflare 접속 hostname으로 등록하며 StrictHostKeyChecking을 끄지 않는다.

공식 근거는 [Cloudflare SSH published application](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ssh-cloudflared-authentication/)과 [Cloudflare service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)이다. CI ProxyCommand는 workflow가 설치한 pinned `cloudflared`에 `access ssh --hostname`를 호출하는 현재 스크립트 계약을 따른다.

## 배포 순서와 실패 경계

서버 worker는 전체 SHA가 대상 branch의 HEAD인지 확인한 뒤 bare mirror에서 release를 추출한다. compose config를 JSON으로 검사해 다음을 보장한다.

- 앱 이미지 세 개와 migrate가 같은 요청 SHA를 사용한다.
- staging과 production의 edge network, project name, image namespace, postgres volume이 교차하지 않는다.
- 앱과 PostgreSQL에 published port가 없다.
- PostgreSQL가 edge network에 붙지 않는다.
- staging의 payment environment는 `test`다.

그 뒤 GHCR image digest와 OCI revision label을 확인하고 image lock을 만든다. PostgreSQL을 기동해 gzip dump를 먼저 만든다. backup이 비어 있거나 실패하면 migration하지 않는다. migration 성공 후 API, frontend, admin을 healthcheck와 함께 기동하고 `current.sha`와 `previous.sha`를 갱신한다. `docker compose down -v`는 어떤 rollback 절차에도 사용하지 않는다.

`dispatch.sh`는 job lock을 새 detached worker에 상속한다. SSH monitor 연결 종료는 worker를 중단하지 않는다. 같은 SHA의 중복 요청은 실행 중 작업에 붙는다. 이미 완료한 작업의 재요청은 성공 기록을 재사용하지 않고 worker를 다시 실행해 branch HEAD·이미지·실제 기동 상태를 검증한다. 과거 SHA 재요청은 HEAD 검증에서 실패하며, 현재 SHA 재요청은 백업·migration·healthcheck까지 실제 배포를 반복한다. `status`는 job 이력 조회다. 재부팅 등으로 stale `running` 상태만 남으면 lock 확인 뒤 재시작한다. 다른 SHA·환경의 실제 DB 작업은 공용 lock으로 직렬화한다. migration 실패 시 API는 중지 상태일 수 있으며 자동 DB rollback은 수행하지 않는다.

최초 bootstrap은 두 환경을 각각 임시 flag와 수동 CI로 내부 기동한 뒤 flag를 다시 끄고 shared edge로 전환한다. 이후 브라우저 확인·production 초기 데이터 준비를 마치고 정기 자동 배포 flag를 켠다. staging 브라우저 확인 후 release 승격이라는 정기 배포 순서는 최초 edge 전환 전의 bootstrap 선행조건으로 적용하지 않는다.

## 로컬 검증 (2026-11-25)

- deployment 정책·격리·ProxyCommand·실제 Compose parser 테스트 15개 통과
- 배포 worker·digest 검증·백업 실패·재시도 테스트 14개 통과. 완료한 SHA의 재요청에서 HEAD 불일치·실제 재배포·health 실패도 검증
- 기존 branch policy 테스트 24개, actionlint, shell 구문 검사 통과
- backend format/lint 및 1,270개 테스트 통과
- frontend lint/Astro check/build 및 388개 테스트 통과
- admin lint/build 및 139개 테스트 통과
- 합성 환경 파일로 실제 Docker 두 project를 기동해 각각 migration 성공과 postgres/api/frontend/admin healthy 확인
- 양쪽 Alembic revision `b4c9d0e1f2a3`, staging 전용 테이블이 production에 없고 volume·edge network도 별도임을 확인
- 실제 `pg_dump -Fc` gzip 산출물을 `pg_restore --list`로 검사
- edge Compose config와 공식 Caddy 이미지의 `caddy adapt` 통과
- 검증용 컨테이너·volume·network·이미지 정리 후 잔존 리소스 0개 확인

Docker smoke에서는 로컬 이미지의 원격 pull만 막는 임시 `pull_policy: never` override를 사용했다. 실제 배포는 GHCR pull 후 digest lock으로 기동한다. 실제 Cloudflare Access 인증, GHCR 원격 publish/pull과 VPS 적용은 이 로컬 검증에 포함하지 않는다.

## 남은 수동 활성화 TODO

- staging/production 각각의 Cloudflare Tunnel SSH hostname, Self-hosted Access application, 별도 service token 생성
- 배포 사용자와 환경별 forced-command public key 설치. wrapper는 만들지 않음
- `repository.url`, staging/production env 파일과 backend secret 파일을 Git 밖에 생성
- 기존 staging Caddy/PostgreSQL volume과 network를 실제 서버에서 확인
- GitHub Environment variables/secrets 등록, staging flag 단독 활성화
- production 신규 DB의 owner/content/R2 초기화, staging browser smoke와 backup/restore rehearsal 후 production 활성화 승인

구현은 실제 외부 서비스가 활성화되었다는 증거를 만들지 않는다. 공개 HTTPS, 브라우저 로그인, 결제, 외부 포트 차단, 백업 복구는 사용자가 별도 확인해야 한다.
