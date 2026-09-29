"""Version-pinned pending facts and immutable human disposition history."""
from alembic import op

revision = '0026_pending_graphics'
down_revision = '0025_reviewed_patches'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE ai_pending_fact (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), document_version_id uuid NOT NULL REFERENCES document_version(id),
 section_id uuid NOT NULL, block_id uuid NOT NULL, actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, copilot_run_id uuid NOT NULL, reason text NOT NULL CHECK(length(reason) BETWEEN 1 AND 4000),
 proposed_value text NOT NULL CHECK(length(proposed_value) BETWEEN 1 AND 4000),
 evidence jsonb NOT NULL, target_hash text NOT NULL CHECK (target_hash ~ '^[0-9a-f]{64}$'),
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed')),
 confirmed_value text, confirmed_by uuid REFERENCES identity_account(id), confirmed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,copilot_run_id) REFERENCES copilot_run(workspace_id,id),
 UNIQUE(workspace_id,copilot_run_id), UNIQUE(workspace_id,id),
 CHECK ((status='pending' AND confirmed_value IS NULL AND confirmed_by IS NULL AND confirmed_at IS NULL)
 OR (status='confirmed' AND confirmed_value IS NOT NULL AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL))
);
CREATE TABLE ai_pending_event (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, fact_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES identity_account(id), action text NOT NULL CHECK(action='confirm'),
 base_version_id uuid NOT NULL REFERENCES document_version(id), reason text NOT NULL CHECK(length(reason) BETWEEN 1 AND 1000),
 value_hash text NOT NULL CHECK(value_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,fact_id) REFERENCES ai_pending_fact(workspace_id,id), UNIQUE(workspace_id,fact_id)
);
CREATE FUNCTION eid_pending_event_immutable() RETURNS trigger LANGUAGE plpgsql AS $body$
BEGIN RAISE EXCEPTION 'Pending events are immutable'; END; $body$;
CREATE TRIGGER pending_event_immutable BEFORE UPDATE OR DELETE ON ai_pending_event
 FOR EACH ROW EXECUTE FUNCTION eid_pending_event_immutable();
REVOKE ALL ON ai_pending_fact,ai_pending_event FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON ai_pending_fact,ai_pending_event TO eid_api;
GRANT UPDATE(status,confirmed_value,confirmed_by,confirmed_at) ON ai_pending_fact TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve pending fact decisions')
