"""Drop the unused outbox aggregate index; merge the two cars indexes

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # aggregate_type/aggregate_id are written on insert and copied into
    # the published envelope, but no query filters on them, so this index
    # only cost write throughput. Reinstate it if per-aggregate event
    # history becomes a read path.
    op.drop_index("ix_outbox_aggregate", table_name="outbox_events")

    # Replaced by one partial index matching the query the application
    # actually issues: live cars, optionally narrowed by status, ordered
    # by id. Neither of these was selective enough to be chosen on its
    # own, and neither covered the deleted_at predicate every read carries.
    op.drop_index("ix_cars_status", table_name="cars")
    op.drop_index("ix_cars_deleted_at", table_name="cars")
    op.create_index(
        "ix_cars_live_status",
        "cars",
        ["status", "id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_cars_live_status", table_name="cars")
    op.create_index("ix_cars_deleted_at", "cars", ["deleted_at"])
    op.create_index("ix_cars_status", "cars", ["status"])
    op.create_index("ix_outbox_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])
