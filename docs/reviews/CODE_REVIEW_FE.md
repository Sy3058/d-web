# Frontend 코드 리뷰 체크리스트

Opus 4.7로 검증할 때 사용.

**리뷰 원칙·코멘트 규약·응답 방법은 [`GUIDE_REVIEW.md`](./GUIDE_REVIEW.md) 참조** (함께 첨부할 것).

사용법: `fe/feat/`, `fe/fix/` 작업 완료 후 커밋 전에 이 문서를 Opus 리뷰 프롬프트에 첨부.

---

## 검토 범위

pages/, components/, layouts/, lib/ 변경사항 (Astro 독자용)

---

## 🚨 Critical - 머지 금지

- [ ] JWT를 `localStorage`/`sessionStorage` 저장 - **HttpOnly 쿠키만**
- [ ] 클라이언트에서 결제 금액 임의 조정 가능 - 포트원 전송 전 백엔드 재검증 필수
- [ ] 미결제 상태에서 에피소드 이미지 URL 응답/렌더링 - **Signed URL만**
- [ ] `.astro` 파일에서 `import.meta.env.SECRET_*` 접근 - 빌드 시 HTML에 인라인됨
- [ ] OAuth state 검증 없이 콜백 처리
- [ ] `xmlHttpRequest` 사용 - `fetch` API 사용

---

## ⚠️ Major - 수정 필요

- [ ] **fetch에 `credentials: 'include'`** - HttpOnly 쿠키 전달
- [ ] **React 섬 분리**: 정말 필요한 부분만 `.tsx`, 그 외 `.astro` 정적 렌더링
- [ ] **`client:*` 지시어**:
  - `client:load`: 로그인, 결제, OAuth (페이지 로드 직후)
  - `client:idle`: 댓글, 하트 (유휴 시간)
  - `client:visible`: 하단 위젯 (뷰포트 진입)
- [ ] **SSR 페이지**: `export const prerender = false` 명시
- [ ] **폼 검증**: react-hook-form + Zod
- [ ] **뷰어 진행도**: % 기반 아닌 **페이지 번호**
- [ ] **콘텐츠 보호**: `select-none` + `onContextMenu 차단` + `onDragStart 차단` 모두 포함
- [ ] **PUBLIC_* 확인**: 환경변수 번들에 포함 여부

---

## 💡 Minor - 권장

- 데이터 페칭: SSG 우선, 로그인 필수는 SSR, 실시간은 React 섬
- 에러 UI: 사용자 친화적 메시지 (기술 용어 X)
- 이미지 lazy loading: 뷰어 외 모든 곳

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
