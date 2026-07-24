# Backend - FastAPI REST API 서버

## 스택 결정 (왜?)

| 항목 | 선택 | 이유 |
|------|------|------|
| 프레임워크 | FastAPI | 비동기, 자동 API 문서, Pydantic 통합, AI 확장 용이 |
| ORM | SQLModel | DB 모델 = API 응답 타입 (코드 중복 없음) |
| DB | PostgreSQL | ACID 보장, VPS 직접 운영 |
| 환경변수 | Pydantic Settings | .env 자동 로딩 + 타입 검증 |
| 테스트 | pytest | 비동기 지원, fixture |
| 로깅 | structlog | JSON 구조화 로그 |

---

## 프로젝트 구조

```
backend/src/
├── main.py                  # FastAPI 앱 + Lifespan
├── config.py                # Pydantic Settings
├── routers/                 # 도메인별 라우터
│   ├── auth.py              # 로그인, 소셜, 2FA, 토큰 갱신
│   ├── episodes.py          # 목록, 상세, 업로드
│   ├── payment.py           # 결제 검증, 취소
│   ├── community.py         # 댓글, 신고, 환불
│   └── admin.py             # 관리자 전용
├── models/                  # SQLModel (DB + 응답 타입 겸용)
│   ├── user.py
│   ├── episode.py
│   ├── payment.py
│   └── community.py
├── services/                # 비즈니스 로직
│   ├── auth_service.py      # JWT, TOTP, OAuth
│   ├── episode_service.py
│   ├── payment_service.py   # 포트원 연동
│   ├── r2_service.py        # Signed URL
│   └── community_service.py
├── lib/
│   ├── db.py                # AsyncSession, get_session
│   ├── auth.py              # JWT 검증, 권한 확인
│   ├── exceptions.py
│   └── pagination.py
├── migrations/              # Alembic
└── tests/                   # pytest
```

---

## 핵심 패턴

### 레이어드 아키텍처
- **router**: 요청 검증, HTTP 응답 포장
- **service**: 비즈니스 로직, 트랜잭션 경계
- **model**: DB CRUD만

### 결제 검증
- 금액은 반드시 DB에서 계산 (클라이언트 값 무시)
- 포트원 검증 완료 → DB 저장 순서 엄수
- 결제 관련 다중 INSERT는 반드시 트랜잭션

### Signed URL (R2)
- **서버가 이미 열람 가능하다고 확정한 분량에만 발급.** 클라이언트가 보낸 키를 그대로 서명하지 않는다
  - 무료 구간(M2): `content`를 paywall 경계에서 **서버가 절단한 뒤** 남은 image 키만 서명 (인증 불요 - M2 결정 1)
  - 유료 구간(M3): 구매 검증 통과 후에만
- 매 요청마다 생성 (캐시 안 함 - 응답은 `Cache-Control: no-store`)
- 무료 공개분 외 이미지 키는 클라이언트에 절대 노출 금지
- 편집본(`episodes.draft`)·미공개 원고는 독자 DTO에 절대 포함 금지 - owner 전용 `AdminEpisodeRead`만 (#86)

### N+1 방지
- 관계 데이터 필요 시 `selectinload` 명시 (lazy loading 기본값 믿지 말 것)

### JWT
- 액세스 토큰 15분, 리프레시 토큰 7일
- 리프레시는 HttpOnly + Secure + SameSite=Strict 쿠키
- 2FA: 이메일/비번 검증 → TOTP 코드 검증 → JWT 발급

### 에러 코드
- 401: 인증 필요 / 403: 권한 없음(구매 필요) / 400: 검증 실패

---

## 절대 금지

❌ 클라이언트 결제 금액 신뢰
❌ JWT localStorage 저장
❌ 권한 확인 없이 리소스 반환
❌ Signed URL 클라이언트 생성
❌ Raw SQL 문자열 직접 조합
❌ 비동기 함수에서 동기 블로킹 호출
❌ 트랜잭션 없이 다중 INSERT
❌ 환경변수 하드코딩
❌ 개인정보 plaintext 로깅
❌ TOTP 시크릿 클라이언트 노출

---

## 코드 리뷰

커밋 전 Opus 4.8 검증: `@docs/reviews/CODE_REVIEW_BE.md` (+ 원칙은 `@docs/reviews/GUIDE_REVIEW.md`)