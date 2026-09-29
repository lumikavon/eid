"""Versioned, fail-closed generation policy and fenced runs; no model content in audit."""
from alembic import op

revision = '0022_model_governance'
down_revision = '0021_epic3_remediation'
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
CREATE TABLE model_policy_version (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 version integer NOT NULL CHECK (version>0), created_by uuid NOT NULL REFERENCES identity_account(id),
 provider text NOT NULL CHECK (provider IN ('internal','external')),
 model_id text NOT NULL CHECK (length(model_id) BETWEEN 1 AND 128),
 prompt_ref text NOT NULL CHECK (length(prompt_ref) BETWEEN 1 AND 128),
 prompt_sha256 text NOT NULL CHECK (prompt_sha256 ~ '^[0-9a-f]{{64}}$'),
 capabilities jsonb NOT NULL CHECK (jsonb_typeof(capabilities)='array'),
 max_classification smallint NOT NULL CHECK (max_classification BETWEEN 0 AND 3),
 max_context_chars integer NOT NULL CHECK (max_context_chars BETWEEN 1 AND 32000),
 max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 4096),
 daily_token_budget integer NOT NULL CHECK (daily_token_budget BETWEEN 1 AND 10000000),
 max_cost_micros integer NOT NULL CHECK (max_cost_micros BETWEEN 1 AND 100000000),
 timeout_seconds integer NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 30),
 redact_rules jsonb NOT NULL CHECK (jsonb_typeof(redact_rules)='array'),
 external_l2_exception boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,version), UNIQUE(workspace_id,id),
 CHECK (provider='internal' OR max_classification<=2),
 CHECK (provider='internal' OR NOT external_l2_exception OR max_classification=2)
);
CREATE FUNCTION eid_model_policy_immutable() RETURNS trigger LANGUAGE plpgsql AS $plpgsql$
BEGIN RAISE EXCEPTION 'Model policy versions are immutable'; END; $plpgsql$;
CREATE TRIGGER model_policy_immutable BEFORE UPDATE OR DELETE ON model_policy_version
 FOR EACH ROW EXECUTE FUNCTION eid_model_policy_immutable();
CREATE TABLE model_policy_active (
 workspace_id uuid PRIMARY KEY REFERENCES access_workspace(workspace_id),
 version_id uuid, FOREIGN KEY(workspace_id,version_id) REFERENCES model_policy_version(workspace_id,id),
 revision bigint NOT NULL DEFAULT 0 CHECK (revision>=0)
);
CREATE TABLE model_generation_run (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 document_id uuid NOT NULL REFERENCES document(id), actor_id uuid NOT NULL REFERENCES identity_account(id),
 subject text NOT NULL, request_key uuid NOT NULL, policy_version_id uuid NOT NULL,
 FOREIGN KEY(workspace_id,policy_version_id) REFERENCES model_policy_version(workspace_id,id),
 document_version_id uuid NOT NULL, document_revision bigint NOT NULL,
 policy_epoch jsonb NOT NULL, policy_revision bigint NOT NULL CHECK (policy_revision>=0),
 capability text NOT NULL,
 input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{{64}}$'),
 safe_input_sha256 text NOT NULL CHECK (safe_input_sha256 ~ '^[0-9a-f]{{64}}$'),
 input_char_count integer NOT NULL CHECK (input_char_count BETWEEN 1 AND 32000),
 reserved_tokens integer NOT NULL CHECK (reserved_tokens BETWEEN 1 AND 100000000),
 safe_input text CHECK (safe_input IS NULL OR length(safe_input) BETWEEN 1 AND 32000),
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED','FAILED')),
 stage text NOT NULL DEFAULT 'waiting', attempt smallint NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3),
 repair_count smallint NOT NULL DEFAULT 0 CHECK (repair_count BETWEEN 0 AND 1),
 fence uuid, lease_until timestamptz, next_retry_at timestamptz,
 next_wake_at timestamptz NOT NULL DEFAULT clock_timestamp(), error_code text,
 route text NOT NULL CHECK (route IN ('internal','external')),
 output jsonb, output_sha256 text, usage jsonb NOT NULL DEFAULT '{{}}'::jsonb,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,actor_id,request_key), UNIQUE(workspace_id,id)
);
CREATE INDEX model_generation_pending ON model_generation_run(state,next_wake_at,lease_until);
CREATE INDEX model_generation_daily_budget ON model_generation_run(workspace_id,created_at);
-- Identifier-only scheduler view. The worker cannot read prompts, policy or run rows.
CREATE FUNCTION eid_model_pending_v1() RETURNS TABLE(workspace_id uuid,document_id uuid,run_id uuid)
 LANGUAGE sql {security} AS $pending$
 SELECT r.workspace_id,r.document_id,r.id FROM model_generation_run r
 WHERE session_user='eid_worker' AND r.next_wake_at<=clock_timestamp() AND
 ((r.attempt<3 AND (r.state='QUEUED' OR (r.state='RETRY_WAIT' AND r.next_retry_at<=clock_timestamp())))
 OR (r.state='RUNNING' AND r.lease_until<clock_timestamp()))
 ORDER BY r.created_at,r.id LIMIT 32;
 $pending$;
REVOKE ALL ON FUNCTION eid_model_pending_v1() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_model_pending_v1() TO eid_worker;
REVOKE ALL ON model_policy_version,model_policy_active,model_generation_run FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON model_policy_version TO eid_api;
GRANT SELECT,INSERT ON model_policy_active TO eid_api;
GRANT UPDATE(version_id,revision) ON model_policy_active TO eid_api;
GRANT SELECT,INSERT ON model_generation_run TO eid_api;
GRANT UPDATE(state,stage,attempt,repair_count,fence,lease_until,next_retry_at,next_wake_at,error_code,output,output_sha256,usage,safe_input,updated_at) ON model_generation_run TO eid_api;
-- Worker receives identifiers only; no grant on policy, run payload, audit, ACL or document head.
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve model governance and generation provenance')
