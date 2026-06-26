"""계정 / 인증 도메인 모델 (DB_SCHEMA §1 "계정/인증 도메인").

SQLModel `table=True` 모델은 DB 테이블이자 내부 타입. 응답에 그대로 쓰지 말 것
(`hashed_password` 등 민감 필드 노출 방지). 외부 응답은 `UserRead` 등 별도 스키마 사용.

PK는 DB_SCHEMA "설계 원칙"대로 전 테이블 UUID(`gen_random_uuid()`).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlmodel import Field, SQLModel


def _pk_column() -> Column:
    """UUID PK, DB측 gen_random_uuid() 기본값 (DB_SCHEMA 설계 원칙)."""
    return Column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _fk_user_column() -> Column:
    """users.id 참조 FK. soft delete가 기본이라 cascade 실제 발동은 드묾."""
    return Column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created_at_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        # soft delete 필터링: deleted_at IS NULL 조회 최적화 (DB_SCHEMA §6)
        Index(
            "idx_users_deleted_at",
            "deleted_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    email: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    # 소셜 전용 가입은 NULL (DB_SCHEMA §1)
    hashed_password: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    nickname: str = Field(sa_column=Column(String(50), nullable=False))
    profile_image: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    is_admin: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    is_email_verified: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("false")),
    )
    email_verified_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class OAuthAccount(SQLModel, table=True):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_id",
            name="uq_oauth_accounts_provider_provider_id",
        ),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    user_id: uuid.UUID = Field(sa_column=_fk_user_column())
    provider: str = Field(sa_column=Column(String(20), nullable=False))  # 'google'|'kakao'
    provider_id: str = Field(sa_column=Column(String(255), nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        # 회전/재사용 탐지 시 user_id로 세션 전체 revoke (M1 C4). Postgres는
        # FK에 인덱스를 자동 생성하지 않으므로 명시 (DB_SCHEMA §6)
        Index("idx_refresh_tokens_user_id", "user_id"),
        # 갱신/로그인의 WHERE token_hash=? 직접 조회 인덱스 + 회전 불변식 방어선
        # (한 토큰에서 새 토큰 2개 발급 차단). 결정적 해시 + 고엔트로피라 UNIQUE 가능 (M1 I1)
        Index("uq_refresh_tokens_token_hash", "token_hash", unique=True),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    user_id: uuid.UUID = Field(sa_column=_fk_user_column())
    # 원문 토큰 저장 금지 - HMAC-SHA256(+TOKEN_PEPPER) 해시만 (DB_SCHEMA §1, M1 B2)
    token_hash: str = Field(sa_column=Column(String(255), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    # 토큰 체인의 최초 발급 시각. 회전돼도 부모 값을 승계(불변)해 절대 수명 cap의
    # 기준점이 된다 (M1 A). 앱이 create_refresh_token에서 항상 명시 설정하므로
    # server_default 없음(회전 토큰의 발급 시각은 now가 아니라 부모값이라 DB 기본값은 부적절).
    original_issued_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime | None = Field(default=None, sa_column=_created_at_column())
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class EmailVerification(SQLModel, table=True):
    __tablename__ = "email_verifications"
    __table_args__ = (
        # 검증(M1 E2)은 WHERE token=HMAC해시 직접 조회 - 인덱스 필수.
        # 결정적 해시 + 고엔트로피 랜덤이라 충돌이 없어 UNIQUE 가능(중복 방지 겸용)
        Index("uq_email_verifications_token", "token", unique=True),
        # 재발송/무효화(M1 E3)의 WHERE user_id=? AND used_at IS NULL 조회용.
        # Postgres는 FK에 인덱스를 자동 생성하지 않으므로 명시 (DB_SCHEMA §6, council I2)
        Index("idx_email_verifications_user_id", "user_id"),
    )

    id: uuid.UUID | None = Field(default=None, sa_column=_pk_column())
    user_id: uuid.UUID = Field(sa_column=_fk_user_column())
    # 컬럼명은 token이나 저장값은 해시 (HMAC-SHA256+pepper). 원문은 메일 링크에만 (M1 E1)
    token: str = Field(sa_column=Column(String(255), nullable=False))
    # 발급 후 1시간 (DB_SCHEMA §1)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class UserRead(SQLModel):
    """외부 응답 전용 스키마. 민감 필드(hashed_password 등) 제외 (M1 C5 /auth/me)."""

    id: uuid.UUID
    email: str
    nickname: str
    profile_image: str | None
    is_email_verified: bool
    is_admin: bool
    created_at: datetime
