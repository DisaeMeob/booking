"""fix facilities and constraints

Revision ID: f8d80f8013d6
Revises: b05ef1b0ec39
Create Date: 2026-11-08 15:20:14.396508

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f8d80f8013d6"
down_revision: Union[str, Sequence[str], None] = "b05ef1b0ec39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DELETE FROM rooms_facilities
        WHERE id NOT IN (
            SELECT MIN(id) FROM rooms_facilities GROUP BY room_id, facility_id
        )
        """
    )
    op.execute(
        """
        DELETE FROM facilities
        WHERE id NOT IN (
            SELECT MIN(id) FROM facilities GROUP BY title
        )
        """
    )
    op.create_unique_constraint("uq_facilities_title", "facilities", ["title"])
    op.create_unique_constraint(
        "uq_rooms_facilities_room_id_facility_id",
        "rooms_facilities",
        ["room_id", "facility_id"],
    )
    op.drop_constraint(
        "rooms_facilities_room_id_fkey", "rooms_facilities", type_="foreignkey"
    )
    op.create_foreign_key(
        "rooms_facilities_room_id_fkey",
        "rooms_facilities",
        "rooms",
        ["room_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "rooms_facilities_facility_id_fkey", "rooms_facilities", type_="foreignkey"
    )
    op.create_foreign_key(
        "rooms_facilities_facility_id_fkey",
        "rooms_facilities",
        "facilities",
        ["facility_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "rooms_facilities_facility_id_fkey", "rooms_facilities", type_="foreignkey"
    )
    op.create_foreign_key(
        "rooms_facilities_facility_id_fkey",
        "rooms_facilities",
        "facilities",
        ["facility_id"],
        ["id"],
    )
    op.drop_constraint(
        "rooms_facilities_room_id_fkey", "rooms_facilities", type_="foreignkey"
    )
    op.create_foreign_key(
        "rooms_facilities_room_id_fkey",
        "rooms_facilities",
        "rooms",
        ["room_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_rooms_facilities_room_id_facility_id", "rooms_facilities", type_="unique"
    )
    op.drop_constraint("uq_facilities_title", "facilities", type_="unique")
