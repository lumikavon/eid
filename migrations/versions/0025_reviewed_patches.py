"""Persist an author's selected AI patch decision and its exact provenance."""
from alembic import op

revision = '0025_reviewed_patches'
down_revision = '0024_copilot_run'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE ai_patch_decision (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, action text NOT NULL CHECK (action IN ('accept','reject')),
 base_version_id uuid NOT NULL REFERENCES document_version(id), base_revision bigint NOT NULL,
 run_ids uuid[] NOT NULL, provenance jsonb NOT NULL, result_version_id uuid REFERENCES document_version(id),
 result_revision bigint, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id),
 CHECK (cardinality(run_ids) BETWEEN 1 AND 12),
 CHECK ((action='reject' AND result_version_id IS NULL AND result_revision IS NULL)
     OR (action='accept' AND result_version_id IS NOT NULL AND result_revision IS NOT NULL))
);
CREATE INDEX ai_patch_decision_accepted_runs ON ai_patch_decision USING gin(run_ids) WHERE action='accept';
CREATE FUNCTION eid_ai_patch_decision_immutable() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN RAISE EXCEPTION 'AI decisions are immutable'; END; $body$;
CREATE TRIGGER ai_patch_decision_immutable BEFORE UPDATE OR DELETE ON ai_patch_decision
 FOR EACH ROW EXECUTE FUNCTION eid_ai_patch_decision_immutable();
REVOKE ALL ON ai_patch_decision FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON ai_patch_decision TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve AI decisions and provenance')
