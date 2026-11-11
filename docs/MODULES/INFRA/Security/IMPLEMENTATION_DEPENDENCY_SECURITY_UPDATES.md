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
