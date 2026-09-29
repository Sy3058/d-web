# d-web

> 한 명의 웹툰 작가가 작품을 직접 연재하고 판매하며, 독자가 작품을 탐색하고 이어서 읽을 수 있도록 만드는 웹 플랫폼

독자용 사이트, 작가용 관리 화면, API를 한 저장소에서 개발합니다. 독자는 작품과 회차를 찾아 무료 공개 구간을 읽고, 작가는 관리 화면에서 작품과 에피소드를 작성·공개합니다. 웹툰은 이미지뿐 아니라 텍스트도 포함할 수 있으며, 읽기 경험과 유료 콘텐츠 접근 제어를 함께 설계하고 있습니다.

**진행 상태:** 개발 중. [M2(공개 콘텐츠와 독자용 뷰어)는 완료](docs/milestones/README.md)했고, [M3(결제와 유료 콘텐츠)는 진행 중](docs/milestones/README.md)입니다. 결제·환불·커뮤니티·알림 등 기획된 모든 기능이 현재 서비스된다는 의미는 아닙니다.

## 주요 사용자 흐름

| 사용자 | 화면과 기능 | 현재 범위 |
| --- | --- | --- |
| 독자 | 메인에서 작품 탐색, 태그별 작품 목록, 작품 상세와 회차 목록 | M2 구현 |
| 독자 | 이미지·텍스트가 섞인 회차 읽기, 무료 구간 이후 잠금 안내, 이전·다음 회차 이동 | M2 구현 |
| 독자 | 회원 가입·로그인·이메일 인증, 읽기 위치 저장과 재방문 복원 | M1~M2 구현 |
| 작가 | 별도 관리 화면에서 로그인과 2단계 인증, 작품과 에피소드 작성·편집·공개 예약 | M1.5 구현 |
| 작가 | 메인 소개 문구·프로필·커미션 소개 편집 | M2 구현 |
| 독자·작가 | 결제 후 유료 구간 열람, 환불과 매출 관리 | M3 진행 중, [세부 체크리스트](docs/milestones/README.md) 참조 |

화면 경로는 [`frontend/src/pages/`](frontend/src/pages/), 관리 화면은 [`admin/src/routes/`](admin/src/routes/)에서 확인할 수 있습니다. 기획 범위와 실제 구현 상태는 구분해서 [PRD](docs/PRD.md)와 [마일스톤](docs/milestones/README.md)에 기록합니다.

## 구조와 기술

| 영역 | 기술 | 역할 |
| --- | --- | --- |
| [`frontend/`](frontend/) | Astro, React, TypeScript, Tailwind CSS | 작품 탐색과 뷰어. 공개 페이지는 Astro, 상호작용이 필요한 뷰어는 React |
| [`admin/`](admin/) | React, Vite, TanStack Router·Query, TypeScript, TipTap | 작가용 관리 화면과 에피소드 편집기 |
| [`backend/`](backend/) | FastAPI, PostgreSQL, SQLModel, Alembic | 인증, 작품·회차, 읽기 기록과 콘텐츠 API |
| [`packages/shared/`](packages/shared/) | pnpm workspace | 독자·관리 화면의 공유 코드 |

서버는 공개 요청에서 볼 수 있는 콘텐츠를 결정합니다. 무료 구간은 서버에서 유료 경계 뒤를 잘라낸 다음 허용된 이미지에만 임시 URL을 발급하며, 독자 뷰어는 해당 응답을 받아 표시합니다. 인증은 HttpOnly 쿠키를 사용하고 관리자 접근은 별도 권한으로 제한합니다. 구체적인 계약과 근거는 [콘텐츠 API 문서](docs/MODULES/BE/)와 [설계 결정](docs/DECISIONS.md)에 있습니다.

## 프론트엔드에서 해결한 문제

### 이미지가 늦게 로드되어도 읽던 위치로 돌아가기

