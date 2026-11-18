"""Add confhub columns: join_code, join_passcode, join_mode, display_name_override,
   platform_credentials table, rename bot_display_name.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename bot_display_name -> display_name_override
    with op.batch_alter_table("meetings") as batch_op:
        batch_op.alter_column(
            "bot_display_name",
            new_column_name="display_name_override",
            existing_type=sa.String(160),
            existing_nullable=False,
        )
        # Add new columns
        batch_op.add_column(sa.Column("join_code", sa.String(200), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("join_passcode", sa.String(100), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("join_mode", sa.String(20), nullable=False, server_default="as_user"))

    # Create platform_credentials table
    op.create_table(
        "platform_credentials",
        sa.Column("credential_id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("user_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("platform", sa.String(40), nullable=False, index=True),
        sa.Column("token_data", sa.Text, nullable=False, server_default=""),
        sa.Column("scopes", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_credentials")

    with op.batch_alter_table("meetings") as batch_op:
        batch_op.drop_column("join_mode")
        batch_op.drop_column("join_passcode")
        batch_op.drop_column("join_code")
        batch_op.alter_column(
            "display_name_override",
            new_column_name="bot_display_name",
            existing_type=sa.String(160),
            existing_nullable=False,
        )
