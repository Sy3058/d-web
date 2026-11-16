"""현재 사용자 계정 설정 입력 경계."""

import unicodedata
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.auth import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, validate_password_policy


class NicknameUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nickname: str = Field(min_length=1, max_length=50)

    @field_validator("nickname", mode="before")
    @classmethod
    def _nickname(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("닉네임에는 제어 문자를 사용할 수 없습니다")
        return value.strip()


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    confirm_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return validate_password_policy(value)

    @model_validator(mode="after")
    def _confirmation(self) -> Self:
        if self.new_password != self.confirm_password:
            raise ValueError("새 비밀번호 확인이 일치하지 않습니다")
        return self
