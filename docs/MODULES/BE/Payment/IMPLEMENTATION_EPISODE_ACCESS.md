# M3 F1 중앙 회차 권한 판정

## 범위

F1은 내부 `resolve_episode_access`를 제공한다. content API, viewer bootstrap, 개인화 progress, 첫 전문 발급 CAS와 결제 UI 연결은 후속 작업이다. F 그룹 전체 완료를 뜻하지 않는다.

## 판정 계약

- 작품 또는 회차가 없거나 soft delete 상태이면 `unavailable`이다.
- 현재 배포 결제 환경의 활성 구매자는 작품·회차가 일반 비공개가 되어도 `full`이다. purchase와 연결 order의 환경을 함께 확인한다. 다른 사용자·환경 또는 active 이외 상태는 구매 권한이 아니다.
- 공개 작품의 공개 회차는 문서의 paywall 뒤 유의미 콘텐츠 유무로 `full` 또는 `preview`를 결정한다. 목록용 파생 `is_free`는 권한 근거로 사용하지 않는다.
- 신규 판매 중지는 기존 열람을 막지 않는다는 설계 계약을 유지한다. 현재 모델에 `sales_paused_at` 필드는 없어 F1에서 새 필드나 동작을 만들지 않는다. 긴급 법적 차단 필드·SOP는 M7에서 결정한다.
- 삭제된 사용자의 구매는 권한으로 인정하지 않는다. 문서 구조 또는 이미지 매니페스트가 유효하지 않으면 공개 회차는 `preview`, 비공개 회차는 `unavailable`로 닫는다. 잘못된 저장 문서를 무료 전문으로 추측하지 않는다.
- 판정 결과에 원고·이미지 키·개인 메타데이터를 담지 않는다. 구매 권한으로 full인 경우에만 내부 purchase ID를 제공한다.

## 동시성과 후속 통합

이 함수는 조회 시점의 snapshot을 반환하고 열람 이력을 쓰거나 트랜잭션을 commit하지 않는다. `full` 결과만으로 이후 환불 경합에서 전문 발급을 허용할 수 없다. 후속 content 서비스는 안전한 문서 투영·허용 키 presign 이후 응답 직전에 구매 active 상태를 재확인하고 첫 발급 CAS로 환불 승인과 단일 승자를 결정해야 한다.

공개 API와 schema는 변경하지 않는다. 기존 무료 구간 content 경로는 그대로 유지되며 F1만으로 유료 전문이 외부에 제공되지 않는다.

F3 통합 보강(2026-11-08)에서는 `episode_access_columns`와 순수 `evaluate_episode_access`로 조회 입력과 정책을 분리했다. 기존 `load_episode_access`·`resolve_episode_access` 계약을 유지하면서 bootstrap도 메타·네비·권한을 같은 SELECT snapshot에서 판정한다. 공개 전환 뒤 새 권한으로 이전 비공개 메타를 승인하지 않으며 상세 검증은 [viewer-bootstrap 구현 문서](./IMPLEMENTATION_VIEWER_BOOTSTRAP.md)를 따른다.

## 검증

2026-11-08 최종 검증:

- `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run ruff format --check .`: 105 files 통과.
- `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run ruff check .`: 통과.
- `UV_CACHE_DIR=/tmp/d-web-uv-cache uv run pytest`: **974 passed**, 67.76초, 경고 없음. 신규 권한 판정 29건이 포함된다.
- `git diff --check`와 신규 파일 U+2014 금지 검사 통과.

신규 테스트는 공개 문서·paywall·오염된 파생 is_free, 3종 비공개 조합, 전체 PurchaseStatus, 환경·사용자·회차 격리, soft delete·탈퇴, malformed 문서/매니페스트, stale ORM 상태에서 환불 대기·비공개 전환을 검증한다. 주문 status가 변경되어도 active 구매 자체의 계약을 유지하는 경우도 확인한다.

초기 전체 실행은 974개 통과했으나 테스트의 deprecated `session.execute` 호출에서 경고 5건이 발생했다. `session.exec`로 수정한 뒤 위 전체 gate를 다시 통과했다. sandbox focused 실행은 DB 연결 대기로 중단했고 승인된 외부 실행에서 PID별 격리 테스트 DB로 검증했다. 실제 결제 write와 브라우저 확인은 수행하지 않았다. Frontend/Admin과 API schema 변경은 없어 해당 gate·타입 재생성은 대상이 아니다.
