# 의존성 보안 수정 (2026-11-12)

## 범위

일일 점검에서 확인한 CA 신뢰 bundle과 관리자 에디터 붙여넣기 취약점의 수정 버전을 활성 worktree에 반영한다. 기존 구매 내역·영수증 구현 변경은 파일 해시로 보존을 확인했다. 다른 취약점 후보, 보존용 detached worktree와 복구 snapshot은 이번 업데이트에 포함하지 않는다.

| 대상 | 이전 버전 | 수정 버전 | 반영 위치 |
| --- | --- | --- | --- |
| certifi | 2026.5.20 | 2026.10.19 | Backend 직접 의존성 하한, uv.lock, 로컬 Backend 환경 |
| uv | Docker 0.11.17, 로컬 0.11.16 | 0.13.4 | Backend Dockerfile, 로컬 uv 실행 파일 |
| prosemirror-view | 1.42.1 | 1.42.3 | pnpm workspace override, pnpm-lock.yaml, FE·Admin 설치 그래프 |

certifi는 `oauth_service`가 직접 import하고 HTTPX도 사용하는 런타임 의존성이므로 `backend/pyproject.toml`에 보안 수정 하한을 명시했다. `uv lock --upgrade-package certifi==2026.10.19`로 해당 패키지만 갱신하고 frozen sync로 설치했다. uv 0.13.4가 lock revision을 3에서 5로 갱신했으며 새 Docker 이미지에서도 같은 uv로 frozen sync를 검증했다. CI는 `setup-uv`에서 별도 버전을 고정하지 않으므로 현재 기본 버전 설치 경로를 유지한다.

ProseMirror는 FE·Admin 공통의 TipTap 간접 의존성이다. 상위 TipTap 버전을 일괄 올리는 대신 workspace override로 수정 버전을 고정해 두 앱이 같은 버전을 해석하게 했다. pnpm이 재생성한 Linux native package의 libc 메타데이터도 lock에 포함됐다. 실제 잠금 패키지 집합을 비교해 JS에서는 prosemirror-view만, Python에서는 certifi만 버전이 바뀐 것을 확인했다. 무관한 패키지 버전은 갱신하지 않았다.

## 검증

- `uv sync --frozen` 통과. 로컬 `uv --version`은 **0.13.4**, Backend 설치 certifi는 **2026.10.19**다. 실제 CA 목록에 `emSign ECC Root CA - G3`가 없는 것을 확인했다.
- `pnpm install --frozen-lockfile --ignore-scripts` 통과. `pnpm why prosemirror-view`로 FE·Admin 모두 **1.42.3 한 버전**만 해석하는 것을 확인했다.
- Backend Ruff format **116 files**·Ruff check, pytest **1,147 passed**(93.73초).
- Frontend lint·Astro check·**241 tests**·build 통과. Astro check는 기존 unused import hint 1건이며 error와 warning은 0이다. build의 Sentry token 미설정·Astro transitions sourcemap 경고는 별도이며 이번 변경에서 설정을 바꾸지 않았다.
- Admin lint·**119 tests**·build 통과. 잠금 갱신의 `openapi-typescript` TypeScript 5 peer 요구와 설치 TypeScript 6 경고는 기존 버전 조합이며 검증은 통과했다.
- Backend Docker 이미지를 별도 로컬 태그 `d-web-backend-security-check:20261112`로 빌드했다. 실제 이미지의 uv **0.13.4**, certifi **2026.10.19**와 문제 CA 부재를 확인했다. 빌드된 Python base는 **3.12.16**이다. 기존 서비스 재시작·배포는 하지 않았다.
- OSV 공식 API에서 수정한 세 정확한 버전을 재조회했고 조회 범위에서 연결된 공지가 발견되지 않았다. 이는 전체 의존성이나 컨테이너 OS의 무취약성을 보장하지 않으며 일일 보고서의 다른 확인 필요 항목을 종결하지 않는다.
- 기존 구매 내역·영수증 등 미커밋 13개 파일의 SHA256이 업데이트 전과 동일하다. 브라우저 실기능 확인은 사용자 담당이며 이번에는 실행하지 않았다.

