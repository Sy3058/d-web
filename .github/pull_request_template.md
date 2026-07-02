<!--
  기본 PR 템플릿.
  GitHub은 PR 템플릿이 여러 개여도 자동 선택 UI를 주지 않는다(이슈 템플릿과 다른 점).
  그래서 .github/PULL_REQUEST_TEMPLATE/ 안의 be/fe/admin/common 템플릿은
  URL에 ?template= 를 붙여야만 적용된다. 이 기본 파일이 있어야 PR을 열 때 본문이 자동으로 뜬다.
  아래 링크를 누르면 해당 영역 템플릿으로 다시 열린다.
-->

## 영역별 템플릿으로 다시 열기

아래 링크를 누르면 본문이 해당 영역 템플릿으로 바뀝니다 (URL의 `?template=` 이용):

- [백엔드 (be)](?expand=1&template=be.md)
- [프론트 (fe)](?expand=1&template=fe.md)
- [관리자 (admin)](?expand=1&template=admin.md)
- [공통/설정/문서 (common)](?expand=1&template=common.md)

> 영역이 명확하면 위 링크로 바꿔 열고, 이 안내와 아래 공통 체크는 지우세요.

---

## 변경 사항

<!-- 무엇을, 왜 변경했는지 -->

## 타입

- [ ] feat (새 기능)
- [ ] fix (버그 수정)
- [ ] chore (설정/인프라)
- [ ] refactor
- [ ] docs

## 체크

- [ ] 영향 받는 영역 CLAUDE.md 업데이트 확인
- [ ] DECISIONS.md 기록 필요 여부 확인
- [ ] 환경변수 변경 시 `.env.example` 업데이트

## 검증 체크

- [ ] 영향 받는 영역 빌드/테스트 확인 (`pnpm build` / `uvicorn src.main:app` / `pytest`)
