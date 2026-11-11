"""주문 영수증 저장과 응답이 공유하는 URL 검증."""

import ipaddress
import re
from urllib.parse import urlsplit


def safe_receipt_url(value: str | None) -> str | None:
    if (
        not value
        or len(value) > 2048
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        if (
            "\\" in value
            or not re.fullmatch(r"(?:\[[^\[\]]+\]|[^:]+)(?::[0-9]+)?", parsed.netloc)
            or parsed.port is not None
            and not 1 <= parsed.port <= 65535
        ):
            return None
        try:
            ipaddress.ip_address(host)
        except ValueError:
            labels = host.encode("idna").decode("ascii").split(".")
            if len(host) > 253 or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in labels
            ):
                return None
    except (ValueError, UnicodeError):
        return None
    return value
