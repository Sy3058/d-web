# RBAC role + TOTP 기반 + 관리자 부트스트랩 (M1.5 그룹 B - B1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1.5](../../../milestones/M1.5_foundation.md) 그룹 B - B1 |
| 작성 시점 | 2026-07-10 (구현은 2026-07-02~03, 브랜치 `be/feat/admin-auth-totp` - 사후 작성) |
| 상태 | 구현 완료·머지. `alembic check` 클린 + `is_admin`→`role` 데이터 이관 실측 확인 |
| 관련 문서 | DECISIONS.md "관리자 권한 분리"·"2FA", M1.5_foundation.md 결정 3·4, [IMPLEMENTATION_ADMIN_2FA_LOGIN.md](./IMPLEMENTATION_ADMIN_2FA_LOGIN.md)(B2/B3 - 이 기반 위 로그인 플로우) |

관리자 인증(그룹 B)의 토대: 권한 모델(`role`)과 TOTP 저장 프리미티브, 최초 owner를 만드는 부트스트랩. `require_owner` 가드·2단계 로그인은 B2/B3 소관.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/user.py` | `RoleEnum`(reader/owner/moderator) + `role` VARCHAR(16) 컬럼(`is_admin` 대체), `totp_secret`(Fernet 암호문, nullable)·`totp_confirmed_at` 컬럼 |
| `backend/migrations/versions/20260701_1709_user_role_rbac_and_totp_columns.py` | `role` 추가 + **`is_admin=true`→`role='owner'` 데이터 이관** 후 `is_admin` drop + TOTP 컬럼 (rev `9a25c6be3759`) |
| `backend/src/lib/totp.py` | Fernet 암복호(`encrypt_secret`/`decrypt_secret`) + pyotp 래퍼(`generate_secret`/`provisioning_uri`/`verify_code`) |
| `backend/src/config.py` + `.env.example` + CI | `TOTP_ENCRYPTION_KEY`(SecretStr, default 금지) |
| `backend/scripts/promote_admin.py` | 기존 이메일 인증 유저 → owner 승격 (`uv run python -m scripts.promote_admin <email>`) |
| 테스트 | TOTP round-trip, role 기본값, 부트스트랩 플로우 |

새 의존성: `pyotp`, `cryptography`(설치 직전 최신 안정 버전 확인).

---

## 2. 주요 결정

### role = VARCHAR(16) + Python StrEnum (3-역할, M1.5는 owner만 빌드)
`is_admin`(boolean)을 `role`(reader 기본/owner/moderator)로 교체. 네이티브 PG enum이 아니라 후속 역할 추가는 앱 enum 값만 - **DB 마이그레이션 0**. moderator는 M4, developer는 product 역할이 아니라 미도입(관측은 외부 도구, 매출 차단은 인프라/자격증명 소유권 - DECISIONS). **authz 진실 소스는 DB `user.role`**(JWT claim 아님): `get_current_user`가 매 요청 User를 로드하므로 추가 쿼리 0 + 강등 즉시 반영.

### TOTP 시크릿 = Fernet 대칭 암호화 at-rest (결정 3)
TOTP는 검증 때마다 원본이 필요해 단방향 해시 불가 → 암호화 vs 평문 중 암호화. 일일 R2 DB 덤프가 실제 "DB만 유출" 경로라 암호화 시 덤프엔 복호 불가 암호문만 남는다(env 동반 유출엔 무력하나 부분 유출엔 실효). 키는 `jwt_secret`·`password_pepper`·`token_pepper`와 **별도**(키 분리 원칙). `lib/totp.py`의 `Fernet` 인스턴스는 모듈 로드 시 1회 생성 - 키가 잘못됐으면 부팅 시 즉시 실패(fail-fast). Fernet/pyotp는 CPU 경량(HMAC/AES)이라 bcrypt와 달리 `to_thread` 오프로드 불필요.

### 컬럼 의미(상태 기계)
`totp_secret IS NULL` = 미등록 → 등록(setup) 시 암호문 저장 + `totp_confirmed_at=NULL`(미확인) → 첫 코드 검증(confirm) 성공 시 `totp_confirmed_at` 세팅 = **활성**. 로그인 2단계는 활성만 통과(B2/B3).

### 부트스트랩 = 스크립트 승격 (공개 관리자 가입 없음)
셀프 가입 경로는 보안 위험이라 없음. 운영자가 `promote_admin.py`로 기존 유저 승격 → 그 유저는 다음 관리자 로그인에서 2FA 등록을 강제받는다. 멱등(이미 owner면 무변경), 미존재/이메일 미인증 거부. 승격은 권한 상승이라 실행 전 대상 이메일 확인. **B3에서 보강**: 기존 refresh 체인 일괄 revoke + 신뢰 기기 revoke + 소셜 전용(비번 없음) 계정 승격 거부(락아웃 방지) - 상세는 B2/B3 문서.

---

## 3. 검증

- `uv run alembic upgrade head` + `alembic check` 클린. `is_admin=true` 행이 `role='owner'`로 이관되는 것 실측 확인(downgrade 왕복 포함)
- Fernet 암호화→복호화 round-trip, role 기본값(reader)·enum 검증, 부트스트랩 상태별(미존재/미인증/이미 owner/승격) 테스트 통과
- `uv run ruff check` 클린, CI 그린(`TOTP_ENCRYPTION_KEY` 시크릿 추가)
