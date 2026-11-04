"""add rooms

Revision ID: f1e6baafcd7d
Revises: 0ca79263ec36
Create Date: 2026-03-10 15:03:44.815005

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1e6baafcd7d"
down_revision: Union[str, Sequence[str], None] = "0ca79263ec36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hotel_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotels.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
def downgrade() -> None:
    op.drop_table("rooms")
