"""HaveIBeenPwned k-anonymity 유출 비번 검사 (M1 C1, AUTH-01).

비번 SHA-1 해시의 앞 5자리(prefix)만 외부로 보내고, 나머지(suffix)는 응답받은
후보 목록과 로컬에서 대조한다(k-anonymity). 원문·전체 해시는 외부로 나가지 않는다.
외부 API 장애 시 가입을 막지 않도록 fail-open + 경고 로깅(가용성 우선).
"""

import hashlib

import httpx
import structlog

logger = structlog.get_logger(__name__)

_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
_TIMEOUT_SECONDS = 3.0


async def is_password_pwned(password: str) -> bool:
    """비번이 알려진 유출 목록에 있으면 True. 외부 장애 시 False(fail-open)."""
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()  # noqa: S324
    prefix, suffix = sha1[:5], sha1[5:]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            # Add-Padding: 응답 크기로 prefix를 추측하지 못하게 패딩 요청(프라이버시)
            response = await client.get(
                _HIBP_RANGE_URL.format(prefix=prefix),
                headers={"Add-Padding": "true"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("hibp_check_failed_fail_open", error=str(exc))
        return False

    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        # 패딩 항목은 count=0. suffix 일치 + count>0 만 유출로 판정.
        if candidate.strip().upper() == suffix and count.strip() not in ("", "0"):
            return True
    return False
