"""이메일 발송 서비스 - C1↔E1 계약 (M1).

C 그룹은 인터페이스(시그니처)만 고정한 스텁이다. 실제 Resend 연동은 E1에서 구현한다
(A4 SPF/DKIM 외부 블로커 선행). C1 회원가입이 이 함수들을 호출한다.

비열거: 신규=인증 메일, 중복=이미 가입됨 안내로 분기는 '메일 내용'에서만.
HTTP 응답은 양쪽 동일하므로 회원 여부는 수신함 주인만 안다.
⚠️ 개인정보(이메일 전체) plaintext 로깅 금지 - 마스킹 적용.
"""

import structlog

logger = structlog.get_logger(__name__)


def _mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***{sep}{domain}"


async def send_verification_email(email: str, token: str) -> None:
    """가입 인증 메일 발송. E1에서 Resend 연동, 지금은 no-op + 로깅.

    token(원문)은 메일 링크에만 싣고 로깅하지 않는다(at-rest 해시는 DB에 별도 저장).
    """
    logger.info("verification_email_queued", email=_mask_email(email))


async def send_already_registered_email(email: str) -> None:
    """중복 가입 시도 시 '이미 가입된 계정' 안내 메일(로그인/비번재설정 링크).

    비열거 정책의 핵심: 이 메일을 받는 사람만 회원임을 안다.
    """
    logger.info("already_registered_email_queued", email=_mask_email(email))
