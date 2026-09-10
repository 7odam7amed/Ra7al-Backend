"""Remove otp_verifications table and is_phone_verified column.

Revision ID: 013_remove_otp_verification
Revises: 012_user_status_approval
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "013_remove_otp_verification"
down_revision: Union[str, None] = "012_user_status_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.drop_table("otp_verifications")
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("is_phone_verified")
        return

    # 1. Drop otp_verifications table if present
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "otp_verifications" in tables:
        op.drop_table("otp_verifications")

    # 2. Drop is_phone_verified column from users table if present
    columns = [c["name"] for c in inspector.get_columns("users")]
    if "is_phone_verified" in columns:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("is_phone_verified")


def downgrade() -> None:
    # 1. Re-add is_phone_verified to users
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_phone_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )

    # 2. Re-create otp_verifications table
    op.create_table(
        "otp_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("otp_hash", sa.String(length=255), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_otp_verifications_user_id"), "otp_verifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_otp_verifications_phone_number"), "otp_verifications", ["phone_number"], unique=False)
