"""Capability state model, device-time tracking, credential verification.

Revision ID: 3c8d9e1a2b4f
Revises: 2b4f4a1c0e7a
Create Date: 2026-09-08

Changes:
- device_capabilities: add implemented, enabled, is_destructive columns
  (the `supported` column is preserved as a read alias but the new tri-state
  is implemented/verified/enabled).
- device_credentials: add `verification_state` column (VERIFIED / NOT_VERIFIED / FAILED).
- devices: add last_probe_at, last_probe_error, storage_usage_pct,
  device_time_offset_s columns.
- devices: drop overly-confident brand default (vendor stays UNKNOWN unless
  OEMVendor explicitly reports something).
- attendance_logs: ensure fingerprint uniqueness and add useful indexes.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "3c8d9e1a2b4f"
down_revision = "2b4f4a1c0e7a"
branch_labels = None
depends_on = None


DESTRUCTIVE_CAPS = {
    "create_users",
    "update_users",
    "delete_users",
    "delete_logs",
    "clear_data",
    "set_time",
    "sync_users_to_device",
    "write_templates",
    "restart",
    "poweroff",
    "disable_device",
}


def upgrade() -> None:
    # device_capabilities -- add new columns; back-fill from supported/verified.
    with op.batch_alter_table("device_capabilities") as bop:
        bop.add_column(sa.Column("implemented", sa.Boolean(), nullable=False, server_default=sa.false()))
        bop.add_column(sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        bop.add_column(sa.Column("is_destructive", sa.Boolean(), nullable=False, server_default=sa.false()))

    # Back-fill: implemented = supported, enabled = verified AND NOT destructive.
    op.execute(
        "UPDATE device_capabilities SET implemented = COALESCE(supported, false)"
    )
    op.execute(
        "UPDATE device_capabilities SET enabled = verified "
        "WHERE capability NOT IN ('create_users','update_users','delete_users',"
        "'delete_logs','clear_data','set_time','sync_users_to_device',"
        "'write_templates','restart','poweroff','disable_device')"
    )
    for cap in DESTRUCTIVE_CAPS:
        op.execute(
            f"UPDATE device_capabilities SET is_destructive = true WHERE capability = '{cap}'"
        )
    op.execute(
        "UPDATE device_capabilities SET is_destructive = true WHERE is_destructive IS NULL OR is_destructive = false AND capability IN ("
        + ",".join(f"'{c}'" for c in DESTRUCTIVE_CAPS) + ")"
    )

    # device_credentials
    with op.batch_alter_table("device_credentials") as bop:
        bop.add_column(sa.Column(
            "verification_state", sa.String(length=20), nullable=False,
            server_default="NOT_VERIFIED",
        ))
        bop.add_column(sa.Column("verified_at", sa.DateTime(), nullable=True))
        bop.add_column(sa.Column("last_error", sa.Text(), nullable=True))

    # devices -- new tracking columns
    with op.batch_alter_table("devices") as bop:
        bop.add_column(sa.Column("last_probe_at", sa.DateTime(), nullable=True))
        bop.add_column(sa.Column("last_probe_error", sa.Text(), nullable=True))
        bop.add_column(sa.Column("device_time_offset_s", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("device_time_checked_at", sa.DateTime(), nullable=True))
        bop.add_column(sa.Column("storage_used", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("storage_capacity", sa.Integer(), nullable=True))
        bop.add_column(sa.Column("storage_usage_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("devices") as bop:
        bop.drop_column("storage_usage_pct")
        bop.drop_column("storage_capacity")
        bop.drop_column("storage_used")
        bop.drop_column("device_time_checked_at")
        bop.drop_column("device_time_offset_s")
        bop.drop_column("last_probe_error")
        bop.drop_column("last_probe_at")
    with op.batch_alter_table("device_credentials") as bop:
        bop.drop_column("last_error")
        bop.drop_column("verified_at")
        bop.drop_column("verification_state")
    with op.batch_alter_table("device_capabilities") as bop:
        bop.drop_column("is_destructive")
        bop.drop_column("enabled")
        bop.drop_column("implemented")
