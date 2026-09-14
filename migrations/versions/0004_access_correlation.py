"""Correlate new permission audits and restricted delegations without inventing historical traces."""
from alembic import op

revision = "0004_access_correlation"
down_revision = "0003_current_access"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE access_audit ADD COLUMN trace_id text")
    op.execute("ALTER TABLE access_delegation ADD COLUMN request_id text, ADD COLUMN trace_id text")


def downgrade():
    raise RuntimeError("Local access migrations are forward-only; preserve historical audits")
