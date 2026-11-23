# 로컬 개발과 배포 구성 확인

평소에는 WSL에서 앱 개발 서버를 실행하고 DB만 Docker로 유지한다. 로컬 Docker 전체 구성과
VPS 스테이징은 배포 전 확인 단계다. 실행 중인 `localhost`는 VPS 스테이징이 아니다.

## 최초 준비

- Node.js 24.22.3 이상, pnpm, uv, Docker Desktop과 WSL 통합이 필요하다. 실행 스크립트는 Bash와 `setsid`를 사용한다.
- 저장소 루트에서 `pnpm install --frozen-lockfile`, `backend/`에서 `uv sync --frozen`으로 의존성을 준비한다.
- 각 영역의 `.env.example`을 참고해 로컬 환경을 준비한다. 기존 환경 파일을 덮어쓰거나 비밀값을 커밋하지 않는다.
- Backend의 `DATABASE_URL`은 로컬 PostgreSQL을 가리켜야 한다. 개발과 스테이징의 DB·스토리지·자격증명은 분리한다.

최초 실행이나 새 migration이 있을 때 로컬 DB를 준비한다.

```bash
pnpm dev:db
cd backend
uv run alembic upgrade head
cd ..
```

## 평소 개발

저장소 루트에서 실행한다.

```bash
pnpm dev
```

| 서비스 | 주소 | 실행 방식 |
| --- | --- | --- |
| 독자 사이트 | http://localhost:4321 | Astro dev, HMR |
| 관리자 | http://localhost:5173 | Vite dev, HMR |
| API | http://localhost:8000 | uvicorn reload |
| PostgreSQL | localhost:5432 | Docker, 기존 볼륨 유지 |

명령은 기존 로컬 preview 앱 컨테이너를 중지하고 DB가 준비된 뒤 세 개발 서버를 시작한다.
포트가 이미 사용 중이면 해당 프로세스를 임의로 죽이지 않고 안내 후 종료한다. 모든 개발
서버는 `127.0.0.1`에 바인딩하며, 다른 포트로 자동 변경하지 않는다. 주소는 브라우저에서
일관되게 `localhost`를 사용한다.

Ctrl+C는 이 명령이 시작한 앱과 reload 자식 프로세스만 종료한다. 한 앱이 종료되어도 나머지
앱을 함께 정리한다. PostgreSQL 컨테이너와 데이터는 유지한다. DB도 중지하려면 다음을 실행한다.

```bash
docker compose stop postgres
```

앱을 개별 터미널에서 실행하려면 `pnpm dev:api`, `pnpm dev:fe`, `pnpm dev:admin`을 사용한다.
통합 `pnpm dev`와 중복 실행하지 않는다.

## 로컬 URL과 외부 서비스

개발 명령은 API의 `ENV=development`와 localhost 세 URL, 프런트의 `PUBLIC_API_URL`·
`API_INTERNAL_URL`, 관리자의 `VITE_API_URL`을 로컬 주소로 설정한다. 기존 환경 파일의
API 키를 출력하거나 프런트에 복사하지 않는다.

로컬 기동에서는 `PAYMENTS_ACCEPT_NEW=false`로 신규 결제를 닫는다. 서버가 요구하는 공개
HTTPS 조건을 완화하지 않으며, 결제 redirect·webhook 등 외부 연동은 스테이징에서 확인한다.
로컬 Google OAuth를 사용할 때에는 개발 콜백 `http://localhost:8000/auth/callback/google`을
해당 Google 프로젝트에 등록해야 한다. 공개 환경용 콜백과 구분한다.

## 로컬 Docker 전체 구성 확인

먼저 실행 중인 개발 서버를 Ctrl+C로 종료한다.

```bash
pnpm preview:up
```

이 명령은 `docker compose --profile preview up -d --build --wait`를 실행한다.
독자 사이트는 `http://localhost`, 관리자는 `http://admin.localhost`, API 직접 주소는
`http://localhost:8000`이다. 프런트·관리자는 빌드 산출물을 사용하므로 변경 반영에는 재빌드가 필요하다.
기본 `docker compose up -d`는 PostgreSQL만 실행한다.

```bash
pnpm preview:stop
```

preview 앱 컨테이너만 중지하고 DB·볼륨을 유지한다. 이후 `pnpm dev`로 개발 모드로 돌아간다.

## VPS 스테이징

VPS는 [배포 가이드](GUIDE_DEPLOYMENT.md)와 [배포 파일 안내](../../deploy/README.md)를 따른다.
루트의 `preview` profile과 VPS `deploy/compose.yml`은 서로 다른 실행 구성이다.

## Astro 실행 방식

통합 실행은 Astro의 `--ignore-lock`을 사용해 AI 도구에서도 foreground로 실행한다.
중복 실행은 지정 포트 검사로 막고, 종료는 통합 스크립트가 소유한 프로세스 그룹으로 관리한다.
기존 Astro 캐시 분리는 유지한다. 개발 서버 실행 중 검사·빌드가 dev 캐시를 덮어쓰지 않는다.

- [Astro CLI의 background와 ignore-lock](https://docs.astro.build/en/reference/cli-reference/#--ignore-lock)
- [Vite strictPort](https://vite.dev/config/server-options.html#server-strictport)
