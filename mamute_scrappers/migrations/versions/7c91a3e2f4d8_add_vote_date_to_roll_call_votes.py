"""add vote_date column to roll_call_votes

Revision ID: 7c91a3e2f4d8
Revises: df2d3f4c8a56
Create Date: 2026-06-02 04:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7c91a3e2f4d8"
down_revision: Union[str, None] = "df2d3f4c8a56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "roll_call_votes",
        sa.Column("vote_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_roll_call_votes_vote_date",
        "roll_call_votes",
        ["vote_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_roll_call_votes_vote_date", table_name="roll_call_votes")
    op.drop_column("roll_call_votes", "vote_date")
