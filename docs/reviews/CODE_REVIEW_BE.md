# Backend 코드 리뷰 체크리스트

Opus 4.8로 검증할 때 사용.

**리뷰 원칙·코멘트 규약·응답 방법은 [`GUIDE_REVIEW.md`](./GUIDE_REVIEW.md) 참조** (함께 첨부할 것).

사용법: `be/feat/`, `be/fix/` 작업 완료 후 커밋 전에 이 문서를 Opus 리뷰 프롬프트에 첨부.

---

## 검토 범위

routers/, services/, models/, lib/, config.py, main.py 변경사항

---

## 🚨 Critical - 머지 금지

다음 위반 발견 시 즉시 STOP:

- [ ] 클라이언트 결제 금액 신뢰 - 금액은 **DB에서만 계산**
- [ ] JWT를 응답 본문 평문으로 반환 - **HttpOnly 쿠키만**
- [ ] 권한 검증 없이 리소스 반환 - `Depends(get_current_user)`, `Depends(require_admin)` 필수
- [ ] 미결제 유저에게 Signed URL, r2_key, 이미지 URL 노출
- [ ] 클라이언트에서 Signed URL 생성 - 백엔드만 생성
- [ ] 원시 SQL 조합 (`text("SELECT ...")`) - SQLModel ORM 사용
- [ ] 비동기 함수에서 `requests`, `time.sleep`, 동기 DB 호출 등 블로킹
- [ ] 트랜잭션 없이 다중 INSERT (결제 관련)
- [ ] 환경변수 하드코딩
- [ ] 개인정보 평문 로깅 (이메일, 카드, TOTP 시크릿)
- [ ] CORS `allow_origins=["*"]`
- [ ] TOTP 시크릿을 API 응답/로그에 포함

---

## ⚠️ Major - 수정 필요

- [ ] **결제 흐름**: 포트원 API 검증 → 금액 확인 → DB insert 순서. 검증 실패 시 DB 변경 없음
- [ ] **Webhook**: `PORTONE_WEBHOOK_SECRET` 검증, 타임스탬프 확인
- [ ] **N+1**: 관계 데이터 조회 시 `selectinload` 명시 (lazy loading 금지)
- [ ] **JWT**: 액세스 15분 / 리프레시 7일 일관성
- [ ] **리프레시 쿠키**: `HttpOnly=True, Secure=True, SameSite='Strict'`
- [ ] **에러 코드**: 401(인증) / 403(권한/구매) / 400(검증) 구분
- [ ] **config.py 조립**: CORS_ORIGINS, KAKAO_REDIRECT_URI, GOOGLE_REDIRECT_URI는 baseURL에서 조립, env에 박지 말 것
- [ ] **레이어 분리**: router는 검증/응답 포장만, service는 비즈니스 로직 + 트랜잭션 경계, model은 DB CRUD만

---

## 💡 Minor - 권장

- 타입 힌트: 모든 함수 반환 타입 명시
- 의존성 주입: DB 세션, 현재 유저는 `Depends()`로
- 예외: `lib/exceptions.py`의 커스텀 클래스 사용
- 로깅: 구조화 로깅, PII 제외

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
