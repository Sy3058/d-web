# M3 F3 BE 뷰어 초기 메타 API

## 범위

`GET /works/{work_id}/episodes/{public_id}/viewer-bootstrap`이 중앙 권한 판정에 따라 뷰어 진입에 필요한 최소 메타를 반환한다. 공개 카탈로그에서 찾을 수 없는 일반 비공개 구매 회차를 해석하기 위한 API다. BE API와 테스트, OpenAPI 생성 타입까지만 완료하며 FE 진입 셸·세션 복구·Viewer 연결은 BE 머지 뒤 별도 `fe/` 브랜치에서 진행한다. F 그룹 전체 완료를 뜻하지 않는다.

## 인증과 반환 범위

`get_optional_user`로 확인한 사용자 ID로 중앙 권한 서비스의 조회 열과 정책 평가를 재사용한다. 공개 회차는 익명으로 조회할 수 있고, 작품·회차가 일반 비공개여도 현재 결제 환경의 활성 구매자는 조회할 수 있다. 다른 사용자·회차·환경의 구매나 환불 대기·환불 완료 구매로는 비공개 회차의 메타를 조회할 수 없다. 비구매 비공개와 soft delete는 메타 없이 404다. 작품 UUID와 해당 작품의 회차 public ID를 함께 확인한다.

응답은 `work_id`, `work_title`, `episode_id`, `public_id`, `episode_title`, `episode_subtitle`, `previous_episode`, `next_episode`만 포함한다. 이웃은 `public_id`와 `title`만 담는다. 원고 본문·이미지 키·서명 URL·가격·구매 ID와 구매 상태는 포함하지 않는다. bootstrap은 이미지 서명과 `first_viewed_at` 기록을 수행하지 않으며 실제 전문 발급은 기존 F2 content API가 다시 인가한다.

access 쿠키 없음·무효·만료는 익명으로 처리한다. 이 API에서 refresh나 쿠키 삭제를 하지 않으므로 FE는 `useEffect`에서 세션 복구를 마친 뒤 호출해야 한다. 위조 쿠키가 비공개 구매 메타를 열거나 쿠키를 변경하지 않는 것을 검증했다. 기존 중앙 resolver의 문서 검증도 유지해 손상 문서가 비공개 구매 메타를 열지 못한다.

성공 200, 존재를 숨기는 404, 경로 검증 422에 `Cache-Control: no-store`를 적용한다. UUID와 public ID 범위 10,000,000~99,999,999를 검증한다. bootstrap 전용 child router의 `APIRoute`가 기본 validation 응답에 헤더를 추가하므로 기존 공개 카탈로그 라우트는 바뀌지 않는다.

## 네비게이션

작품이 공개 상태일 때만 공개·미삭제 회차에서 앞뒤 한 건을 조회한다. 현재 회차가 비공개여도 카탈로그의 정렬 키 `sort_order`, `created_at`, `id`를 기준으로 위치를 찾는다. 작품이 비공개이면 두 이웃 모두 null이다. 다른 비공개 회차나 삭제된 회차의 제목·식별자는 내보내지 않는다.

현재 회차 메타와 양쪽 이웃의 `LIMIT 1` 조회를 `LEFT JOIN LATERAL`로 묶고 공개 여부·문서·활성 구매 등 중앙 권한 서비스의 조회 열도 한 SELECT에서 읽는다. 조회한 같은 row를 중앙 정책으로 평가하므로 인증 조회를 제외하고 SELECT는 한 번이다. 관계 lazy loading, 외부 I/O, commit은 없다. bootstrap 결과는 전문 권한 증명으로 사용하지 않는다.

