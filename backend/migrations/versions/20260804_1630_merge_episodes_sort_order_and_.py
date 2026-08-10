"""merge episodes_sort_order and commission heads

Revision ID: 119aecacde5e
Revises: 7f25d827c9ab, a7c91d05e3b4
Create Date: 2026-08-04 16:30:24.865972+00:00

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "119aecacde5e"
down_revision: str | Sequence[str] | None = ("7f25d827c9ab", "a7c91d05e3b4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
