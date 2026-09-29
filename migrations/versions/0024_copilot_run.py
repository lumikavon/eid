"""Bind Copilot operations to a durable, authorized model run."""
from alembic import op

revision = '0024_copilot_run'
down_revision = '0023_section_generation'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE copilot_run (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, model_run_id uuid NOT NULL,
 FOREIGN KEY(workspace_id,model_run_id) REFERENCES model_generation_run(workspace_id,id),
 document_version_id uuid NOT NULL, document_revision bigint NOT NULL,
 section_id uuid NOT NULL, block_id uuid, operation text NOT NULL,
 pack_job_id uuid NOT NULL REFERENCES section_evidence_job(id),
  pack_id uuid NOT NULL REFERENCES section_evidence_pack(id), pack_hash text NOT NULL,
  view_hash text NOT NULL CHECK (view_hash ~ '^[0-9a-f]{64}$'),
 target_hash text NOT NULL CHECK (target_hash ~ '^[0-9a-f]{64}$'),
 prompt_hash text NOT NULL CHECK (prompt_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id)
);
REVOKE ALL ON copilot_run FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON copilot_run TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve Copilot request provenance')
