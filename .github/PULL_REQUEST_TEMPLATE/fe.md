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
- [ ] 미결제 유저에게 이미지 URL 미노출 (Signed URL만)
- [ ] `.astro`에서 `SECRET_*` 환경변수 미접근

## ✅ 구현 체크

- [ ] fetch에 `credentials: 'include'` 포함
- [ ] React 섬 `client:*` 지시어 적절 (load / idle / visible)
- [ ] SSR 페이지 `export const prerender = false` 명시
- [ ] 폼 검증 Zod 스키마 적용
- [ ] 콘텐츠 보호 (select-none + contextMenu + dragStart 차단)

## 검증 체크

- [ ] `npm run lint` 통과 (ESLint)
- [ ] `npm run prettier` 통과
- [ ] `npm run build` 통과 (TypeScript 에러 없음)
- [ ] `npm run dev` 실행 후 변경된 화면 직접 확인
- [ ] 모바일 뷰 확인 (Chrome DevTools)

## 📝 문서

> 이번 PR에서 작성/수정한 것만 체크하고 옆에 파일을 적는다.

- [ ] IMPLEMENTATION 작성 - 
- [ ] TROUBLESHOOTING 작성 - 
- [ ] CHANGELOG 작성 - 
- [ ] 마일스톤 업데이트 - 
- [ ] 그 외 문서/설정 수정 - 

## 🚫 구현 범위 (feat PR인 경우)

- [ ] 보류 기능 미포함 (멤버십, 소설 뷰어, 포렌식 워터마크, 충전식 코인)

## 스크린샷 (UI 변경 시)

<!-- before / after -->
