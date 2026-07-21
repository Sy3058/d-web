"""lib/totp 단위 테스트 (M1.5 B1). Fernet 암복호 + pyotp 검증(DB 불필요)."""

from datetime import UTC, datetime, timedelta

import pyotp

from src.lib import totp


def test_encrypt_decrypt_roundtrip():
    secret = totp.generate_secret()
    cipher = totp.encrypt_secret(secret)
    assert cipher != secret  # 암호문은 원문(base32)과 다름 - 평문 저장 아님
    assert totp.decrypt_secret(cipher) == secret


def test_encrypt_is_nondeterministic():
    # Fernet은 IV/timestamp를 포함해 같은 원문도 매번 다른 암호문 -> 둘 다 같은 원문으로 복호.
    secret = totp.generate_secret()
    c1 = totp.encrypt_secret(secret)
    c2 = totp.encrypt_secret(secret)
    assert c1 != c2
    assert totp.decrypt_secret(c1) == totp.decrypt_secret(c2) == secret


def test_verify_code_accepts_current():
    secret = totp.generate_secret()
    assert totp.verify_code(secret, pyotp.TOTP(secret).now()) is not None


def test_verify_code_rejects_wrong():
    secret = totp.generate_secret()
    current = pyotp.TOTP(secret).now()
    wrong = f"{(int(current) + 1) % 1000000:06d}"  # 현재 코드와 다른 6자리
    assert totp.verify_code(secret, wrong) is None


def test_verify_code_rejects_malformed():
    # 6자리가 아닌 코드는 결정적으로 거부(길이 불일치라 어떤 창의 코드와도 안 맞음).
    secret = totp.generate_secret()
    assert totp.verify_code(secret, "12") is None


def test_verify_code_returns_matched_step_within_window(monkeypatch):
    # 반환값은 "매칭된 창의 step"(현재 시각의 step이 아님) - replay 가드(#56)의 소모 단위.
    # 시각을 창 중앙(12:00:15)에 고정해 30s 경계 통과에 비의존으로 검증한다.
    secret = totp.generate_secret()
    otp = pyotp.TOTP(secret)
    frozen = datetime(2026, 7, 22, 12, 0, 15, tzinfo=UTC)

    class _FrozenDatetime:
        @staticmethod
        def now(tz: object) -> datetime:
            return frozen

    monkeypatch.setattr(totp, "datetime", _FrozenDatetime)
    step = otp.timecode(frozen)
    assert totp.verify_code(secret, otp.at(frozen)) == step
    assert totp.verify_code(secret, otp.at(frozen + timedelta(seconds=30))) == step + 1
    assert totp.verify_code(secret, otp.at(frozen - timedelta(seconds=30))) == step - 1
    # ±1 창 밖 코드는 거부 - 기존 valid_window=1 동등성 유지.
    assert totp.verify_code(secret, otp.at(frozen + timedelta(seconds=60))) is None


def test_provisioning_uri_has_secret_and_issuer():
    secret = totp.generate_secret()
    uri = totp.provisioning_uri(secret, "admin@example.com")
    assert uri.startswith("otpauth://totp/")
    assert f"secret={secret}" in uri
    assert "issuer=dweb-admin" in uri
