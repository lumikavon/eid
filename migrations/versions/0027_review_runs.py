"""Persist version-pinned review runs and findings without granting worker table access."""
from alembic import op

revision = '0027_review_runs'
down_revision = '0026_pending_graphics'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE review_run (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, document_version_id uuid NOT NULL REFERENCES document_version(id),
 document_revision bigint NOT NULL, content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  template_version_id uuid NOT NULL REFERENCES template_version(id), rule_version text NOT NULL,
   template_hash text NOT NULL CHECK (template_hash ~ '^[0-9a-f]{64}$'),
   input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
 model_version text NOT NULL, policy_epoch jsonb NOT NULL,
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','COMPLETED','FAILED','STALE','DENIED')),
  attempt smallint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3), fence uuid, lease_until timestamptz,
  next_wake_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 error_code text, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id)
);
CREATE TABLE review_result (
 run_id uuid NOT NULL REFERENCES review_run(id), category text NOT NULL CHECK (category IN
 ('structure','fact','requirement','technical','quality','consistency','style','safety')),
 state text NOT NULL CHECK (state IN ('COMPLETED','FAILED','UNEVALUATED')),
 rule_version text NOT NULL, model_version text NOT NULL, execution_kind text NOT NULL
 CHECK (execution_kind IN ('deterministic','model_double','unavailable')),
 error_code text, PRIMARY KEY(run_id,category)
);
CREATE TABLE review_issue (
 id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES review_run(id),
 category text NOT NULL, rule_id text NOT NULL, severity text NOT NULL CHECK (severity IN ('critical','high','medium','low')),
 section_id uuid, block_id uuid, claim_id uuid, source_id text, quote text NOT NULL,
 impact text NOT NULL, suggestion text NOT NULL, details jsonb NOT NULL DEFAULT '{}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX review_run_document_history ON review_run(workspace_id,document_id,created_at DESC);
CREATE INDEX review_run_pending ON review_run(state,next_wake_at,lease_until);
CREATE INDEX review_issue_run ON review_issue(run_id);
REVOKE ALL ON review_run,review_result,review_issue FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON review_run,review_result,review_issue TO eid_api;
GRANT UPDATE(state,attempt,fence,lease_until,next_wake_at,error_code,updated_at) ON review_run TO eid_api;
""")
    schema = op.get_bind().exec_driver_sql('SELECT current_schema()').scalar_one()
    security = 'SECURITY DEFINER SET search_path = pg_catalog, "' + schema.replace('"', '""') + '", pg_temp'
    op.execute(f"""
CREATE FUNCTION eid_review_pending_v1() RETURNS TABLE(workspace_id uuid,document_id uuid,run_id uuid)
 LANGUAGE sql {security} AS $pending$
 SELECT r.workspace_id,r.document_id,r.id FROM review_run r
  WHERE session_user='eid_worker' AND r.next_wake_at<=clock_timestamp()
  AND (r.state='QUEUED' OR (r.state='RUNNING' AND r.lease_until<clock_timestamp()))
 ORDER BY r.created_at,r.id LIMIT 32;
 $pending$;
REVOKE ALL ON FUNCTION eid_review_pending_v1() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_review_pending_v1() TO eid_worker;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve review history')
