# 인증 도메인 모델 + 마이그레이션 (M1 그룹 A)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 A |
| 작성 시점 | M1 A1 (2026-06-01) |
| 상태 | 구현 완료, 로컬 DB 검증 완료 |
| 관련 문서 | [DB_SCHEMA.md](../../../DB_SCHEMA.md) §1, [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) |

이 문서는 M1 그룹 A에서 구현한 계정/인증 도메인 SQLModel 모델과 Alembic 마이그레이션을 다룬다. `DB_SCHEMA.md §1`을 코드로 옮긴 것이며, 보안 배경은 `SECURITY_AUTH_DECISIONS.md` 참조.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/user.py` | `User`, `OAuthAccount`, `RefreshToken`, `EmailVerification` (`table=True`) + 응답 전용 `UserRead` |
| `backend/src/models/__init__.py` | 모델 일괄 import 로 `SQLModel.metadata` 등록 |
| `backend/migrations/env.py` | `import models` 로 메타데이터 자동 등록 (autogenerate 인식용) |
| `backend/migrations/versions/20260531_1431_auth_domain.py` | 4개 테이블 + 인덱스 생성 마이그레이션 (rev `5dc1f89ada58`) |

---

## 2. 테이블 구조

`DB_SCHEMA.md §1`을 그대로 따른다. 핵심만:

- **공통**: PK는 전 테이블 `UUID` + `gen_random_uuid()` 서버 기본값 (DB_SCHEMA 설계 원칙). 시각은 전부 `TIMESTAMPTZ`.
- **`users`**: `email` UNIQUE NOT NULL, `hashed_password` **nullable**(소셜 전용 가입은 NULL), `profile_image`, `is_admin`/`is_email_verified` 기본 false, soft delete용 `deleted_at`.
- **`oauth_accounts`**: `UNIQUE(provider, provider_id)`, `user_id` FK CASCADE.
- **`refresh_tokens`**: `token_hash`(원문 저장 금지), `expires_at`, `revoked_at`(회전/재사용 탐지용).
- **`email_verifications`**: `token`(저장값은 해시), `expires_at`(발급+1시간), `used_at`(1회용).

### 인덱스
- `idx_users_deleted_at` - `WHERE deleted_at IS NULL` partial. soft delete 필터링 최적화.
- `ix_users_email` - `email` UNIQUE.
- `idx_refresh_tokens_user_id` - `user_id`. **회전/재사용 탐지 시 유저 세션 전체 revoke(M1 C4) 쿼리 최적화.** Postgres는 FK에 인덱스를 자동 생성하지 않으므로 명시 (코드 리뷰 지적 반영, DB_SCHEMA §6에도 추가).

---

## 3. 구현 결정

### 3.1 `table=True` 모델과 `UserRead` 분리
SQLModel `table=True` 모델은 DB 테이블이자 내부 타입이라 그대로 응답에 쓰면 `hashed_password` 등이 노출된다. 외부 응답은 민감 필드를 뺀 `UserRead`로만 직렬화한다 (M1 C5 `/auth/me`).

### 3.2 sa_column 헬퍼로 컨벤션 통일
`_pk_column()` / `_fk_user_column()` / `_created_at_column()` 헬퍼로 UUID PK·FK·타임스탬프 정의를 한 곳에 모았다. 후속 도메인 모델(M2~)에서 재사용.

### 3.3 서버 사이드 기본값
`gen_random_uuid()`, `now()`, `false`를 모두 `server_default`로 둬서 DB가 채운다. 앱 코드가 값을 빠뜨려도 일관성 유지.

---

## 4. 검증

로컬 Postgres(`compose.yml`)로 확인:

- `uv run alembic upgrade head` 로 4개 테이블 + 인덱스 생성
- `\d users` 출력이 DB_SCHEMA §1과 일치 (UUID PK, nullable, partial index 포함)
- `alembic downgrade base` 와 `upgrade head` 왕복 정상
- `alembic check` 가 "No new upgrade operations detected" (모델 과 마이그레이션 동기화)
- `uv run ruff check` 통과, `uv run pytest` 통과

---

## 5. 다음 단계 (그룹 B~)

이 모델 위에 그룹 B(해싱·JWT·쿠키), C(이메일/비번 엔드포인트), D(구글 OAuth), E(이메일 인증)가 얹힌다. 보안 구현 세부는 `SECURITY_AUTH_DECISIONS.md`, 작업 단위는 `M1_foundation.md` 참조.
