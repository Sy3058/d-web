# Admin 코드 리뷰 체크리스트

`$fable-review`로 Admin 변경을 검증할 때 사용.

**리뷰 원칙·코멘트 규약·응답 방법은 [`GUIDE_REVIEW.md`](./GUIDE_REVIEW.md) 참조** (함께 첨부할 것).

사용법: Admin 변경 완료 후 커밋 전에 현재 diff와 구현 문서에 이 체크리스트를 함께 적용한다.

---

## 검토 범위

routes/, components/, hooks/, lib/ 변경사항 (Vite React SPA 관리자)

---

## 🚨 Critical - 머지 금지

- [ ] JWT를 `localStorage`/`sessionStorage` 저장 - **HttpOnly 쿠키만**
- [ ] 클라이언트에서만 권한 확인 (UI 표시/숨김) - **백엔드 API에서 검증**
- [ ] 이미지 업로드 후 클라이언트 URL을 그대로 DB 저장 - 백엔드 검증 필수
- [ ] TOTP 코드/시크릿을 영속 클라이언트 저장소에 저장. 초기 등록의 일회성 `otpauth_uri`만 메모리 query에 두고 confirm·logout 때 즉시 폐기
- [ ] API 에러를 무시하거나 사용자 알림 없이 진행
- [ ] 환불/삭제/공개 버튼이 즉시 확정 동작 - 백엔드 응답 대기 필수

---

## ⚠️ Major - 수정 필요

- [ ] **라우트 가드**: `beforeLoad`에서 `fetchQuery(meQueryOptions)`로 서버 세션을 다시 확인하고 `role === 'owner'` 검증. 실패·강등 시 query cache를 비우고 `/login`으로 이동
- [ ] **2FA**: 이메일/비번 입력 → TOTP 화면 → 코드 검증 → 토큰 발급 순서
- [ ] **모든 fetch**: `credentials: 'include'` 옵션
- [ ] **TanStack Query**: 데이터별 신선도 계약을 명시. 인증 가드는 `staleTime: 0`; 변경 후에는 응답으로 `setQueryData`하거나 관련 query를 invalidate
- [ ] **낙관적 업데이트**: 적용했다면 실패 시 rollback하고 서버 응답과 재동기화
- [ ] **폼**: 클라이언트 검증은 UX 보조로 두고 백엔드 검증 오류를 필드 또는 공통 오류로 표시
- [ ] **이미지 업로드**: draft 생성 후 백엔드 multipart 단건 업로드·변환 경로 사용. Admin에서 R2 presigned PUT 직접 업로드 금지
- [ ] **버튼 활성화**: 백엔드 상태 확인 후 (refundable, deletable 등)

---

## 💡 Minor - 권장

- 에러 알림: `ErrorAlert` 컴포넌트 일관 사용
- Destructive 액션: 확인 모달 필수 (환불, 삭제)
- 캡슐화: 권한 분기는 `ProtectedLayout` 안에서

---

## 리뷰 출력 포맷

```
## 🚨 Critical
- 파일:line - 문제 설명 - 수정 방향

## ⚠️ Major
- 파일:line - 문제 설명

## 💡 Minor
- 파일:line - 개선 제안

## ✅ 통과
- 확인 항목 요약 (1-2줄)
```

---

## 우선순위

1. **🚨 Critical**: 보안/데이터 무결성 위반 → **머지 금지**
2. **⚠️ Major**: 동작은 하나 버그/유지보수 악화 → **수정 필요**
3. **💡 Minor**: 개선 제안 → **머지 가능**
4. **✅ 통과**: 확인했으나 이상 없음
