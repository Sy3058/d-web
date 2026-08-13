"""SQLModel 모델 패키지.

모든 `table=True` 모델을 여기서 import해 `SQLModel.metadata`에 등록한다.
Alembic env.py가 이 패키지를 import하면 전체 테이블 메타데이터를 인식한다.
"""

from .commission import CommissionItem, SiteText, SiteTextKey, SiteTextSlotKey
from .user import (
    EmailVerification,
    OAuthAccount,
    RefreshToken,
    RoleEnum,
    User,
    UserRead,
)
from .viewer import ViewerProgress
from .work import (
    Episode,
    Tag,
    Work,
    WorkStatus,
    WorkTag,
)

__all__ = [
    "User",
    "OAuthAccount",
    "RefreshToken",
    "EmailVerification",
    "UserRead",
    "RoleEnum",
    "Work",
    "Tag",
    "WorkTag",
    "Episode",
    "WorkStatus",
    "ViewerProgress",
    "CommissionItem",
    "SiteText",
    "SiteTextKey",
    "SiteTextSlotKey",
]
