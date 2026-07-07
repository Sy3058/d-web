"""인증 엔드포인트 요청/응답 스키마 (M1 C 그룹).

table=True 모델과 분리된 순수 입력 검증/응답 DTO.
비번 정책은 서버에서 강제한다(프론트는 UX 보조). 최대 길이 상한으로 초장문 비번
CPU DoS와 bcrypt 72바이트 truncate 우회를 함께 막는다(AUTH-01).
"""

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

# AUTH-01: 8자 이상 + 영문·숫자·특수문자 각 1개 이상. 상한 128.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")
_HAS_SPECIAL = re.compile(r"[^A-Za-z0-9]")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    nickname: str = Field(min_length=1, max_length=50)

    @field_validator("password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        if not _HAS_LETTER.search(v):
            raise ValueError("영문을 1자 이상 포함해야 합니다")
        if not _HAS_DIGIT.search(v):
            raise ValueError("숫자를 1자 이상 포함해야 합니다")
        if not _HAS_SPECIAL.search(v):
            raise ValueError("특수문자를 1자 이상 포함해야 합니다")
        return v


class LoginRequest(BaseModel):
    # 로그인은 정책 재검증 불필요(이미 가입된 비번). 상한만 둬 DoS 방지.
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class VerifyEmailRequest(BaseModel):
    # 토큰은 secrets.token_urlsafe(32)=43자. 상한으로 초장문 입력 DoS 방지.
    # 원문 토큰은 비로깅(E1 일관) - body로 받아 URL/쿼리 로깅도 회피한다.
    token: str = Field(min_length=1, max_length=512)


class ResendVerificationRequest(BaseModel):
    # 비인증 엔드포인트라 이메일을 body로 받는다(방금 가입한 비로그인 유저도 사용).
    # 비열거: 회원 여부와 무관하게 라우터는 항상 동일 응답을 반환한다(M1 E3).
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class TotpConfirmRequest(BaseModel):
    # 6자리 고정. 앞자리 0 보존을 위해 str로 받는다 (M1.5 B2).
    code: str = Field(pattern=r"^[0-9]{6}$")


class TotpSetupResponse(BaseModel):
    # 시크릿 원문은 이 URI(QR 인코딩용 1회 표시) 안에만 존재 - 별도 필드 노출 금지 (M1.5 B2).
    otpauth_uri: str
