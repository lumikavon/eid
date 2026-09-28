"""Immutable source versions and conflict decisions; access is enforced by the API at use time."""
from alembic import op

revision = '0018_source_governance'
down_revision = '0017_authorized_retrieval'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE knowledge_assertion (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, chain text NOT NULL CHECK (chain IN ('attachment','enterprise')),
 source_id text NOT NULL CHECK (length(source_id) BETWEEN 1 AND 128),
 document_id uuid, version text NOT NULL CHECK (length(version) BETWEEN 1 AND 128),
 chunk_hash text NOT NULL CHECK (chunk_hash ~ '^[0-9a-f]{64}$'),
 locator text NOT NULL CHECK (length(locator) BETWEEN 1 AND 512),
 page integer, ordinal integer,
 authority smallint NOT NULL CHECK (authority BETWEEN 1 AND 8),
 -- Level 9 (LLM general knowledge) cannot be registered as formal evidence.
 classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 project_id text NOT NULL, product_id text, customer_id text,
 effective_from timestamptz NOT NULL, effective_until timestamptz,
 topic text NOT NULL CHECK (length(topic) BETWEEN 1 AND 256),
 statement text NOT NULL CHECK (length(statement) BETWEEN 1 AND 4000),
 value text NOT NULL CHECK (length(value) BETWEEN 1 AND 256),
 unit text NOT NULL DEFAULT '' CHECK (length(unit)<=64),
 conditions text NOT NULL DEFAULT '' CHECK (length(conditions)<=512),
 recorded_by uuid NOT NULL, recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (effective_until IS NULL OR effective_until>effective_from),
 CHECK ((chain='attachment' AND document_id IS NOT NULL AND page BETWEEN 1 AND 500 AND ordinal BETWEEN 1 AND 200)
     OR (chain='enterprise' AND document_id IS NULL AND page IS NULL AND ordinal IS NULL)),
 UNIQUE (workspace_id,chain,source_id,version,chunk_hash,locator,topic,conditions),
 UNIQUE (workspace_id,id)
);
CREATE INDEX knowledge_assertion_topic ON knowledge_assertion(workspace_id,project_id,topic);
CREATE TABLE knowledge_conflict (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, left_id uuid NOT NULL, right_id uuid NOT NULL,
 revision bigint NOT NULL DEFAULT 1 CHECK (revision>0), status text NOT NULL DEFAULT 'open'
 CHECK (status IN ('open','accepted_left','accepted_right','unresolved')),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (left_id<right_id),
 FOREIGN KEY(workspace_id,left_id) REFERENCES knowledge_assertion(workspace_id,id),
 FOREIGN KEY(workspace_id,right_id) REFERENCES knowledge_assertion(workspace_id,id),
 UNIQUE(workspace_id,left_id,right_id), UNIQUE(workspace_id,id)
);
CREATE TABLE knowledge_disposition (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, conflict_id uuid NOT NULL,
 revision bigint NOT NULL, status text NOT NULL CHECK (status IN ('accepted_left','accepted_right','unresolved')),
 reason text NOT NULL CHECK (length(btrim(reason)) BETWEEN 3 AND 2000),
 actor_id uuid NOT NULL, decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 left_id uuid NOT NULL, right_id uuid NOT NULL,
 FOREIGN KEY(workspace_id,conflict_id) REFERENCES knowledge_conflict(workspace_id,id),
 UNIQUE(workspace_id,conflict_id,revision)
);
-- Future Pack/Claim/Review writers register dependencies here; no fictional Pack is created by 3.3.
CREATE TABLE knowledge_dependency (
 workspace_id uuid NOT NULL, conflict_id uuid NOT NULL, kind text NOT NULL CHECK (kind IN ('pack','claim','review')),
 dependent_id uuid NOT NULL, needs_review boolean NOT NULL DEFAULT true,
 PRIMARY KEY(workspace_id,conflict_id,kind,dependent_id),
 FOREIGN KEY(workspace_id,conflict_id) REFERENCES knowledge_conflict(workspace_id,id)
);
REVOKE ALL ON knowledge_assertion,knowledge_conflict,knowledge_disposition,knowledge_dependency FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON knowledge_assertion TO eid_api;
GRANT SELECT,INSERT,UPDATE(revision,status,updated_at) ON knowledge_conflict TO eid_api;
GRANT SELECT,INSERT ON knowledge_disposition TO eid_api;
GRANT SELECT,INSERT,UPDATE(needs_review) ON knowledge_dependency TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve conflict and decision history')
