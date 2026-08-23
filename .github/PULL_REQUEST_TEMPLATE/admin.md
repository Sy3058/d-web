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
- [ ] TOTP 등록 URI는 메모리에서만 보관하고 confirm/logout 시 폐기
- [ ] 환불/삭제 버튼 즉시 확정 동작 없음 (백엔드 응답 대기)

## ✅ 구현 체크

- [ ] 라우트 가드 (`beforeLoad`에서 서버 세션 + owner role 검증)
- [ ] 모든 fetch `credentials: 'include'`
- [ ] TanStack Query: 응답으로 cache 갱신 또는 관련 query invalidate
- [ ] API 에러 사용자에게 알림 (try-catch + ErrorAlert)
- [ ] Destructive 액션 확인 모달 포함

## 검증 체크

- [ ] `pnpm --filter admin lint` 통과
- [ ] `pnpm --filter admin test` 통과
- [ ] `pnpm --filter admin build` 통과
- [ ] 사용자 브라우저 확인 결과 기록 (변경 화면, 로그인·기능 flow)

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
