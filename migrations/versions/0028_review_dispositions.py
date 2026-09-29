"""Preserve version-pinned human finding decisions and recheck evidence."""
from alembic import op

revision = '0028_review_dispositions'
down_revision = '0027_review_runs'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE review_disposition (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), run_id uuid NOT NULL REFERENCES review_run(id),
 issue_id uuid NOT NULL REFERENCES review_issue(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
 action text NOT NULL CHECK (action IN ('accept','reject','modify','handled')),
 base_version_id uuid NOT NULL REFERENCES document_version(id), base_revision bigint NOT NULL,
 reason text, patch_decision_id uuid REFERENCES ai_patch_decision(id),
 result_version_id uuid REFERENCES document_version(id), result_revision bigint,
 recheck_run_id uuid REFERENCES review_run(id),
 section_id uuid, block_id uuid, policy_epoch jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key),
 CHECK (action<>'reject' OR coalesce(length(btrim(reason)),0)>0),
 CHECK ((action='accept' AND patch_decision_id IS NOT NULL AND result_version_id IS NOT NULL AND result_revision IS NOT NULL)
     OR (action<>'accept' AND patch_decision_id IS NULL AND result_version_id IS NULL AND result_revision IS NULL)),
 CHECK ((action='handled' AND recheck_run_id IS NOT NULL) OR (action<>'handled' AND recheck_run_id IS NULL)),
 CHECK (action<>'modify' OR (section_id IS NOT NULL AND block_id IS NOT NULL))
);
CREATE INDEX review_disposition_document ON review_disposition(workspace_id,document_id,run_id);
CREATE UNIQUE INDEX review_disposition_first ON review_disposition(issue_id) WHERE action<>'handled';
CREATE UNIQUE INDEX review_disposition_closed ON review_disposition(issue_id) WHERE action='handled';
CREATE FUNCTION eid_review_disposition_immutable() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN RAISE EXCEPTION 'Review dispositions are immutable'; END; $body$;
CREATE TRIGGER review_disposition_immutable BEFORE UPDATE OR DELETE ON review_disposition
 FOR EACH ROW EXECUTE FUNCTION eid_review_disposition_immutable();
REVOKE ALL ON review_disposition FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON review_disposition TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve review decisions and evidence')
