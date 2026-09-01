"""Change user authentication from email to phone_number.

Revision ID: 010_auth_phone_number
Revises: 009_subscriptions_boarding
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_auth_phone_number"
down_revision: Union[str, None] = "009_subscriptions_boarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Backfill any existing users that have NULL phone_number to ensure non-null constraint succeeds
    op.execute(
        "UPDATE users SET phone_number = 'UNKNOWN_' || id WHERE phone_number IS NULL"
    )

    # 2. Alter users table: drop email and make phone_number required and unique
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_email"))
        batch_op.drop_column("email")
        batch_op.alter_column(
            "phone_number",
            existing_type=sa.String(length=20),
            type_=sa.String(length=20),
            nullable=False,
        )
        batch_op.create_index(
            op.f("ix_users_phone_number"), ["phone_number"], unique=True
        )


def downgrade() -> None:
    # Revert users table: drop unique phone_number, add email column and index
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_phone_number"))
        batch_op.alter_column(
            "phone_number",
            existing_type=sa.String(length=20),
            type_=sa.String(length=20),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("email", sa.String(length=255), nullable=True)
        )

    # Backfill placeholder email if any records exist
    op.execute(
        "UPDATE users SET email = 'user_' || id || '@restored.local' WHERE email IS NULL"
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=255),
            type_=sa.String(length=255),
            nullable=False,
        )
        batch_op.create_index(
            op.f("ix_users_email"), ["email"], unique=True
        )
