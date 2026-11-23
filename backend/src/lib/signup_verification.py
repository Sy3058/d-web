"""가입 이메일 proof 쿠키 경계."""

from fastapi import Response

from src.config import settings


def cookie_name() -> str:
    return "__Host-signup_verification" if settings.cookie_secure else "signup_verification"


def set_signup_verification_cookie(response: Response, proof: str) -> None:
    response.set_cookie(
        key=cookie_name(),
        value=proof,
        max_age=15 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def clear_signup_verification_cookie(response: Response) -> None:
    response.delete_cookie(
        key=cookie_name(),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
