"""Initial schema: cars, rentals, and the transactional outbox

Revision ID: 0001
Revises:
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "AVAILABLE",
                "IN_USE",
                "UNDER_MAINTENANCE",
                name="carstatus",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        # Soft delete: rentals are audit history that reference this row,
        # so a car is retired rather than removed.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # One index for the only shape car queries take: live rows, optionally
    # narrowed by status, ordered by id. The trailing id serves the ORDER BY
    # without a sort and makes the status count an index-only scan.
    op.create_index(
        "ix_cars_live_status",
        "cars",
        ["status", "id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "rentals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        # NULL means the rental is ongoing — the partial unique index below
        # keys on exactly this.
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # RESTRICT, not CASCADE: the database refuses to drop a car that has
        # rental history.
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_rentals_end_after_start",
        ),
    )
    op.create_index("ix_rentals_car_id", "rentals", ["car_id"])

    # The double-booking guard. Partial, so a car may be rented any number of
    # times in sequence but only once at a time — the invariant becomes
    # unrepresentable rather than merely checked.
    op.create_index(
        "uq_one_active_rental_per_car",
        "rentals",
        ["car_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PUBLISHED",
                "FAILED",
                name="outboxstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    # The relay polls "pending, oldest first" every tick. Partial, so the
    # index stays small once the table holds millions of published rows.
    op.create_index(
        "ix_outbox_pending",
        "outbox_events",
        ["id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    # Consumer-side idempotency ledger. The composite key is what makes
    # reprocessing a redelivered event a no-op.
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=32), primary_key=True),
        sa.Column("consumer", sa.String(length=64), primary_key=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_pending", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("uq_one_active_rental_per_car", table_name="rentals")
    op.drop_index("ix_rentals_car_id", table_name="rentals")
    op.drop_table("rentals")
    op.drop_index("ix_cars_live_status", table_name="cars")
    op.drop_table("cars")
