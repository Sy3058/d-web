# Frontend 코드 리뷰 체크리스트

`$fable-review`로 Frontend 변경을 검증할 때 사용.

**리뷰 원칙·코멘트 규약·응답 방법은 [`GUIDE_REVIEW.md`](./GUIDE_REVIEW.md) 참조** (함께 첨부할 것).

사용법: Frontend 변경 완료 후 커밋 전에 현재 diff와 구현 문서에 이 체크리스트를 함께 적용한다.

---

## 검토 범위

pages/, components/, layouts/, lib/ 변경사항 (Astro 독자용)

---

## 🚨 Critical - 머지 금지

- [ ] JWT를 `localStorage`/`sessionStorage` 저장 - **HttpOnly 쿠키만**
- [ ] 클라이언트에서 결제 금액 임의 조정 가능 - 포트원 전송 전 백엔드 재검증 필수
- [ ] 서버가 허용하지 않은 유료 구간 이미지 key나 URL을 응답·렌더링. 무료 구간도 서버가 paywall 경계로 절단해 서명한 URL만 사용
- [ ] `PUBLIC_`이 아닌 환경변수를 클라이언트 번들이나 렌더된 HTML에 노출. `.astro` 확장자만으로 서버 전용이라고 가정 금지
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
- [ ] **폼 검증**: 클라이언트 검증만 신뢰하지 않고 서버 오류를 사용자에게 표시
- [ ] **뷰어 진행도**: `page_no`는 최상위 블록 index, `block_offset_bp`는 블록 내부 0..10000 상대 위치로 저장
- [ ] **콘텐츠 보호**: `select-none` + `onContextMenu 차단` + `onDragStart 차단` 모두 포함
- [ ] **PUBLIC_* 확인**: 환경변수 번들에 포함 여부

---

## 💡 Minor - 권장

- 데이터 페칭: 쿼리 파라미터·신선도·개인화 요구에 따라 SSG/SSR/React island를 선택. SSR은 `export const prerender = false`
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
