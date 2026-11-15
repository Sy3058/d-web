# U2 관리자 공통 UI 통일

## 범위

사용자가 보존하도록 요청한 관리자 로그아웃 빨간 글씨 변경을 전반적인 관리자 UI 전달 단위에 포함한다. 최신 main 기반 admin/feat/ui-consistency 별도 작업 공간에서 진행했다. 전체 관리자 화면 재설계나 원고·폼·업로드 동작 변경은 포함하지 않는다.

## 변경

- CSS 공통 컨트롤은 최소 44px, 둥근 8px, 회색 hover, focus-visible, disabled 상태를 제공한다. 주요 탐색·대시보드·기존 돌아가기/생성 버튼·커미션 상태와 재배열 컨트롤에 적용한다.
- 로그아웃과 기존 실제 삭제 항목은 빨간색으로 구분한다. 태그 선택 해제를 영구 삭제처럼 바꾸지 않는다.
- 수동 ActionsMenu를 기존 독자 메뉴와 같은 Base UI Menu 1.9.0으로 바꾼다. 포털 배치·방향키 탐색·Escape 닫기·트리거 포커스 복귀·바깥 클릭 처리를 사용한다.
- 작품·회차·커미션의 기존 콜백과 삭제/비공개 직렬화 잠금은 유지한다. Menu.Item의 aria-disabled 의미에 맞춰 회귀의 접근성 질의를 갱신하고 비활성 클릭 시 추가 요청·콜백이 없음을 확인한다.
- 회차 표의 순서·메뉴 열은 44px 컨트롤과 좌우 여백을 수용하도록 넓히고 제목은 말줄임을 유지한다. 가로 스크롤 경계와 고정 메타 열은 유지한다.
- Admin importer에 이미 workspace가 사용하는 @base-ui/react 1.9.0을 추가한다. 무관한 전이 의존성 변경은 제외했으며 pnpm lock의 추가는 importer뿐이다. 설치는 기존 로컬 캐시와 frozen/ignore-scripts로 확인했다.

## 검증

- Admin lint·22 files/123 tests·production build 통과.
- 메뉴 4개 회귀는 키보드 이동·포털·Escape/포커스 복원·바깥 클릭·콜백 1회·잠금 항목 콜백 0회를 확인한다. 기존 회차 삭제 직렬화 테스트는 잠긴 항목을 눌러도 DELETE가 추가되지 않음을 유지한다.
- git diff --check 통과. 별도 작업 공간에 처음 부족했던 shared/zod 링크는 동일 lock의 offline frozen 설치로 보완한 뒤 전체 검증했다. 수집 실패를 성공으로 처리하지 않았다.
- 실제 브라우저·모바일의 표 배치·포인터 조작은 사용자 확인 대상이다. Backend/Frontend 동작은 이 브랜치에서 수정하지 않았다.

## 근거

- [UI 결정](../../../DECISIONS.md)
- [M3 후속 합의](../../../milestones/M3_foundation.md)
- [shadcn Dropdown Menu](https://ui.shadcn.com/docs/components/base/dropdown-menu)
- [Base UI Menu](https://base-ui.com/react/components/menu)
