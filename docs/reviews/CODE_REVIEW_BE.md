# Backend 코드 리뷰 체크리스트

`$fable-review`로 Backend 변경을 검증할 때 사용.

**리뷰 원칙·코멘트 규약·응답 방법은 [`GUIDE_REVIEW.md`](./GUIDE_REVIEW.md) 참조** (함께 첨부할 것).

사용법: Backend 변경 완료 후 커밋 전에 현재 diff와 구현 문서에 이 체크리스트를 함께 적용한다.

---

## 검토 범위

routers/, services/, models/, lib/, config.py, main.py 변경사항

---

## 🚨 Critical - 머지 금지

다음 위반은 머지를 차단한다. 리뷰만 요청받았으면 보고하고, 수정까지 요청받았으면 원인을 검증해 수정과 관련 검증을 계속한다:

- [ ] 클라이언트 결제 금액 신뢰 - 금액은 **DB에서만 계산**
- [ ] JWT를 응답 본문 평문으로 반환 - **HttpOnly 쿠키만**
- [ ] 권한 검증 없이 리소스 반환 - 인증은 `get_current_user`, 관리자 권한은 `require_owner`/`require_role` 등 현재 dependency로 검증
- [ ] 서버 paywall 경계 밖의 유료 이미지 key나 URL을 미구매 사용자에게 노출. 무료 구간은 서버에서 경계를 절단한 뒤 허용된 key만 서명 가능
- [ ] 클라이언트에서 Signed URL 생성 - 백엔드만 생성
- [ ] 사용자 입력을 포함한 원시 SQL 문자열 조합. SQLModel/SQLAlchemy 표현식과 바인딩 사용
- [ ] 비동기 함수에서 `requests`, `time.sleep`, 동기 DB 호출 등 블로킹
- [ ] 트랜잭션 없이 다중 INSERT (결제 관련)
- [ ] 환경변수 하드코딩
- [ ] 개인정보 평문 로깅 (이메일, 카드, TOTP 시크릿)
- [ ] CORS `allow_origins=["*"]`
- [ ] TOTP 시크릿을 로그나 일반 API 응답에 포함. 단, 초기 등록 화면의 일회성 `otpauth_uri`는 owner 비밀번호 검증 뒤 발급하고 메모리에서만 보관

---

## ⚠️ Major - 수정 필요

- [ ] **결제 흐름**: PortOne 단건 조회 → 서버 주문 snapshot 대조 → 권한 생성 순서. 검증 실패 시 권한을 만들지 않는다. 이미 승인된 금액 불일치는 서버 예상 금액을 바꾸지 않고 검증된 provider 총액으로 보상 취소하며, 취소를 확정할 수 없으면 대사·격리 상태를 DB에 보존한다.
- [ ] **Webhook**: `PORTONE_WEBHOOK_SECRET` 검증, 타임스탬프 확인
- [ ] **N+1**: 관계 데이터 조회 시 `selectinload` 명시 (lazy loading 금지)
- [ ] **JWT**: 액세스 15분 / 리프레시 7일 일관성
- [ ] **인증 쿠키**: HttpOnly, path, SameSite, 환경별 Secure 설정이 `src/lib/auth.py`의 발급·삭제 계약과 일치
- [ ] **에러 코드**: 401(인증) / 403(권한·구매) / 409(상태 충돌) / 422(요청 검증) 등을 실패 의미에 맞게 구분
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
