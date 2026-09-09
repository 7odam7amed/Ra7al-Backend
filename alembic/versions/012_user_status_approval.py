"""Add status and rejection_reason to users table for CEO approval workflow.

Revision ID: 012_user_status_approval
Revises: 011_otp_verification
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012_user_status_approval"
down_revision: Union[str, None] = "011_otp_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add status and rejection_reason to users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="PENDING",
            )
        )
        batch_op.add_column(
            sa.Column(
                "rejection_reason",
                sa.String(length=500),
                nullable=True,
            )
        )
        batch_op.create_index(
            op.f("ix_users_status"), ["status"], unique=False
        )

    # 2. Backfill existing users sensibly:
    users = sa.table(
        "users",
        sa.column("status", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_phone_verified", sa.Boolean),
        sa.column("role", sa.String),
    )
    # Existing active users should remain ACTIVE so their ability to log in is preserved
    op.execute(users.update().where(users.c.is_active == True).values(status="ACTIVE"))
    # Existing deactivated users become INACTIVE
    op.execute(users.update().where(users.c.is_active == False).values(status="INACTIVE"))
    # Unverified students become PENDING
    op.execute(
        users.update()
        .where(sa.and_(users.c.is_phone_verified == False, users.c.role == "STUDENT"))
        .values(status="PENDING")
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_status"))
        batch_op.drop_column("rejection_reason")
        batch_op.drop_column("status")
