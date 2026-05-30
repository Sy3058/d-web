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
- [ ] 권한 확인 클라이언트에서만 하지 않음 (백엔드 API 검증 병행)
- [ ] TOTP 코드/시크릿 메모리 외 저장 없음
- [ ] 환불/삭제 버튼 즉시 확정 동작 없음 (백엔드 응답 대기)

## ✅ 구현 체크

- [ ] 라우트 가드 (`beforeLoad` 토큰 검증)
- [ ] 모든 fetch `credentials: 'include'`
- [ ] TanStack Query: 변경 후 `invalidateQueries()` 호출
- [ ] API 에러 사용자에게 알림 (try-catch + ErrorAlert)
- [ ] Destructive 액션 확인 모달 포함

## 검증 체크

- [ ] `npm run lint` 통과 (ESLint)
- [ ] `npm run build` 통과 (tsc + vite build)
- [ ] `npm run dev` 실행 후 변경된 화면 직접 확인
- [ ] 로그인 → 해당 기능 플로우 직접 확인

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
