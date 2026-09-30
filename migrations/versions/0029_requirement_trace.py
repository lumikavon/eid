"""保存双向版本化需求测试链接。"""
from alembic import op

revision = '0029_requirement_trace'
down_revision = '0028_review_dispositions'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute('''CREATE TABLE requirement_trace (
        workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
        document_id uuid NOT NULL REFERENCES document(id), version_id uuid NOT NULL REFERENCES document_version(id),
        section_id uuid NOT NULL, block_id uuid NOT NULL,
        target_document_id uuid NOT NULL REFERENCES document(id),
        target_version_id uuid NOT NULL REFERENCES document_version(id),
        target_section_id uuid NOT NULL, target_block_id uuid NOT NULL,
        PRIMARY KEY(version_id,block_id,target_version_id,target_block_id));
        CREATE INDEX requirement_trace_reverse ON requirement_trace(workspace_id,target_document_id,target_block_id);
        REVOKE ALL ON requirement_trace FROM PUBLIC,eid_api,eid_worker;
        GRANT SELECT,INSERT ON requirement_trace TO eid_api;''')


def downgrade():
    raise RuntimeError('Forward-only: preserve trace history')
