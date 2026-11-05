"""Initial Foundation Baseline

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-10-02 12:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Baseline migration placeholder for Phase 1 foundation.
    # Non-destructive baseline; business schema tables will be created in Phase 2.
    pass


def downgrade() -> None:
    # Downgrade baseline
    pass
