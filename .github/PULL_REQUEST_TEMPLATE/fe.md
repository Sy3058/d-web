## 변경 사항

<!-- 무엇을, 왜 변경했는지 -->

## 타입

- [ ] feat (새 기능)
- [ ] fix (버그 수정)
- [ ] chore (설정/인프라)
- [ ] refactor
- [ ] docs

## 🚨 보안 체크 (Critical)

- [ ] JWT localStorage 저장 없음 (HttpOnly 쿠키만)
- [ ] 결제 금액 클라이언트에서 조작 불가
- [ ] 미구매 유저에게 유료 구간 이미지 key/URL 미노출 (무료 구간은 서버 경계 절단 후 서명)
- [ ] `PUBLIC_`이 아닌 환경변수가 클라이언트 bundle/HTML에 노출되지 않음

## ✅ 구현 체크

- [ ] fetch에 `credentials: 'include'` 포함
- [ ] React 섬 `client:*` 지시어 적절 (load / idle / visible)
- [ ] SSR 페이지 `export const prerender = false` 명시
- [ ] 클라이언트 검증과 서버 오류 표시 확인
- [ ] 콘텐츠 보호 (select-none + contextMenu + dragStart 차단)

## 검증 체크

- [ ] `pnpm --filter frontend lint` 통과 (Astro/TS/TSX ESLint)
- [ ] `pnpm --filter frontend astro check` 통과 (Astro/TypeScript 진단)
- [ ] `pnpm --filter frontend test` 통과 (Vitest)
- [ ] `pnpm --filter frontend build` 통과 (Astro 빌드 · 빌드타임 에러 없음)
- [ ] 사용자 브라우저 확인 결과 기록 (변경 화면, 모바일 view)

## 📝 문서

> 이번 PR에서 작성/수정한 것만 체크하고 옆에 파일을 적는다.

- [ ] IMPLEMENTATION 작성 - 
- [ ] TROUBLESHOOTING 작성 - 
- [ ] 마일스톤 업데이트 - 
- [ ] 그 외 문서/설정 수정 - 

## 🚫 구현 범위 (feat PR인 경우)

- [ ] 보류 기능 미포함 (멤버십, 소설 뷰어, 포렌식 워터마크, 충전식 코인)

## 스크린샷 (UI 변경 시)

<!-- before / after -->