## 반영과 한계

현재 코드는 새 이미지 빌드 시 수정 버전을 사용한다. 이미 실행 중인 API·dev server와 배포 이미지는 자동 갱신되지 않으므로 운영 반영은 별도 재빌드·재배포가 필요하다. 보존용 worktree와 복구 snapshot의 이전 lock·Dockerfile은 이력 자료이며 활성 코드의 완료 근거로 사용하지 않는다. 커밋·push는 수행하지 않았다.

## 공식 근거

- [certifi CA 제거 공지](https://github.com/advisories/GHSA-6q48-6c7w-9gw2): compromised emSign CA의 신뢰 제거. 2026.10.18이 최초 수정 버전이고 2026.10.19는 영향 없는 root를 복원한 권장 버전이다.
- [uv CA 제거 공지](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62), [uv 0.13.4 릴리스](https://github.com/astral-sh/uv/releases/tag/0.13.4).
- [ProseMirror paste XSS 공지](https://github.com/advisories/GHSA-c8x8-7fp4-3x9w): 1.42.3에서 수정.
- [pnpm workspace overrides](https://pnpm.io/10.x/settings#overrides), [uv dependency upgrade](https://docs.astral.sh/uv/concepts/projects/sync/#upgrading-locked-package-versions).

## 2026-11-19 Pillow·Vite 업데이트

- Backend의 Pillow 하한과 잠금 버전을 12.3.0에서 13.0.0으로 올렸다. `uv lock --upgrade-package pillow==13.0.0`과 `uv sync --frozen`을 실행했고, 잠금 파일에서 Pillow만 버전이 바뀌었다. [Pillow JPEG 공지](https://github.com/python-pillow/Pillow/security/advisories/GHSA-8g5g-8vmr-9782) · [Pillow OpenJPEG 공지](https://github.com/python-pillow/Pillow/security/advisories/GHSA-78g4-xqwv-q3g8)
- 공지의 Vite 수정 버전 8.2.5는 npm 레지스트리에서 조회되지 않아, 같은 8.2 계열에서 배포가 확인된 8.2.6을 선택했다. Admin 하한과 워크스페이스 잠금 파일을 갱신했다. 잠금 파일에는 Vite 및 필요한 Rolldown, PostCSS, picomatch 하위 의존성 변경을 반영했다. `pnpm why vite`로 Astro·Tailwind·Vitest 및 Admin 플러그인이 모두 8.2.6을 해석하는 것을 확인했다. 기존 frontend의 `react-easy-crop` 의존성 변경은 보존했다. [Vite 보안 공지](https://github.com/vitejs/vite/security/advisories/GHSA-p4f5-76q4-ffq7) · [Vite 8.2.6 릴리스](https://github.com/vitejs/vite/releases/tag/v8.2.6)
- Node 24.22.3과 pnpm 10.24.0으로 `pnpm install --frozen-lockfile --ignore-scripts`를 실행했다. Frontend Node 하한을 24.22.3으로 올렸다.
- Backend에서 Pillow 13.0.0 import 및 Ruff format 126개 파일·Ruff check를 확인했다. Frontend lint·Astro check·단위 테스트 352개·build, Admin lint·단위 테스트 123개·build가 통과했다. Astro check는 기존 unused import hint 1건을 보고했고, Frontend build는 Sentry 토큰 미설정 및 Astro transitions sourcemap 경고를 출력했다.

### 런타임·DB 적용과 추가 검증

- 로컬 uv를 0.13.9로 갱신해 Python 3.12.16 빌드 목록을 받은 뒤 설치했다. 기존 `.venv`는 `backend/.venv.pre-security-20261119.local`에 보존하고 새 환경을 frozen sync했다. `.python-version`과 Docker base는 3.12.16, Docker의 uv는 0.13.9로 맞췄다. 새 Python·Pillow·PostgreSQL 조합에서 Ruff와 Backend pytest **1,243개**가 통과했다.
- nvm의 Node 24.22.3 설치 및 기본 별칭 전환, FE·Admin Docker builder와 FE runtime 태그 갱신을 완료했다. 개발 API도 정상 종료 후 새 Python으로 재시작했고 `/`의 정상 응답과 실행 파일을 확인했다.
- d-web PostgreSQL 16.14를 **16.16-alpine**으로 교체하고 기존 named volume을 유지했다. 개발·CI 이미지를 16.16으로 고정했다. 전체 cluster dump를 Git 제외 `secrets/security-update-20261119/`에 권한 0600으로 보관하고, 외부 포트·영구 볼륨이 없는 임시 PostgreSQL 16.16에서 전체 복원과 public 테이블 17개를 확인했다. 설치된 확장은 plpgsql뿐이고 `bpchar` 컬럼은 없어 해당 REINDEX 필수 조건은 없다.
- API·FE·Admin Docker 빌드가 통과했다. 이미지 내부 Python **3.12.16**, Pillow **13.0.0**, uv **0.13.9**, Node **24.22.3**, nginx **1.31.9**를 확인했다. root/backend `.dockerignore`에 비공개 백업과 `*.local` 제외를 추가하고 최종 빌드를 확인했다. API·FE·Admin Docker 서비스는 배포하지 않았다.
- WSL Git은 공식 kernel.org 소스·SHA256을 대조해 사용자 경로에 **2.56.1**을 설치했다. 시스템 Git은 보존했고 기본 PATH가 새 Git을 선택한다. HTTPS 원격 조회와 credential 테스트 **56개**를 통과했다. 이 사용자 빌드는 Rust 구성 요소·번역·Tcl/Tk GUI를 포함하지 않는다.
- Windows Git **2.56.1.windows.1**, 기본 Microsoft JDK **17.0.21.1+2**, Oracle JDK **25.0.5.1+4**를 설치·확인했다. STS는 별도 Microsoft JDK **21.0.13.1+2**로 실행하도록 변경했다. Android Studio의 앱 등록은 **2026.2.2.9**로 바뀌었으나 설치 프로그램은 1223을 반환했으므로 무조건적인 설치 성공으로 해석하지 않는다. Android의 `STUDIO_JDK`와 VS Code Java 언어 서버는 패치된 Oracle JDK 25를 지정했다. IDE 화면 기동과 기존 창 재시작은 하지 않았다. 이전 JDK·내장 런타임은 남아 있으므로 모든 Java 설치본을 제거·수정했다고 주장하지 않는다. Windows 설정 백업은 사용자 Temp의 `d-web-security-update-20261119`에 있다.
- 같은 호스트의 make-the-one도 Node **24.22.3**, Next.js **16.4.6**, PostgreSQL **16.16** 설정으로 갱신했다. 기존 DB 전체 백업의 별도 복원(14개 public 테이블), 기존 볼륨의 새 버전 기동과 전체 REINDEX를 확인했고 원 서비스는 중지 상태로 보존했다. 상세 구현·검증은 해당 저장소와 원본 PRD에 기록한다.
- 별도 세션의 오늘 공지 검색 완료 결과를 확인했다. GitHub 피드 첫 100건과 KEV·주요 공급업체 공지의 범위이며, 과거의 다른 조건부·미해결 판정은 유지한다. 이 작업은 확인된 대상의 업데이트와 호환성 검증이며 전체 시스템·전체 의존성의 무취약성 판정이 아니다. 커밋·push·tag는 수행하지 않았다.
- 최종 Node 24.22.3에서 Frontend HTTP·SSR 통합 검사 **16개**도 통과했다. 기존 터미널·Codex 앱 프로세스의 상속 PATH는 이전 Node를 유지할 수 있으므로 새 셸을 열거나 `nvm use 24.22.3`을 실행한다. Windows IDE도 기존 창을 저장 후 다시 열어 새 JDK 설정을 반영해야 하며 UI 실기능 확인은 사용자 담당이다.

공식 근거: [Node 11월 보안 릴리스](https://nodejs.org/en/blog/vulnerability/november-2026-security-releases/), [Python 3.12.16](https://www.python.org/downloads/release/python-31216/), [PostgreSQL 16.16 업데이트 지침](https://www.postgresql.org/docs/16/release-16-16.html), [Git 보안 공지](https://github.blog/open-source/git/git-security-vulnerabilities-announced-7/), [Java 25.0.5.1 보안 기준](https://www.oracle.com/java/technologies/javase/25-0-5-1-relnotes.html).

### 구버전 정리 후속

- 사용자 명시 요청으로 실행 파일·설정 참조를 확인하고 Oracle JDK 24.0.1, nvm Node 24.16.0·24.22.2, uv Python 3.12.13을 제거했다. 현재 Codex는 별도 standalone 경로를 사용하므로 Node 24.16.0에 남은 이전 npm Codex 설치의 제거와 독립적이다. Microsoft JDK 17.0.16.8은 이미 제거된 상태였다.
- 앞선 업데이트 뒤에도 FE·Admin dev 프로세스는 Node 24.22.2를 계속 사용하고 있었다. 같은 포트와 host로 정상 종료·재시작하고 실제 `/proc` 실행 파일이 24.22.3을 가리키는 것을 확인했다. Admin은 Vite 8.2.6으로 시작했고 FE·Admin·API의 HTTP 200 응답을 확인했다. 이전 Node·Python 실행 파일을 사용하는 프로세스는 없었다.
- 기존 Backend 가상환경의 재귀 영구 삭제는 저장소 보호 훅이 차단했다. 보호 훅을 바꾸지 않고 복구 가능한 휴지통으로 이동했으므로 약 214MB는 휴지통에 남아 있다. 활성 Backend의 Python 3.12.16·Pillow 13 import를 재확인했다. make-the-one 보안 도구의 minor alias도 실제로는 Python 3.12.16을 가리켜 제거한 3.12.13에 의존하지 않았다.
- 중지된 API·FE·Admin 컨테이너에는 cache/runtime 파일 외의 데이터 변경이 없음을 확인하고 파일 변경 목록과 nginx 설정을 비공개 백업에 보존했다. 컨테이너를 새 이미지로 교체하되 시작하지 않았고 이전 앱 이미지 세 개의 부재를 확인했다. 이전 PostgreSQL 16.14·16.15 및 11월 12일 검증 이미지를 제거했다. 다른 프로젝트용 이미지·모든 DB 볼륨·검증된 DB 백업은 유지했다.
- 사용자가 Android Studio를 직접 제거해 새로 추가했던 `STUDIO_JDK` 사용자 환경변수를 원복했다. Windows 설치용 임시 다운로드 약 1.97GB를 정리하고 설정 백업 세 개는 보존했다. STS·VS Code의 구형 내장 JRE는 배포 구성품이므로 폴더를 임의 삭제하지 않았고, 실제 실행 설정은 수정된 외부 JDK를 유지한다. APT 관리 Git과 시스템 Python도 유지했다. 기존 터미널·IDE의 상속 환경은 새 세션에서 갱신해야 한다.

## 2026-11-23 Astro 이미지 경로 경계 수정

사용자 요청으로 최신 `origin/develop`에서 `fe/fix/astro-image-path` 브랜치와 별도 worktree를 만들었다. 기존 `common/feat/staging-deployment`의 미커밋 배포 설정은 원래 worktree에 보존한다.

### 대상과 변경

- `GHSA-r3h5-4585-7x3w` / `CVE-2026-126364`: Node adapter의 이미지 엔드포인트가 Linux에서 대소문자만 다른 출력 경로를 허용하는 문제다. Astro 7.4.7에서 수정되며 adapter만 갱신해서는 해결되지 않는다.
- frontend의 Astro 하한을 `^7.4.7`, 실제 잠금을 `7.4.7`로 변경했다. `@astrojs/node`는 호환 peer 범위 안의 기존 `11.1.4`를 유지했다.
- Astro가 사용하는 `@astrojs/internal-helpers`는 `0.13.1`로 갱신된다. adapter 등 다른 경로에 기존 helper `0.10.4`가 남아 있어도 이미지 엔드포인트는 Astro의 수정된 helper를 사용한다. 단순히 old helper 문자열이 존재하는지만으로 이 공지의 잔존을 판정하지 않는다.
- 새 Astro는 Vite `^8.3.5`를 요구하므로 frontend의 실제 Vite는 `8.3.8`이다. Admin의 직접 Vite는 `8.2.6`을 유지했다. Astro 하위 compiler·markdown·Sharp·Shiki·Zod·devalue 등의 새 의존성 및 peer snapshot도 lockfile에 반영됐다. 다른 직접 의존성 하한을 일괄 올리거나 override로 강제하지 않았다.
- Node 24.22.3·pnpm 10.24.0으로 별도 설치했으며 원본 worktree의 node_modules·env 파일을 복사하거나 연결하지 않았다. frozen offline install과 diff 검사를 통과했다.

### HTTP 회귀 검사와 한계

기존 `frontend/tests/viewer-ssr.check.mjs`에 다음 검사를 추가했다. 브라우저나 Playwright를 사용하지 않고 실제 production SSR 빌드를 localhost로 실행한다.

1. `dist/client`와 대소문자만 다른 `dist/CLIENT`가 서로 다른 inode인 Linux 파일시스템임을 확인한다.
2. 고유 파일명과 무해한 SVG로 공개 정적 이미지의 200 응답을 확인한다.
3. `/_image?href=/../CLIENT/...&w=32&f=svg`가 파일 경계에서 400으로 거부되고 비공개 표시 문자열을 반환하지 않는지 확인한다.
4. 생성한 고유 파일만 정리한다. 기존 CLIENT 디렉터리는 보존하고 테스트가 만든 디렉터리만 비재귀로 제거한다.

현재 앱은 Sharp를 직접 설치하지 않아 production bundle의 정상 최적화 요청이 `MissingSharp`로 실패할 수 있다. 이 기능을 새로 활성화하기 위해 의존성을 추가하지 않았다. 그래서 정상 대조는 정적 이미지 제공으로 확인하고, 공격 경로는 **이미지 처리에 도달하기 전 400 거부**를 검사한다. 구버전 7.2.4 이미지에서는 경계를 통과해 이미지 처리까지 진행한 뒤 MissingSharp로 500이 발생해 새 검사가 실패했고, 수정본은 400으로 거부해 통과했다. 실제 원고·비밀 파일을 읽거나 유출 성공을 주장하는 검증은 아니다.

### 검증과 반영

- Frontend lint·Astro check·단위 테스트 377개·build와 HTTP SSR 검사 20개 통과.
- frontend Docker 이미지 빌드 후 동일 HTTP SSR 검사 20개를 다시 통과했다. 임시 컨테이너는 network none으로 외부 통신과 포트 공개 없이 실행·자동 제거했다.
- Admin lint·단위 테스트 139개·build 통과. 공유 잠금의 peer graph 변경을 함께 검증했다.
- 기존 unused import hint 1건, Sentry 토큰 미설정 및 transitions sourcemap 경고는 유지된다.
- Backend 의존성·코드는 변경하지 않았다. 기존 서버와 원본 worktree의 개발 프로세스는 재시작하지 않았다.
- 실제 배포 적용에는 이 브랜치의 develop 병합과 배포 작업 브랜치의 최신 코드 반영, release 승격 후 이미지 재빌드가 필요하다. 기존 이미지와 실행 중 프로세스는 자동으로 수정되지 않는다. 커밋·push·배포는 수행하지 않았다.

공식 근거: [Astro 보안 공지](https://github.com/withastro/astro/security/advisories/GHSA-r3h5-4585-7x3w), [Astro 7.4.7 릴리스](https://github.com/withastro/astro/releases/tag/astro%407.4.7), [pnpm 사용 시 Sharp 의존성 안내](https://docs.astro.build/en/guides/images/#default-image-service).
