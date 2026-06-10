"""인증 서비스 - 비밀번호 해싱 (M1 B1) + refresh 토큰 프리미티브 (M1 B2).

비밀번호 해싱은 OWASP Password Storage Cheat Sheet의 pre-hash 구조를 따른다:

    bcrypt( base64( hmac_sha384(password, key=PASSWORD_PEPPER) ), gensalt(cost=12) )

이 구조 하나로 세 가지를 동시에 해결한다.
  - 72바이트 한도: HMAC-SHA384 다이제스트(48B)를 base64로 인코딩하면 64자(<72)로 고정 ->
    bcrypt 5.x가 긴 비번에 던지는 ValueError와 조용한 truncate를 모두 회피.
  - pepper: HMAC 키로 서버측 시크릿(DB 밖)을 섞어 DB 단독 유출 시 오프라인 크래킹 차단.
  - password shucking / null 바이트: HMAC + base64로 방어.

bcrypt는 ~250~350ms CPU 블로킹이라, 이벤트 루프를 막지 않도록 워커 스레드로 오프로드한다
(backend/CLAUDE.md "비동기 함수에서 동기 블로킹 호출" 금지). 관련 study: secret-hashing.

refresh 토큰은 secrets.token_urlsafe(32) opaque 랜덤(256bit).
DB에는 HMAC-SHA256(token, key=TOKEN_PEPPER) 해시만 저장. 고엔트로피라 빠른 해시로 충분.
결정적 해시라 WHERE token_hash=? 직접 조회 가능. study: secret-hashing, refresh-token-rotation.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from anyio import to_thread
from fastapi import BackgroundTasks
from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.config import settings
from src.lib.auth import create_access_token
from src.lib.exceptions import (
    EmailVerificationError,
    InvalidCredentialsError,
    InvalidTokenError,
    PwnedPasswordError,
    TokenReuseError,
)
from src.models.user import EmailVerification, RefreshToken, User
from src.services import email_service, hibp

# OWASP work factor >= 10. 소형 VPS 기준 cost=12 (배포 후 ~250~350ms 되도록 보정).
_BCRYPT_ROUNDS = 12


def _prehash(plain: str) -> bytes:
    """비번을 pepper로 HMAC-SHA384 → base64. bcrypt에 넣기 전 고정 길이(64자)로 정규화.

    반드시 raw digest(48B)를 base64. hexdigest(96자)는 다시 72바이트를 초과해 truncate된다.
    """
    digest = hmac.new(
        settings.password_pepper.get_secret_value().encode("utf-8"),
        plain.encode("utf-8"),
        hashlib.sha384,
    ).digest()
    return base64.b64encode(digest)


def _hash_sync(prehashed: bytes) -> str:
    return bcrypt.hashpw(prehashed, bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("utf-8")


def _verify_sync(prehashed: bytes, hashed: str) -> bool:
    return bcrypt.checkpw(prehashed, hashed.encode("utf-8"))


async def hash_password(plain: str) -> str:
    """평문 비번 → 저장용 해시 문자열. bcrypt는 스레드로 오프로드."""
    return await to_thread.run_sync(_hash_sync, _prehash(plain))


async def verify_password(plain: str, hashed: str) -> bool:
    """평문 비번이 저장된 해시와 일치하는지 확인. 상수 시간 비교(bcrypt.checkpw)."""
    return await to_thread.run_sync(_verify_sync, _prehash(plain), hashed)


# ---------------------------------------------------------------------------
# Refresh 토큰 프리미티브 (M1 B2)
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    """opaque 토큰 원문을 HMAC-SHA256(+TOKEN_PEPPER) 해시로 변환.

    결정적 해시라 WHERE token_hash=? 직접 조회 가능.
    HMAC은 빠른 해시지만 256bit 랜덤 토큰은 brute-force가 물리적으로 불가라 충분.
    """
    return hmac.new(
        settings.token_pepper.get_secret_value().encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def create_refresh_token(user_id: uuid.UUID, session: AsyncSession) -> str:
    """refresh 토큰을 발급하고 hash를 DB에 저장(flush)한다. 원문을 반환(쿠키용).

    commit은 하지 않는다 - 호출자(C2 로그인, C4 회전)가 트랜잭션 경계를 잡는다.
    flush로 INSERT를 보내 FK 위반 등을 이 시점에 노출시킨다.
    """
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    record = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(raw),
        expires_at=expires_at,
    )
    session.add(record)
    await session.flush()
    return raw


async def get_refresh_token(raw: str, session: AsyncSession) -> RefreshToken | None:
    """원문 토큰으로 DB 행을 조회해 반환한다.

    revoked/만료 여부는 호출자가 판단한다. revoke된 행도 반환해야 C4 재사용 탐지 가능.
    """
    token_hash = _hash_token(raw)
    result = await session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.first()


async def revoke_refresh_token(record: RefreshToken, session: AsyncSession) -> None:
    """refresh 토큰 1건을 revoke 표시한다. commit은 호출자 책임."""
    record.revoked_at = datetime.now(UTC)
    session.add(record)


async def revoke_all_refresh_tokens(user_id: uuid.UUID, session: AsyncSession) -> None:
    """유저의 유효한 refresh 토큰을 전부 revoke 표시한다. 재사용 탐지 시 세션 전체 무효화용.

    commit은 호출자 책임(C4에서 신규 발급과 한 트랜잭션으로 묶기 위함).
    """
    now = datetime.now(UTC)
    result = await session.exec(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
        )
    )
    for record in result.all():
        record.revoked_at = now
        session.add(record)


async def _claim_refresh_token(record: RefreshToken, session: AsyncSession) -> bool:
    """회전 시 revoke를 원자적으로 '선점'한다. revoked_at IS NULL인 행만 now()로 갱신하고,
    실제로 갱신된 행 수(rowcount)가 1이면 이 요청이 회전 승자, 0이면 그 사이 다른
    요청/로그아웃이 이미 revoke한 패자다.

    멀티워커에선 앱 락이 프로세스별 메모리라 무효 → 모든 워커가 공유하는 단일 지점인 DB의
    조건부 UPDATE로 단일 승자를 보장한다(Postgres 행 락 + READ COMMITTED 재평가:
    동시 UPDATE는 직렬화되고, 패자는 잠금 해제 후 revoked_at IS NOT NULL을 보고 0행 매칭).
    commit은 호출자(rotate_refresh)가 신규 발급과 한 트랜잭션으로 묶는다.

    synchronize_session=False: 직후 in-memory record를 다시 안 읽고 새 토큰만 INSERT하므로
    ORM identity-map 동기화가 불필요(불필요한 추가 SELECT 회피).
    """
    result = await session.exec(
        update(RefreshToken)
        .where(
            RefreshToken.id == record.id,
            RefreshToken.revoked_at.is_(None),  # type: ignore[union-attr]
        )
        .values(revoked_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# 이메일 인증 토큰 (M1 C1 발급, E1에서 발송/E2에서 검증)
# ---------------------------------------------------------------------------


async def create_email_verification(user_id: uuid.UUID, session: AsyncSession) -> str:
    """이메일 인증 토큰을 발급하고 at-rest 해시를 DB에 저장(flush). 원문 반환(메일 링크용).

    refresh와 동일하게 원문은 고엔트로피 랜덤, DB엔 HMAC 해시만(B2 키 정책). 유효 1시간.
    commit은 호출자(signup)가 user 생성과 한 트랜잭션으로 묶는다.
    """
    raw = secrets.token_urlsafe(32)
    record = EmailVerification(
        user_id=user_id,
        token=_hash_token(raw),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(record)
    await session.flush()
    return raw


async def verify_email(raw_token: str, session: AsyncSession) -> None:
    """이메일 인증 토큰 검증. 유효 시 유저를 인증 완료로 표시(멱등). 실패 시 EmailVerificationError.

    입력 토큰을 동일 HMAC 해시해 결정적 조회(E1 at-rest 해시와 대조).
    거부(무효/만료/사용됨)는 호출자가 단일 generic 400으로 통일(구분 노출 안 함).
    멱등: 이미 인증된 유저면 email_verified_at은 보존하고 토큰(used_at)만 소비한다.
    동시 더블클릭은 둘 다 인증 완료라는 같은 결과(멱등)라 별도 락이 필요 없다.
    """
    token_hash = _hash_token(raw_token)
    result = await session.exec(
        select(EmailVerification).where(EmailVerification.token == token_hash)
    )
    record = result.first()
    if (
        record is None
        or record.used_at is not None
        or record.expires_at <= datetime.now(UTC)
    ):
        raise EmailVerificationError

    user = await session.get(User, record.user_id)
    if user is None:  # FK 무결성상 사실상 도달 불가
        raise EmailVerificationError

    now = datetime.now(UTC)
    record.used_at = now
    if not user.is_email_verified:
        user.is_email_verified = True
        user.email_verified_at = now
    session.add(record)
    session.add(user)
    await session.commit()


async def invalidate_email_verifications(
    user_id: uuid.UUID, session: AsyncSession
) -> None:
    """유저의 미사용 이메일 인증 토큰을 전부 무효화(used_at 세팅). commit은 호출자 책임.

    재발송(E3) 시 직전 토큰들을 죽여 '최신 메일 링크만 동작'을 보장한다.
    refresh의 revoke_all_refresh_tokens와 동형 - '재발송 = 직전 토큰 무효화' 규칙을
    인증 토큰과 (향후 P1) 비번재설정 토큰 전반에 통일하기 위함.
    """
    now = datetime.now(UTC)
    result = await session.exec(
        select(EmailVerification).where(
            EmailVerification.user_id == user_id,
            EmailVerification.used_at.is_(None),  # type: ignore[union-attr]
        )
    )
    for record in result.all():
        record.used_at = now
        session.add(record)


# ---------------------------------------------------------------------------
# 유저 CRUD + 인증 플로우 (M1 C 그룹)
# ---------------------------------------------------------------------------


def _normalize_email(email: str) -> str:
    """대소문자 차이로 중복 계정/우회가 생기지 않도록 정규화."""
    return email.strip().lower()


# 타이밍 평탄화용 고정 더미 해시. 비번과 무관하게 항상 같은 값이라 import 시 1회 생성한다.
# lazy로 미루면 첫 호출(최초 로그인 실패/중복 가입) 때 bcrypt(~300ms)가 이벤트 루프를
# 블로킹한다. 부팅 시점(루프 없음)에 미리 내면 무해. _prehash/_hash_sync 정의 이후라 OK.
_DUMMY_HASH = _hash_sync(_prehash("timing-flatten-dummy"))


async def _dummy_verify() -> None:
    """미존재/소셜전용/중복 경로에서 더미 해시를 검증해 응답 시간을 평탄화한다.

    실제 verify_password와 같은 bcrypt 비용을 소비해 타이밍 enumeration을 막는다.
    더미 해시는 import 시 미리 만들어 둔 고정값(_DUMMY_HASH), verify만 워커 스레드로 오프로드.
    """
    await verify_password("timing-flatten-dummy", _DUMMY_HASH)


async def get_user_by_email(email: str, session: AsyncSession) -> User | None:
    """유효한(soft delete 안 된) 유저를 이메일로 조회."""
    result = await session.exec(
        select(User).where(
            User.email == _normalize_email(email),
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.first()


async def create_user(
    email: str, password: str, nickname: str, session: AsyncSession
) -> User:
    """이메일/비번 유저를 미인증 상태로 생성(flush). commit은 호출자 책임."""
    user = User(
        email=_normalize_email(email),
        hashed_password=await hash_password(password),
        nickname=nickname,
        is_email_verified=False,
    )
    session.add(user)
    await session.flush()
    return user


async def signup(
    email: str,
    password: str,
    nickname: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """회원가입. 비열거: 신규/중복 모두 호출자는 동일 응답을 반환한다.

    - 유출 비번(HIBP) → PwnedPasswordError (이메일 존재와 무관 → 422 노출 안전)
    - 신규: 미인증 user 생성 + 인증 토큰 발급 → commit 후 인증 메일(백그라운드)
    - 중복: user 생성 안 함 + 더미 해시로 타이밍 평탄화 + '이미 가입됨' 안내 메일
    메일 발송은 BackgroundTasks라 DB commit 이후 실행(메일 실패가 가입을 롤백 안 함).
    """
    email = _normalize_email(email)
    if await hibp.is_password_pwned(password):
        raise PwnedPasswordError

    existing = await get_user_by_email(email, session)
    if existing is not None:
        await _dummy_verify()  # 신규 경로의 bcrypt 비용과 시간 정합
        background_tasks.add_task(email_service.send_already_registered_email, email)
        return

    user = await create_user(email, password, nickname, session)
    raw_token = await create_email_verification(user.id, session)
    await session.commit()
    background_tasks.add_task(email_service.send_verification_email, email, raw_token)


async def resend_verification(
    email: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    """인증 메일 재발송(E3). 비열거: 회원/인증 여부와 무관하게 호출자는 동일 응답.

    - 미존재 / 이미 인증된 유저 → no-op (DB 변경·발송 없음)
    - 미인증 유저 → 기존 미사용 토큰 무효화 + 신규 토큰 발급을 한 트랜잭션으로 commit,
      이후 인증 메일을 BackgroundTasks로(응답 후 실행 → 메일 실패가 발급을 롤백 안 함).

    조회는 get_user_by_email(내부 _normalize_email) 경유 - 대소문자/공백 차이로 정상
    유저가 no-op에 빠지는 가용성 버그를 막는다. resend엔 bcrypt가 없어 signup/login식
    더미 해시 평탄화는 불필요하다. 잔여 타이밍 차(미인증 경로의 DB write 몇 건)는
    응답 바디 동일 + 재발송 rate limit(F1)으로 커버한다(완전 평탄화 아님 - 의도된 한계).
    """
    user = await get_user_by_email(email, session)
    if user is None or user.is_email_verified:
        return
    await invalidate_email_verifications(user.id, session)
    raw_token = await create_email_verification(user.id, session)
    await session.commit()
    background_tasks.add_task(
        email_service.send_verification_email, user.email, raw_token
    )


async def login(
    email: str, password: str, session: AsyncSession
) -> tuple[User, str, str]:
    """이메일/비번 검증 후 (user, access_token, refresh_token) 반환. 실패 시 401 매핑.

    미존재/소셜전용 계정도 더미 해시를 돌려 응답 시간을 맞춘다(비열거).
    """
    email = _normalize_email(email)
    user = await get_user_by_email(email, session)
    if user is None or user.hashed_password is None:
        await _dummy_verify()
        raise InvalidCredentialsError
    if not await verify_password(password, user.hashed_password):
        raise InvalidCredentialsError

    access = create_access_token(str(user.id))
    refresh = await create_refresh_token(user.id, session)
    await session.commit()
    return user, access, refresh


async def logout(user_id: uuid.UUID, session: AsyncSession) -> None:
    """유저의 refresh 토큰을 전부 revoke(전체 로그아웃) + commit.

    refresh 쿠키는 Path=/auth/refresh라 /auth/logout엔 안 실린다. 특정 토큰을 받을 수
    없으므로 access 토큰으로 식별한 유저의 세션 전체를 무효화한다.
    """
    await revoke_all_refresh_tokens(user_id, session)
    await session.commit()


async def rotate_refresh(raw: str, session: AsyncSession) -> tuple[User, str, str]:
    """refresh 회전. (user, new_access, new_refresh) 반환.

    - 미존재/만료 → InvalidTokenError
    - 이미 revoke된 토큰 재제출(SELECT 시점에 이미 revoked) → 재사용 탐지: 세션 전체
      revoke + commit → TokenReuseError
    - 유효 → revoke를 원자적으로 선점(_claim)한 단 하나의 요청만 신규 refresh/access를
      한 트랜잭션으로 발급. 선점 실패(패자)는 SELECT 직후 동시 회전/로그아웃이 끼어든
      정상 케이스라 탈취가 아님 → 세션 유지하고 단순 거부(InvalidTokenError → 401).
    """
    record = await get_refresh_token(raw, session)
    if record is None:
        raise InvalidTokenError

    # 제출된 토큰 자체가 이미 죽음(stale): 회전이 지난 토큰의 재제출 = 탈취 신호.
    # (아래 _claim 패자와 구분 - 패자는 SELECT 땐 살아있던 토큰을 찰나에 남이 회전시킨 정상 경우)
    if record.revoked_at is not None:
        await revoke_all_refresh_tokens(record.user_id, session)
        await session.commit()
        raise TokenReuseError

    if record.expires_at <= datetime.now(UTC):
        raise InvalidTokenError

    # _claim 패자(rowcount=0): SELECT 땐 유효였는데 그 사이 동시 회전/로그아웃이 끼어든
    # 정상 케이스(탈취 아님) → 세션 유지하고 단순 401. 진짜 stale 재사용은 위 분기가 잡는다.
    if not await _claim_refresh_token(record, session):
        await session.rollback()
        raise InvalidTokenError

    new_refresh = await create_refresh_token(record.user_id, session)
    user = await session.get(User, record.user_id)
    assert user is not None  # FK 무결성상 항상 존재
    access = create_access_token(str(record.user_id))
    await session.commit()
    return user, access, new_refresh
