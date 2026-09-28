"""Immutable section evidence and fenced, bounded build attempts."""
from alembic import op

revision = '0019_section_evidence'
down_revision = '0018_source_governance'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE section_evidence_job (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 actor_id uuid NOT NULL, subject text NOT NULL, section_id uuid NOT NULL,
 outline_version_id uuid NOT NULL, context_version_id uuid NOT NULL,
 document_version_id uuid NOT NULL, document_revision bigint NOT NULL,
 policy_epoch jsonb NOT NULL, request_key uuid NOT NULL,
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED')),
 stage text NOT NULL DEFAULT 'waiting' CHECK (stage IN ('waiting','planning','retrieving','verifying','retry_wait','done','blocked','failed')),
 attempt integer NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3), fence uuid,
 lease_until timestamptz, next_retry_at timestamptz, error_code text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id)
);
CREATE INDEX section_evidence_pending ON section_evidence_job(state,next_retry_at,lease_until);
CREATE TABLE section_evidence_pack (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, job_id uuid NOT NULL UNIQUE,
 document_id uuid NOT NULL, section_id uuid NOT NULL, outline_version_id uuid NOT NULL,
 context_version_id uuid NOT NULL, document_version_id uuid NOT NULL,
 content jsonb NOT NULL, content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,job_id) REFERENCES section_evidence_job(workspace_id,id),
 UNIQUE(workspace_id,id)
);
CREATE TABLE section_evidence_query (
 pack_id uuid NOT NULL REFERENCES section_evidence_pack(id), ordinal smallint NOT NULL CHECK (ordinal BETWEEN 1 AND 10),
 query text NOT NULL CHECK (length(query) BETWEEN 2 AND 128), PRIMARY KEY(pack_id,ordinal)
);
CREATE TABLE section_evidence_item (
 pack_id uuid NOT NULL REFERENCES section_evidence_pack(id), ordinal smallint NOT NULL CHECK (ordinal BETWEEN 1 AND 30),
 chain text NOT NULL CHECK (chain IN ('attachment','enterprise')),
 source_id text NOT NULL, version text NOT NULL, chunk_hash text NOT NULL, locator text NOT NULL,
 excerpt text NOT NULL CHECK (length(excerpt) BETWEEN 1 AND 4000),
 scores jsonb NOT NULL, provenance jsonb NOT NULL,
 PRIMARY KEY(pack_id,ordinal)
);
REVOKE ALL ON section_evidence_job,section_evidence_pack,section_evidence_query,section_evidence_item FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON section_evidence_job TO eid_api;
GRANT UPDATE(state,stage,attempt,fence,lease_until,next_retry_at,error_code,updated_at) ON section_evidence_job TO eid_api;
GRANT SELECT,INSERT ON section_evidence_pack,section_evidence_query,section_evidence_item TO eid_api;
-- Worker has no authority to inspect stored excerpts or fabricate a Pack.
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve evidence provenance')
