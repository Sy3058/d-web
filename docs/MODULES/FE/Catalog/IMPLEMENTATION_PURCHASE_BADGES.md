# 작품 회차 목록 구매 배지

## 원인과 범위

2026-11-10 구매자도 회차 목록에서 `잠금`으로 표시되는 문제가 발견됐다. 기존 `EpisodeRow.astro`는 공개 catalog의 유료 구간 유무만 표시했고, `WorkProgress`는 개인 읽기 이력만 조회했다. 구매 권한은 이미 content API에서 판정하지만 목록에는 그 상태가 연결되지 않았다.

M3 foundation 결정 5에 따라 개인 진행도 응답을 확장하고 공개 회차 목록·진행도·CTA를 `WorkExperience` 한 React island로 통합했다. 구매 배지만 먼저 반영하며 회차 전체 진행률·완독·CTA 의미 변경과 구매 내역은 후속이다. DB 모델·마이그레이션·구매 권한·첫 전문 발급 계약은 변경하지 않는다.

## 서버 계약

로그인 전용 `GET /works/{work_id}/progress`의 no-store 응답에 필수 `purchased_episode_ids: UUID[]`를 추가한다. 읽기 이력이 0건이어도 구매 회차 ID를 반환한다. 공개 작품 확인과 기존 진행도 조회에 더해 구매 후보를 한 번의 batch SELECT로 조회하며 회차별 요청이나 N+1 쿼리를 추가하지 않는다.

공개·미삭제 작품/회차와 중앙 `active_purchase_query`로 후보를 제한하고, `episode_access_columns`와 `evaluate_episode_access`로 같은 snapshot의 문서·매니페스트·구매 출처를 판정한다. `full`이면서 활성 purchase ID가 있는 회차만 반환한다. 다른 사용자·환경·비활성 구매·손상 문서는 제외하며 중앙 정책과 다른 별도 주문 상태 조건을 추가하지 않는다.

회차 UUID만 추가하며 본문·이미지 key·URL 반환, presign, 최초 열람·읽기 이력 생성은 하지 않는다. 비공개 구매의 직접 열람은 기존 viewer-bootstrap이 담당하고 이 공개 목록에는 숨긴 회차를 추가하지 않는다. OpenAPI 변경에 따라 Admin 생성 타입을 재생성했다.

## 화면과 캐시

작품 상세는 공개 catalog와 기존 60초 공유 캐시를 유지한다. `WorkExperience client:load`는 SSR에서 공개 회차·무료/잠금·가격·날짜·정렬·첫 화 CTA를 제공한다. hydration 뒤 effect에서 login_hint를 읽고 기존 보호 API wrapper로 개인 응답을 한 번 조회해 구매 배지와 진행도·CTA를 함께 갱신한다.

- 서버 구매 ID에 포함된 회차는 `구매완료`를 우선 표시하고 잠금·가격을 숨긴다. 무료로 전환된 기존 구매도 구매완료가 우선한다.
- 미구매의 잠금·가격과 무료 배지는 유지한다. 공개 catalog에는 구매 필드를 두지 않고 개인 응답의 구매 ID만 판단에 사용한다.
- 비로그인 로컬 진행도는 구매 근거가 아니다. 401·서버 오류 때 공개 배지를 유지하며 진행률·CTA는 기존 M2 의미를 유지한다.
- 정렬은 표시 목록만 바꾸고 CTA는 작가 지정 원본 순서를 사용한다. 작품 ID key와 effect cleanup으로 이전 작품 상태·늦은 응답을 격리한다.

`EpisodeRow.astro`와 `WorkProgress`를 React `EpisodeRow`와 `WorkExperience`로 옮겼다. SSR에 구매 상태를 섞지 않으며 실제 열람은 계속 content API가 인가한다.

리뷰 보완: React 이벤트 등록 전 실패한 SSR 썸네일은 hydration 시 img ref의 `complete && naturalWidth === 0`도 확인해 제거한다. URL 변경 시 이미지를 다시 마운트·검사하며 과거 이미지의 늦은 오류는 현재 ref와 URL이 같은 경우에만 반영한다. SSR 초기 이미지와 정상·로딩 중 이미지는 유지한다. 썸네일 회귀 5개와 결제 리뷰 후속을 포함한 Frontend 전체 241개·SSR HTTP 9개 및 관련 gate가 통과했다.

## 검증

- Backend focused progress·중앙 access **68 passed**, 전체 **1,042 passed**, 전체 Ruff format/check 통과. 전체 결과는 `/tmp/d-web-purchase-badges-pytest.xml`에 기록했다.
- Frontend focused **25 passed**, 결제 모달 후속 포함 전체 **220 passed**, lint·Astro check·build 통과. renderToString→hydrateRoot로 SSR 구매 배지/API 0, 개인 응답 1회, 읽기 이력 없는 구매, 무료보다 구매완료 우선, 잠금·가격 제거, guest 위조·401·503, 정렬·작품 변경·늦은 응답을 검증한다.
- Admin 타입 생성 및 lint·**115개 테스트**·build 통과.
- SSR HTTP **8 passed**. 실제 Node adapter의 공개 목록·60초 공유 캐시, 쿠키/구매완료 비노출과 개인 API 미호출을 확인한다.

브라우저는 실행하지 않았다. 사용자 계정의 실제 구매 배지와 모바일 표시는 사용자 검증 대상이다.

## 공개 구매 계약 정리 (2026-11-11, Q3 FE)

BE [PR #149](https://github.com/Sy3058/d-web/pull/149)에서 공개 `EpisodeSummary.is_purchased`를 제거한 뒤, 최신 main 기준의 `fe/fix/m3-purchase-contract`에서 수기 타입과 episode fixture 두 곳, SSR HTTP 검증의 API fixture를 함께 정리했다. `frontend/` 전체에 해당 필드의 잔여 참조가 없다.

구매 상태는 기존 `WorkExperience`가 작품당 한 번 조회한 no-store `purchased_episode_ids`로만 표시한다. 로컬 읽기 이력은 구매 근거가 아니며, 공개 SSR의 캐시와 최초 열람 비변경 계약도 유지한다. 제품 동작·API 요청·가격 정책은 바꾸지 않았다.

관련 EpisodeRow·WorkExperience 집중 테스트 **19 passed**, 전체 Frontend lint·Astro check·**241개 테스트**·build 및 SSR HTTP **9 passed**를 확인했다. 기존 미사용 import hint와 Sentry·Astro transitions source map 경고는 유지된다. SSR HTTP는 샌드박스 로컬 서버 실행 실패 뒤 허용된 환경에서 통과했으며 브라우저는 실행하지 않았다. [M3 Q3](../../../milestones/M3_foundation.md#m3-quality-followups)의 FE 소비 계약 정리 범위이며 Q2 Admin 입력 검증은 독립 작업이다.
