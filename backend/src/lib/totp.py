"""TOTP 2FA 프리미티브 (M1.5 B). Fernet at-rest 암호화 + pyotp 검증.

TOTP 시크릿은 검증 때마다 원본이 필요해 단방향 해시(bcrypt)를 쓸 수 없다. 그래서
되돌릴 수 있는 대칭 암호화(Fernet = AES-128-CBC + HMAC)로 at-rest 저장한다. 키
(TOTP_ENCRYPTION_KEY)는 jwt_secret/password_pepper/token_pepper와 별개다(키 분리 원칙).

일일 R2 DB 덤프가 실제 "DB만 유출" 경로 - 암호화하면 덤프엔 복호 불가한 암호문만 남는다
(단일 VPS 전체 탈취=env 동반 유출엔 무력하나 부분 유출엔 실효). 상세: DECISIONS 결정 3.

Fernet/pyotp 연산은 HMAC/AES라 CPU 경량 - bcrypt와 달리 이벤트 루프 블로킹이 아니라서
to_thread 오프로드가 불필요하다.
"""

import pyotp
from cryptography.fernet import Fernet

from src.config import settings

# 키가 유효한 Fernet 키(32B url-safe base64)가 아니면 여기서(=import=부팅 시) 즉시 실패한다
# (fail-fast). 모듈 1회 생성이라 루프 블로킹 우려 없음(MISTAKES: 고정 비용은 import 시 eager).
_fernet = Fernet(settings.totp_encryption_key.get_secret_value().encode("utf-8"))


def generate_secret() -> str:
    """새 TOTP 시크릿(base32) 생성. 등록(enrollment) 시 1회 발급."""
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    """base32 시크릿 원문 -> Fernet 암호문(str). DB totp_secret 저장용."""
    return _fernet.encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """DB의 Fernet 암호문 -> base32 시크릿 원문. 코드 검증 직전에만 복호."""
    return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")


def provisioning_uri(secret: str, account_email: str) -> str:
    """authenticator 앱 등록용 otpauth:// URI(QR 인코딩용).

    시크릿 원문이 URI에 담긴다(등록의 본질) - 이 URI는 등록 1회 표시에만 쓰고 응답 바디의
    별도 필드로 노출하거나 로깅하지 않는다.
    """
    return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=settings.totp_issuer)


def verify_code(secret: str, code: str) -> bool:
    """제출된 6자리 코드가 유효한지 검증. valid_window=1로 ±30s 시계 드리프트 허용."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)
