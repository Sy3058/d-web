# 공통 페이지 레이아웃

## 목적과 구성

계정은 `py-8`, 구매 내역·설정은 `py-16`, 수정 화면은 `py-12 sm:py-16`을 직접 사용해 페이지 시작 위치가 달랐다. 2026-11-20 사용자 요청으로 페이지 바깥 여백·폭·제목 간격을 공통화했다. 기존 디자인의 1140px·720px 폭과 Tailwind 간격 단위를 재사용하고, 역할별 토큰의 실제 값은 `frontend/src/styles/globals.css` 한곳에서 관리한다.

정적인 Astro 컴포넌트와 슬롯으로 구성한다. 데이터·행동과 표현을 분리하는 조합 방식을 적용하며 새 UI 라이브러리나 클라이언트 상태는 추가하지 않는다. 기존 `BaseLayout`은 문서 head·내비게이션·푸터를 계속 소유한다.

| 구성 | 책임 |
| --- | --- |
| `PageContainer.astro` | `width=reading\|wide\|compact`, `spacing=page\|none\|viewer`, HTML 속성·class 전달과 기본 본문 슬롯 |
| `PageHeader.astro` | 제목과 선택적인 `title`, `eyebrow`, `description`, `meta`, `actions` 슬롯. `page\|reader` 변형 |
| `PageLayout.astro` | BaseLayout·컨테이너·머리말 조합. 기본 머리말은 문서 제목을 재사용하며 `heading` 또는 `header` 슬롯으로 변경 |
| `AuthLayout.astro` | 공통 컨테이너 안의 인증 패널·제목·본문과 OAuth 오류를 위한 `before-header` 슬롯 |

```astro
<PageLayout title="구매 내역">
  <PurchaseHistory client:load />
</PageLayout>
```

커스텀 머리말은 아래처럼 조합한다. 페이지별로 여백 숫자를 다시 지정하지 않는다.

```astro
<PageLayout title="목록" width="wide">
  <PageHeader slot="header" title="목록">
    <a slot="actions" href="/works">작품 보기</a>
  </PageHeader>
  <p>본문</p>
</PageLayout>
```

## 토큰과 적용 범위

- 모든 독자 페이지의 바깥 컨테이너를 공통화했다. 계정 영역은 동일한 720px 폭·반응형 여백·제목 간격을 사용한다. 홈·작품·커미션은 1140px, 결제 복귀는 기존 512px 폭을 선택한다.
- Navbar와 Footer도 같은 폭·좌우 여백을 사용한다. Footer의 수직 간격은 독립 토큰이며 Navbar 높이는 기존 값을 유지한다.
- 인증 패널은 기존 400px과 테두리를 재사용하고 모바일에서는 패널 테두리를 생략한다.
- 에피소드 공개 SSR의 `PageHeader`와 비공개 구매 회차 React 머리말은 같은 전역 CSS를 쓴다. ClientRouter 왕복 뒤에도 유지되도록 BaseLayout이 항상 읽는 `globals.css`에 규칙을 둔다.
- 뷰어의 4.5rem·5.5rem 고정 컨트롤 예약 공간과 safe area는 별도 토큰으로 유지한다. 2026-11-20 사용자 화면 피드백으로 상단에는 공통 `--spacing-page-y`(32px)를 추가해 고정 바와 작품명 사이 간격을 약 16px에서 48px로 넓혔다. 공개 SSR·비공개 구매 회차 모두 같은 viewer 컨테이너 규칙을 사용한다. 본문 관측 블록과 진행도 인덱스는 바꾸지 않는다.
- 조건부 자식이 비어도 `Astro.slots.has`는 true일 수 있다. 보조 슬롯은 `Astro.slots.render`의 실제 출력이 있는 경우에만 래퍼·간격을 생성한다. `set:html`에는 Astro가 렌더하고 이스케이프한 슬롯 결과만 전달하며 원시 사용자 입력을 전달하지 않는다.

렌더 모드·응답 헤더·인증 조회·구매 및 콘텐츠 인가·React hydration 지시자는 기존 페이지에 남겼다. CSS 프레임워크·의존성·Backend·Admin 동작은 이 공통화에서 변경하지 않는다.

## 검증

Frontend lint·Astro check·단위 테스트·build와 production SSR HTTP 검증으로 확인한다. SSR 테스트는 계정 5개 경로의 익명·정상 인증·장애 상태에서 같은 컨테이너·단일 h1이 나오는지 비교하며, 인증 레이아웃의 오류 슬롯·폼, 커미션 actions 슬롯과 빈 부제의 여백 생략도 검증한다. 브라우저 실기능·시각 확인은 사용자가 수행한다.

2026-11-20 최종 결과: lint 통과, Astro check 115 files·오류/경고 0·기존 hint 1, 단위 테스트 377개, build, SSR HTTP 19개 통과. 빌드 CSS에서 반응형 컨테이너 규칙과 뷰어 safe area 토큰 참조를 확인했다. API·독자 `/my`·Admin 개발 서버는 HTTP 200을 확인했다. 기존 Sentry 토큰 미설정·transitions sourcemap 경고는 유지된다. Backend·Admin 코드와 실행 설정을 이 공통화에서 변경하지 않아 앞선 검증을 반복하지 않았다.

같은 날 사용자 홈 확인에서 `Could not import ../components/layout/PageContainer.astro`를 보고했다. 실제 파일과 경로는 존재하고 다른 페이지는 정상 응답했지만 홈은 500 `FailedToLoadModuleSSR`이었다. 실행 중인 서버의 `.astro/dev.log`에서 HMR route 갱신 실패와 홈의 import 실패를 확인했다. 해당 4321 개발 서버만 SIGTERM으로 정상 종료하고 동일 프로젝트·포트로 재시작하자 코드나 디스크 캐시 변경 없이 복구됐다. 이후 홈·계정 5개·인증 3개·작품·커미션 총 11개 경로의 HTTP 200과 오류 셸 부재, live Viewer TipTap 의존성 200을 확인했다. 최초 완료 검증에서는 실제 dev 홈 진입을 누락했으며 production SSR 테스트 통과가 실행 중인 dev의 모듈 상태까지 보장하지 않는다는 한계가 있었다.

API와 문법은 [Astro 슬롯](https://docs.astro.build/en/basics/astro-components/#slots), [Astro 타입 유틸리티](https://docs.astro.build/en/guides/typescript/#componentprops-type), [Tailwind 테마 토큰](https://tailwindcss.com/docs/theme)을 기준으로 확인했다.
