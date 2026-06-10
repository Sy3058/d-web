# 리프레시 회전 race 원자화 (M1 그룹 I - I1)

| 항목 | 내용 |
|------|------|
| 모듈 | Backend / Auth |
| 관련 마일스톤 | [M1](../../../milestones/M1_foundation.md) 그룹 I - I1 (council 리뷰 fix, 이슈 #28) |
| 작성 시점 | M1 I1 (2026-06-10) |
| 상태 | 구현 완료, `pytest` 59개 통과 + Opus 자가 검증(Critical/Major 없음) |
| 관련 문서 | [SECURITY_AUTH_DECISIONS.md](./SECURITY_AUTH_DECISIONS.md) §2, [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md)(B2 프리미티브), [IMPLEMENTATION_AUTH_ENDPOINTS.md](./IMPLEMENTATION_AUTH_ENDPOINTS.md)(C4 회전) |

council 리뷰(2026-06-06)가 **머지 블로커(보안)**로 식별한 회전 race 수정. 기존 `rotate_refresh`는 락 없이 `SELECT`(revoke 확인) → `record.revoked_at=now()` → 신규 INSERT라, 동시 2요청이 SELECT를 둘 다 통과하면 **한 옛 토큰에서 새 토큰 2개**가 발급된다(회전 불변식 붕괴 → 재사용 탐지 무력화 / 정상유저 오탐). DB 조건부 UPDATE 선점 + `token_hash` UNIQUE 인덱스로 원자화한다.

---

## 1. 산출물

| 파일 | 내용 |
|------|------|
| `backend/src/models/user.py` | `RefreshToken` `uq_refresh_tokens_token_hash` UNIQUE 인덱스 |
| `backend/migrations/versions/20260610_0727_refresh_token_hash_unique_index.py` | 인덱스 마이그레이션 `97b9912aa03e` (forward-only, down=`6d33b06659a8`) |
| `backend/src/services/auth_service.py` | `_claim_refresh_token` 헬퍼 + `rotate_refresh` 원자화 |
| `backend/tests/test_token.py` | 결정적 테스트 2개 |

새 의존성 없음(`sqlalchemy.update`는 기존 설치).

---

## 2. 문제: check-then-act race

```
요청1: SELECT(revoked_at IS NULL ✓) ─┐
요청2: SELECT(revoked_at IS NULL ✓) ─┤  둘 다 통과
요청1: revoke A + INSERT 새 토큰 B    │
요청2: revoke A + INSERT 새 토큰 C    ┘  옛 토큰 A에서 B·C 둘 발급
```
- 회전 불변식("옛 토큰 1개 → 새 토큰 1개")이 깨져 **재사용 탐지가 무력화**되거나 정상 유저가 오탐으로 끊긴다.
- **트랜잭션으로 묶어도** 락/조건이 없으면 발생(원자성 ≠ 동시성). 앱 락(`asyncio.Lock`)은 멀티워커(gunicorn -w N)에서 프로세스별 메모리라 무효 → 모든 워커가 공유하는 **DB가 유일한 직렬화 지점**.

---

## 3. 해법: 조건부 UPDATE 선점

```python
async def _claim_refresh_token(record, session) -> bool:
    result = await session.exec(
        update(RefreshToken)
        .where(RefreshToken.id == record.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1   # 승자만 True
```
`rotate_refresh` 흐름:
```
get_refresh_token(raw)
  None                      → InvalidTokenError (401)
  revoked_at IS NOT NULL    → 재사용 탐지: 전체 revoke + commit → TokenReuseError (401)
  expired                   → InvalidTokenError (401)
  _claim() == False (패자)  → rollback → InvalidTokenError (401, 세션 유지)
  _claim() == True  (승자)  → 신규 refresh/access 발급 + commit (단일 트랜잭션)
```
- **Postgres READ COMMITTED**: 동시 UPDATE는 행 락으로 직렬화. 승자가 commit한 뒤, 패자의 UPDATE는 잠금 해제 시점의 **최신 행 버전으로 WHERE 재평가** → `revoked_at IS NOT NULL` → 0행 → `rowcount=0`. 별도 SELECT 없이 단일 문장으로 한 명만 승자.
- SQLModel 0.0.38: `session.exec(update(...))`가 `CursorResult`(`.rowcount`) 반환. `session.execute`는 deprecation 경고라 `exec` 사용.

---

## 4. 핵심 결정

- **race 패자 = 401 단순 거부, 세션 유지** (확정 2026-06-10): 패자 분기는 SELECT 땐 유효였는데 그 사이 동시 회전/로그아웃이 끼어든 경우라 **탈취 신호가 아니다**(정상 더블클릭). 전체 revoke하면 정상 유저 세션이 통째로 끊기는 오탐. 라우터가 `TokenReuseError`(자식)를 먼저, `InvalidTokenError`(부모)를 나중에 잡아 매핑 자동 정합.
- **진짜 stale-reuse는 기존 분기 유지**: SELECT 시점에 이미 `revoked_at`이 set이면 회전이 끝난 토큰의 재제출 → 전체 revoke(탈취 대응).
- **`token_hash` UNIQUE 인덱스**: (a) `/auth/refresh`·로그인의 `WHERE token_hash=?` hot path seq scan 제거 (b) 한 토큰에서 새 토큰 2개를 DB가 거부하는 불변식 방어선. 결정적 해시 + 고엔트로피라 충돌 없어 UNIQUE 가능. 단일 소형 VPS라 plain `CREATE UNIQUE INDEX`(대용량이면 `CONCURRENTLY`).

study: `db-atomic-claim`, `refresh-token-rotation`.

---

## 5. 검증

`uv run pytest` 59개 통과(기존 57 + I1 2), `ruff check` clean, `alembic check` 클린(single head), Opus 자가 검증 Critical/Major 없음.

| 테스트 | 확인 |
|--------|------|
| `test_claim_refresh_token_single_winner` | 같은 토큰 선점 1회차 True·2회차 False (동시성 결정적 프록시) |
| `test_refresh_token_hash_unique` | 같은 token_hash 중복 INSERT → IntegrityError |
| `test_refresh_rotates_token` (기존) | happy-path 회전: 2행, 1 revoked / 1 active 유지 |
| `test_refresh_reuse_revokes_session` (기존) | stale 재제출 → 세션 전체 revoke + 401 |

> 진짜 동시성은 결정적 재현이 불가해 `_claim` rowcount 멱등(1→0)을 프록시로 검증. 실제 동시성 보증은 DB 조건부 UPDATE 의미론에 위임.

---

## 6. 제약 / 후속

- **절대 수명 cap 미구현**: 회전이 무한 연장되지 않게 하는 상한(예: 30일)은 별도. [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md) §후속, I1 범위 밖.
- **rate limit (I2)**: `/auth/refresh` 자체엔 rate limit 미부착. 인증 표면 rate limit은 `be/feat/auth-rate-limit`(I2).
- 이 fix로 [IMPLEMENTATION_TOKEN.md](./IMPLEMENTATION_TOKEN.md) §후속·[IMPLEMENTATION_EMAIL_VERIFY.md](./IMPLEMENTATION_EMAIL_VERIFY.md) §5의 "token_hash 인덱스 누락", [IMPLEMENTATION_AUTH_ENDPOINTS.md](./IMPLEMENTATION_AUTH_ENDPOINTS.md)의 "refresh 회전 row lock 부재" FYI가 해소됨.