이렇게 현재 위치와 이웃을 동일한 statement snapshot에 고정한다. 이전 구현은 현재 위치를 먼저 읽은 뒤 이웃을 따로 조회해 관리자 재정렬이 끼어들면 현재 회차를 자기 자신의 이전·다음 회차로 반환할 수 있었다. [PostgreSQL Read Committed](https://www.postgresql.org/docs/16/transaction-iso.html#XACT-READ-COMMITTED)의 SELECT별 snapshot과 [SQLAlchemy LATERAL correlation](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html#lateral-correlation)을 확인해 조회를 합쳤다. 자기 자신만 제외하는 필터나 행 잠금으로 우회하지 않는다.

후속 리뷰에서는 메타 조회와 별도 권한 SELECT 사이에 제목·부제를 바꾸며 공개하면 최초 비공개 메타가 익명 응답으로 나가는 P1을 재현했다. 중앙 권한 서비스에서 조회 열과 순수 정책 평가를 분리하고 기존 content 경로와 bootstrap이 함께 사용하도록 했다. 메타·네비·공개 여부·구매·문서가 모두 같은 snapshot에 속하므로 이후 공개 전환이나 구매가 이전의 비공개 메타를 승인하지 않는다. content의 문서 투영·서명·첫 발급 최종 CAS는 기존 경로를 유지한다.

## 검증

2026-11-08 검증 결과:

- 신규 `tests/test_viewer_bootstrap.py` **33개 통과**. 공개 메타 allowlist, 서명·첫 발급 부작용 없음, 작품·회차 비공개 조합, 구매 소유자·회차·환경·상태, 삭제, 작품 경로 불일치·누락, 무효 경로·위조 쿠키, 손상 문서, 정렬 tie와 공개 이웃·경계 및 재정렬·공개 전환·구매 경합을 검증했다.
- Backend `uv run ruff format --check .` **108 files**, `uv run ruff check .` 통과. `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run pytest` **1,032 passed**, 68.18초.
- `pnpm --filter admin generate:types`로 생성 타입을 갱신하고 Admin lint, **115 tests**, build 통과.
- 초기 28개·Backend 전체 1,027개 통과 뒤 리뷰에서 재정렬 P2를 추가 재현했다. `[A, B, C]`의 B 조회 중 독립 DB 세션에서 실제 재정렬 서비스를 호출해 `[B, C, A]`와 `[C, A, B]`를 각각 commit하는 회귀 2개를 추가했다. 자기 자신을 제외하는 데 그치지 않고 양쪽 이웃이 최초 snapshot의 A·C와 정확히 일치함을 단언한다. 조회 수정 후 위 Backend 전체 gate를 다시 통과했다.
- 이후 공개 전환 P1을 독립 DB 세션의 실제 `update_episode`로 재현했다. 회차·작품 공개 전환 2개와 조회 뒤 구매 생성 1개를 추가해 최초 비공개 요청은 메타 없는 404, 후속 요청은 새 공개 메타·구매 권한으로 200임을 검증한다. 재정렬 회귀도 실제 bootstrap SELECT가 끝난 직후 독립 편집 commit을 넣도록 연결했으며 양쪽 이웃의 정확한 단언은 유지했다. 기존 권한·본문·발급 테스트를 포함한 집중 검증은 **118 passed**다.
- Admin 검증은 BE·FE 분리 전에 실행한 결과다. 경합 수정은 service·테스트에 한정되고 DTO·API 계약·생성 타입은 바뀌지 않아 Admin gate를 반복하지 않았다. 보존한 FE 변경은 이번 diff에 포함하지 않는다.

첫 집중 테스트는 PostgreSQL 미실행으로 연결 실패했다. 서비스 상태를 확인한 뒤 기존 볼륨을 유지하고 `docker compose up -d postgres`로 시작하여 위 검증을 완료했다. DB 모델·마이그레이션·dependency 변경, 실제 PortOne 호출과 사용자 브라우저 검증은 없다.

## FE 인계

공개 catalog SSR은 유지하고, 공개 조회에서 회차를 찾지 못하면 메타 없는 client-only 셸에서 세션을 복구한 뒤 이 API를 호출한다. bootstrap 성공 뒤 기존 Viewer에 UUID와 허용된 네비를 전달하고, 본문은 content API가 발급한다. 이 연결과 실제 구매자의 비공개 direct viewer 확인은 FE 작업의 완료조건이다. 이번 BE 완료만으로 비공개 구매의 브라우저 진입이 완성되지는 않는다.
