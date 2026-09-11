"""Create only the Story 1.1 identity/workspace mapping.

Revision ID: 0001_identity_workspace
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_identity_workspace"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("GRANT SELECT ON alembic_version TO eid_api, eid_worker")
    op.create_table(
        "identity_account",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("subject", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("department", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "workspace",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
    )
    op.create_table(
        "workspace_membership",
        sa.Column("identity_id", sa.Uuid(), sa.ForeignKey("identity_account.id"), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspace.id"), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("GRANT SELECT ON identity_account, workspace, workspace_membership TO eid_api")
    op.execute("GRANT SELECT ON identity_account, workspace, workspace_membership TO eid_worker")
    op.execute(
        "INSERT INTO identity_account(id,subject,display_name,department) VALUES "
        "('11111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','本地项目成员','产品部')"
    )
    op.execute(
        "INSERT INTO workspace(id,slug,name) VALUES "
        "('22222222-2222-4222-8222-222222222222','eid-local','企业智能文档工作区')"
    )
    op.execute(
        "INSERT INTO workspace_membership(identity_id,workspace_id) VALUES "
        "('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222')"
    )


def downgrade():
    raise RuntimeError("Story 1.1 local migrations are forward-only; do not clean existing data")
