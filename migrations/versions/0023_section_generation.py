"""Persist section proposals separately from immutable document versions."""
from alembic import op

revision = '0023_section_generation'
down_revision = '0022_model_governance'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    schema = op.get_bind().exec_driver_sql('SELECT current_schema()').scalar_one()
    security = 'SECURITY DEFINER SET search_path = pg_catalog, "' + schema.replace('"', '""') + '", pg_temp'
    op.execute(f"""
CREATE TABLE section_generation_job (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, section_id uuid NOT NULL,
 outline_version_id uuid NOT NULL, context_version_id uuid NOT NULL,
 document_version_id uuid NOT NULL, document_revision bigint NOT NULL,
 pack_job_id uuid NOT NULL REFERENCES section_evidence_job(id), pack_id uuid NOT NULL REFERENCES section_evidence_pack(id),
 pack_hash text NOT NULL, policy_version_id uuid NOT NULL,
 FOREIGN KEY(workspace_id,policy_version_id) REFERENCES model_policy_version(workspace_id,id),
 policy_revision bigint NOT NULL, policy_epoch jsonb NOT NULL,
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED_BY_MISSING_INFO','BLOCKED','CONFLICT','CANCELLED','FAILED')),
 stage text NOT NULL DEFAULT 'waiting', attempt smallint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3),
 reserved_tokens integer NOT NULL DEFAULT 0 CHECK (reserved_tokens BETWEEN 0 AND 100000000),
 fence uuid, lease_until timestamptz, next_retry_at timestamptz, next_wake_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 error_code text, missing jsonb NOT NULL DEFAULT '[]'::jsonb, proposal jsonb, proposal_hash text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id)
);
CREATE INDEX section_generation_pending ON section_generation_job(state,next_wake_at,lease_until);
CREATE FUNCTION eid_section_generation_pending_v1() RETURNS TABLE(workspace_id uuid,document_id uuid,run_id uuid)
 LANGUAGE sql {security} AS $pending$
 SELECT j.workspace_id,j.document_id,j.id FROM section_generation_job j
 WHERE session_user='eid_worker' AND j.next_wake_at<=clock_timestamp() AND j.attempt<3
 AND (j.state='QUEUED' OR (j.state='RETRY_WAIT' AND j.next_retry_at<=clock_timestamp())
 OR (j.state='RUNNING' AND j.lease_until<clock_timestamp()))
 ORDER BY j.created_at,j.id LIMIT 32;
 $pending$;
REVOKE ALL ON FUNCTION eid_section_generation_pending_v1() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_section_generation_pending_v1() TO eid_worker;
REVOKE ALL ON section_generation_job FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON section_generation_job TO eid_api;
GRANT UPDATE(state,stage,attempt,reserved_tokens,fence,lease_until,next_retry_at,next_wake_at,error_code,missing,proposal,proposal_hash,updated_at) ON section_generation_job TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve section proposals and provenance')
