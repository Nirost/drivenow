"""Initial schema: cars and rentals

Revision ID: 0001
Revises:
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa

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
                "AVAILABLE", "IN_USE", "UNDER_MAINTENANCE",
                name="carstatus", native_enum=False, length=32,
            ),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cars_status", "cars", ["status"])
    op.create_index("ix_cars_deleted_at", "cars", ["deleted_at"])

    op.create_table(
        "rentals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "end_date IS NULL OR end_date >= start_date",
            name="ck_rentals_end_after_start",
        ),
    )
    op.create_index("ix_rentals_car_id", "rentals", ["car_id"])

    # Partial unique index: at most one ongoing rental per car.
    op.create_index(
        "uq_one_active_rental_per_car",
        "rentals",
        ["car_id"],
        unique=True,
        postgresql_where=sa.text("end_date IS NULL"),
        sqlite_where=sa.text("end_date IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_one_active_rental_per_car", table_name="rentals")
    op.drop_index("ix_rentals_car_id", table_name="rentals")
    op.drop_table("rentals")
    op.drop_index("ix_cars_deleted_at", table_name="cars")
    op.drop_index("ix_cars_status", table_name="cars")
    op.drop_table("cars")
