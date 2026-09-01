"""Add is_phone_verified to users and create otp_verifications table.

Revision ID: 011_otp_verification
Revises: 010_auth_phone_number
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_otp_verification"
down_revision: Union[str, None] = "010_auth_phone_number"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_phone_verified to users table with default False, backfilling existing users to True
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("is_phone_verified", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )

    # Existing active users prior to OTP flow rollout are considered verified
    op.execute("UPDATE users SET is_phone_verified = true WHERE is_active = true")

    # 2. Create otp_verifications table
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


def downgrade() -> None:
    op.drop_index(op.f("ix_otp_verifications_phone_number"), table_name="otp_verifications")
    op.drop_index(op.f("ix_otp_verifications_user_id"), table_name="otp_verifications")
    op.drop_table("otp_verifications")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_phone_verified")
