"""인증 서비스 - 비밀번호 해싱 (M1 B1).

해싱은 OWASP Password Storage Cheat Sheet의 pre-hash 구조를 따른다:

    bcrypt( base64( hmac_sha384(password, key=PASSWORD_PEPPER) ), gensalt(cost=12) )

이 구조 하나로 세 가지를 동시에 해결한다.
  - 72바이트 한도: HMAC-SHA384 다이제스트(48B)를 base64로 인코딩하면 64자(<72)로 고정 →
    bcrypt 5.x가 긴 비번에 던지는 ValueError와 조용한 truncate를 모두 회피.
  - pepper: HMAC 키로 서버측 시크릿(DB 밖)을 섞어 DB 단독 유출 시 오프라인 크래킹 차단.
  - password shucking / null 바이트: HMAC + base64로 방어.

bcrypt는 ~250~350ms CPU 블로킹이라, 이벤트 루프를 막지 않도록 워커 스레드로 오프로드한다
(backend/CLAUDE.md "비동기 함수에서 동기 블로킹 호출" 금지). 관련 study: secret-hashing.
"""

import base64
import hashlib
import hmac

import bcrypt
from anyio import to_thread

from src.config import settings

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
