"""JWT 발급·검증 유틸 (M1 B2).

access 토큰만 다룬다. refresh는 opaque 랜덤이라 services/auth_service.py 담당.

payload 구조:
  sub  - str(user_id) UUID 문자열
  typ  - "access" 고정 (수동 검증, PyJWT가 커스텀 클레임 자동 검증 안 함)
  exp  - 만료 시각 (PyJWT 자동 검증)
  iat  - 발급 시각
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from src.config import settings


class TokenError(Exception):
    """만료·위조·잘못된 typ 등 토큰 검증 실패."""


def create_access_token(user_id: str) -> str:
    """user_id(UUID str)로 access JWT 발급. PII(이메일 등) payload 포함 금지."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """JWT 검증 후 payload 반환.

    만료·위조 서명·잘못된 typ 시 TokenError를 raise한다.
    라우터(C 그룹)에서 이 예외를 잡아 401로 매핑한다.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as e:
        raise TokenError("expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("invalid") from e

    if payload.get("typ") != "access":
        raise TokenError("invalid typ")

    return payload