긴 세로형 웹툰은 이미지가 나중에 로드되면 문서 높이가 바뀌므로 저장한 스크롤 좌표만으로 읽던 위치를 복원할 수 없습니다. 뷰어는 **콘텐츠 블록 인덱스와 블록 안의 위치**를 저장합니다. 복원할 위치보다 앞선 이미지의 로딩을 기다리고, 대기 상한을 지나면 먼저 복원한 뒤 늦게 도착한 이미지에 맞춰 다시 조정합니다. 사용자가 직접 스크롤하기 시작하면 자동 복원이 그 행동을 덮어쓰지 않게 구분합니다.

- [뷰어](frontend/src/components/viewer/Viewer.tsx) · [뷰어 테스트](frontend/src/components/viewer/Viewer.test.tsx)
- [비회원 진행도 저장](frontend/src/lib/guestProgress.ts) · [관련 테스트](frontend/src/lib/guestProgress.test.ts)

회원의 진행도는 API와 연동하고, 비회원의 기록은 브라우저에 보관합니다. 브라우저 저장소를 사용할 수 없거나 기록이 잘못되어 있어도 열람은 계속할 수 있도록 처리합니다.

### 공개 콘텐츠와 유료 구간의 경계

작품 상세와 회차 목록은 공개 페이지에서 제공하지만, 뷰어 본문의 허용 범위는 서버가 판정합니다. 무료 콘텐츠 API는 유료 경계 이후의 원고와 이미지 키를 응답에서 제외합니다. 프론트엔드는 전달된 블록을 렌더링하고 경계 지점에 잠금 안내를 표시하며, 임시 이미지 URL을 서버 렌더 HTML에 넣지 않습니다. [M2 구현 내역](docs/milestones/README.md)에서 범위를 확인할 수 있습니다.

### 작가용 편집 화면과 독자 화면 분리

작가는 관리 화면에서 작품·표지·태그를 관리하고, TipTap 기반 에디터에서 이미지와 글의 순서 및 공개 시점을 정합니다. 독자용 사이트는 그 결과를 읽는 데 집중합니다. 두 화면을 분리해 서로 다른 접근 권한과 인터랙션을 관리합니다. [관리자 라우트](admin/src/routes/_auth/)와 [독자 라우트](frontend/src/pages/)를 참고하세요.

## 개발 과정과 품질 관리

요구사항과 우선순위는 [PRD](docs/PRD.md), 단계별 완료 조건은 [마일스톤](docs/milestones/README.md), 변경 이유와 실패 사례는 [결정 기록](docs/DECISIONS.md)과 [실수 기록](docs/MISTAKES.md)에 남깁니다. AI 도구를 사용하는 작업에도 이 문서와 현재 코드를 기준으로 범위를 정하고 결과를 검사합니다.

프론트엔드는 Vitest, ESLint, Astro 검사를, 관리 화면은 Vitest와 ESLint를, 백엔드는 pytest와 Ruff를 사용합니다. CI에는 각 앱의 검사·빌드 작업이 구성되어 있습니다. 문서의 완료 표기와 테스트 결과는 해당 시점의 기록이며 운영 서비스의 성능 수치를 뜻하지 않습니다.

## 로컬에서 실행

저장소 루트에서 실행합니다. 독자용 사이트는 `frontend/package.json` 기준 **Node.js 24.16 이상**과 pnpm이 필요합니다. API까지 실행하려면 Python과 Docker, 각 영역의 환경 변수가 추가로 필요합니다. 필요한 설정 키는 영역별 `.env.example`을 확인하세요.

```bash
pnpm install --frozen-lockfile
pnpm --filter frontend dev
```

관리 화면: `pnpm --filter admin dev`. API와 DB 설정은 [`backend/`](backend/)와 [`compose.yml`](compose.yml)을 참고하세요. 비밀 키는 저장소에 추가하지 마세요.

```bash
pnpm --filter frontend lint
pnpm --filter frontend astro check
pnpm --filter frontend test
pnpm --filter frontend build
pnpm --filter admin lint
pnpm --filter admin test
pnpm --filter admin build
```

전체 기능 목록은 [PRD](docs/PRD.md), 현재 완료 여부는 [마일스톤](docs/milestones/README.md)에서 확인할 수 있습니다.
