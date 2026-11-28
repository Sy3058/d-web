"""이메일 발송 서비스 - Resend API 연동 (M1 E1).

발송은 FastAPI BackgroundTasks로 응답 후 실행 - 메일 실패가 가입을 롤백하지 않음.
외부 API 장애 및 키 미설정 시 fail-open (경고 로그 + no-op). HIBP와 동일 철학.

보안 원칙:
- 이메일 전체 plaintext 로깅 금지 - 마스킹(_mask_email) 적용
- 원문 토큰 / 인증 URL 비로깅 (이벤트명 + 마스킹 이메일만)
- 메일 HTML에 user input 미삽입 (HTML 인젝션 방지)
"""

import html as html_module

import httpx
import structlog

from src.config import settings

logger = structlog.get_logger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_TIMEOUT_SECONDS = 5.0


def _mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    head = local[0] if local else ""
    return f"{head}***{sep}{domain}"


async def _send(
    to: str,
    subject: str | None = None,
    html: str | None = None,
    *,
    template: dict[str, object] | None = None,
) -> None:
    """Resend API로 메일 1건을 발송한다. 키 미설정 또는 HTTP 오류 시 fail-open."""
    api_key = settings.resend_api_key.get_secret_value()
    if not api_key:
        logger.warning("email_send_skipped_no_api_key", to=_mask_email(to))
        return

    try:
        payload: dict[str, object] = {"to": [to]}
        if subject is not None:
            payload["subject"] = subject
        if template is not None:
            payload["template"] = template
        else:
            payload["from"] = settings.email_from
            payload["html"] = html
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("email_send_failed_fail_open", to=_mask_email(to), error=str(exc))


def _verification_html(verify_url: str) -> str:
    safe_url = html_module.escape(verify_url)
    return f"""
<p>안녕하세요.</p>
<p>아래 버튼을 눌러 이메일 인증을 완료하세요. 링크는 <strong>1시간</strong> 동안 유효합니다.</p>
<p>
  <a href="{safe_url}"
     style="display:inline-block;padding:12px 24px;background:#111;color:#fff;
            text-decoration:none;border-radius:6px;font-weight:bold;">
    이메일 인증하기
  </a>
</p>
<p style="color:#888;font-size:12px;">
  버튼이 동작하지 않으면 아래 주소를 브라우저에 직접 붙여넣으세요.<br>
  {safe_url}
</p>
""".strip()


async def send_verification_email(email: str, token: str) -> None:
    """가입 인증 메일 발송. 토큰 원문은 URL에만, 로그에는 절대 남기지 않는다."""
    verify_url = f"{settings.app_base_url}/auth/verify-email?token={token}"
    logger.info("verification_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        subject="[dweb] 이메일 인증을 완료해 주세요",
        html=_verification_html(verify_url),
    )


async def send_signup_code_email(email: str, code: str) -> None:
    """가입 전 6자리 인증 코드를 발송한다. 코드는 로그에 남기지 않는다."""
    logger.info("signup_code_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        template={"id": "email-verification", "variables": {"verifycode": code}},
    )


async def send_already_registered_email(email: str) -> None:
    """중복 가입 시도 시 '이미 가입된 계정' 안내 메일. 비열거 정책의 핵심."""
    login_url = f"{settings.app_base_url}/auth/login"
    logger.info("already_registered_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        template={"id": "already-registered", "variables": {"loginurl": login_url}},
    )


async def send_google_registered_email(email: str) -> None:
    """Google 가입 계정에 비밀번호 대신 Google 로그인을 안내한다."""
    login_url = f"{settings.app_base_url}/auth/login"
    logger.info("google_registered_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        template={"id": "gmail-registered", "variables": {"loginurl": login_url}},
    )


async def send_non_registered_email(email: str) -> None:
    """미가입 주소에 가입 경로를 안내한다."""
    register_url = f"{settings.app_base_url}/auth/signup"
    logger.info("non_registered_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        template={
            "id": "non-registered",
            "variables": {"registerurl": register_url},
        },
    )


async def send_password_reset_email(email: str, token: str) -> None:
    """재설정 원문 토큰은 URL fragment에만 포함하고 로그에는 남기지 않는다."""
    reset_url = f"{settings.app_base_url}/auth/reset-password#token={token}"
    logger.info("password_reset_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        template={"id": "password-reset", "variables": {"reseturl": reset_url}},
    )


async def send_password_reset_complete_email(email: str, login_url: str | None = None) -> None:
    """비밀번호 변경 사실만 알린다. 비밀번호와 재설정 토큰은 포함하지 않는다."""
    logger.info("password_reset_complete_email_sending", email=_mask_email(email))
    login_url = login_url or f"{settings.app_base_url.rstrip('/')}/auth/login"
    await _send(
        to=email,
        template={
            "id": "password-reset-complete",
            "variables": {"loginurl": login_url},
        },
    )
