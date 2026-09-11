"""Restrict the bootstrap Worker to schema metadata without changing business rows."""

from alembic import op

revision = "0002_worker_metadata_only"
down_revision = "0001_identity_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("REVOKE SELECT ON identity_account, workspace, workspace_membership FROM eid_worker")


def downgrade():
    raise RuntimeError("Worker privilege hardening is forward-only; do not restore excess grants")
