"""Remove unused API read privileges from append-only authorization records."""
from alembic import op

revision = "0006_api_write_only"
down_revision = "0005_delegation_epoch"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("REVOKE SELECT ON access_audit,access_invalidation,access_delegation FROM eid_api")


def downgrade():
    raise RuntimeError("Local access migrations are forward-only; preserve existing data")
