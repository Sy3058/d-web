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


async def _send(to: str, subject: str, html: str) -> None:
    """Resend API로 메일 1건을 발송한다. 키 미설정 또는 HTTP 오류 시 fail-open."""
    api_key = settings.resend_api_key.get_secret_value()
    if not api_key:
        logger.warning("email_send_skipped_no_api_key", to=_mask_email(to))
        return

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                },
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


def _already_registered_html(login_url: str) -> str:
    safe_login = html_module.escape(login_url)
    return f"""
<p>안녕하세요.</p>
<p>이 이메일 주소로 이미 가입된 계정이 있습니다.</p>
<p><a href="{safe_login}">로그인하기</a></p>
<p style="color:#888;font-size:12px;">
  본인이 가입을 시도하지 않으셨다면 이 메일을 무시하셔도 됩니다.
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


async def send_already_registered_email(email: str) -> None:
    """중복 가입 시도 시 '이미 가입된 계정' 안내 메일. 비열거 정책의 핵심."""
    login_url = f"{settings.app_base_url}/auth/login"
    logger.info("already_registered_email_sending", email=_mask_email(email))
    await _send(
        to=email,
        subject="[dweb] 이미 가입된 이메일입니다",
        html=_already_registered_html(login_url),
    )
