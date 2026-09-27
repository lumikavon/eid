"""Forward-only development-template governance storage, without formal approval.

Revision ID: 0013_template_governance
"""

from alembic import op

revision = "0013_template_governance"
down_revision = "0012_domain_editor"
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(), shobj_description(oid,'pg_database') "
        "FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ("eid_local_dev", "eid-local-dev-v1"):
        raise RuntimeError("Story 2.4 migration requires the isolated EID development database")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    security = f"SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}, pg_temp"
    op.execute("""
-- 0010 already owns access_resource_observation_workspace_key UNIQUE(id,workspace_id).
ALTER TABLE template_version DROP CONSTRAINT template_version_fixture_owner_check;
ALTER TABLE template_version ALTER COLUMN fixture_owner DROP NOT NULL;
ALTER TABLE template_version ALTER COLUMN fixture_version DROP NOT NULL;
ALTER TABLE template_version ADD CONSTRAINT template_version_provenance_check CHECK (
 (fixture_owner IS NOT NULL AND fixture_owner='story-2.1' AND fixture_version IS NOT NULL)
 OR (fixture_owner IS NULL AND fixture_version IS NULL)
);
-- Keep development_only CHECK(development_only): no official font/theme/policy evidence exists.
ALTER TABLE template_version ADD CONSTRAINT template_version_id_template_unique
 UNIQUE(id,template_id);
CREATE TABLE template_governed_family (
 template_id uuid PRIMARY KEY REFERENCES template(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 resource_id uuid NOT NULL UNIQUE,
 created_by uuid NOT NULL REFERENCES identity_account(id),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(created_at)),
 FOREIGN KEY(resource_id,workspace_id) REFERENCES access_resource(id,workspace_id),
 UNIQUE(template_id,workspace_id)
);
CREATE INDEX template_governed_family_workspace ON template_governed_family(workspace_id,template_id);
CREATE TRIGGER template_governed_family_immutable BEFORE UPDATE OR DELETE ON template_governed_family
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
CREATE TABLE template_version_policy (
 version_id uuid PRIMARY KEY,
 template_id uuid NOT NULL REFERENCES template_governed_family(template_id),
 FOREIGN KEY(version_id,template_id) REFERENCES template_version(id,template_id),
 package_sha256 text NOT NULL CHECK (package_sha256 ~ '^[0-9a-f]{64}$'),
 manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
 validator_version text NOT NULL CHECK (length(validator_version) BETWEEN 1 AND 128),
 rule_refs jsonb NOT NULL CHECK (jsonb_typeof(rule_refs)='object'),
 sanitized_assets jsonb NOT NULL CHECK (jsonb_typeof(sanitized_assets)='array'),
 validated_at timestamptz NOT NULL CHECK (isfinite(validated_at)),
 published_by uuid NOT NULL REFERENCES identity_account(id),
 published_at timestamptz NOT NULL CHECK (isfinite(published_at)),
 CHECK (validated_at <= published_at)
);
CREATE TRIGGER template_version_policy_immutable BEFORE UPDATE OR DELETE ON template_version_policy
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
REVOKE ALL ON template_governed_family,template_version_policy FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON template_governed_family,template_version_policy TO eid_api;
GRANT INSERT ON template,template_version,template_version_state,template_workspace TO eid_api;
-- Existing document creation may insert access_resource; do not widen Worker privileges.
""")
    _candidate_storage(security)
    op.execute("""
CREATE FUNCTION eid_governed_version_policy_required() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.fixture_owner IS NULL AND NOT EXISTS (
  SELECT 1 FROM template_version_policy p
  WHERE p.version_id=NEW.id AND p.template_id=NEW.template_id
 ) THEN
  RAISE EXCEPTION 'Governed template requires immutable validation policy' USING ERRCODE='23514';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER template_governed_version_policy_commit
 AFTER INSERT ON template_version DEFERRABLE INITIALLY DEFERRED
 FOR EACH ROW EXECUTE FUNCTION eid_governed_version_policy_required();
REVOKE ALL ON FUNCTION eid_governed_version_policy_required() FROM PUBLIC,eid_api,eid_worker;
""")
    op.execute(f"""
CREATE FUNCTION eid_deprecate_template_version_v1(p_workspace uuid,p_version uuid,p_actor uuid)
 RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE family uuid;
BEGIN
 IF session_user<>'eid_api' OR p_actor IS NULL THEN RETURN FALSE; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=p_workspace FOR UPDATE;
 SELECT v.template_id INTO family FROM template_version v
 JOIN template_governed_family g ON g.template_id=v.template_id
 WHERE v.id=p_version AND g.workspace_id=p_workspace;
 IF family IS NULL OR NOT eid_template_family_allowed_v1(family,p_actor,p_workspace)
 THEN RETURN FALSE; END IF;
 -- The document create path locks template root before version state. Keep the same order.
 PERFORM 1 FROM template WHERE id=family FOR UPDATE;
 UPDATE template_version_state SET status='deprecated',updated_at=clock_timestamp()
 WHERE version_id=p_version AND status='active';
 RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION eid_deprecate_template_version_v1(uuid,uuid,uuid) FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_deprecate_template_version_v1(uuid,uuid,uuid) TO eid_api;
""")


def downgrade():
    raise RuntimeError("Story 2.4 migration is forward-only; preserve referenced template versions")


def _candidate_storage(security):
    op.execute("""
CREATE TABLE template_candidate (
 id uuid PRIMARY KEY, template_id uuid NOT NULL REFERENCES template_governed_family(template_id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 package_bytes bytea NOT NULL CHECK (octet_length(package_bytes) BETWEEN 1 AND 5242880),
 package_sha256 text NOT NULL CHECK (package_sha256 ~ '^[0-9a-f]{64}$'),
 version_label text NOT NULL CHECK (length(version_label) BETWEEN 1 AND 128),
 scope text NOT NULL CHECK (scope IN ('enterprise','department','product_line','project','personal')),
 target_scope_value text, classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 base_version_id uuid,
 FOREIGN KEY(base_version_id,template_id) REFERENCES template_version(id,template_id),
 FOREIGN KEY(template_id,workspace_id) REFERENCES template_governed_family(template_id,workspace_id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (isfinite(created_at)),
 CHECK ((scope IN ('department','product_line','project')) = (target_scope_value IS NOT NULL)),
 UNIQUE(id,template_id), UNIQUE(id,workspace_id)
 );
CREATE INDEX template_candidate_workspace_quota ON template_candidate(workspace_id);
CREATE TRIGGER template_candidate_immutable BEFORE UPDATE OR DELETE ON template_candidate
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
CREATE TABLE template_validation (
 candidate_id uuid PRIMARY KEY REFERENCES template_candidate(id),
 state text NOT NULL DEFAULT 'QUEUED' CHECK(state IN ('QUEUED','RUNNING','VALIDATED','REJECTED','BLOCKED')),
 lease_owner uuid, lease_until timestamptz, attempt integer NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 3),
 report jsonb, error_code text, updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK (report IS NULL OR (jsonb_typeof(report)='object' AND octet_length(report::text)<=12582912))
 );
CREATE INDEX template_validation_pending ON template_validation(state,lease_until,candidate_id);
CREATE TABLE template_governance_receipt (
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[0-9a-f]{64}$'),
 candidate_id uuid NOT NULL REFERENCES template_candidate(id),
 PRIMARY KEY(actor_id,workspace_id,idempotency_key)
 );
ALTER TABLE template_version_policy ADD COLUMN candidate_id uuid NOT NULL UNIQUE,
 ADD CONSTRAINT template_policy_candidate_family_fk FOREIGN KEY(candidate_id,template_id)
 REFERENCES template_candidate(id,template_id);
CREATE TABLE template_governance_action_receipt (
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 idempotency_key text NOT NULL CHECK(idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
 payload_hash text NOT NULL CHECK(payload_hash ~ '^[0-9a-f]{64}$'),
 version_id uuid NOT NULL REFERENCES template_version(id),
 PRIMARY KEY(actor_id,workspace_id,idempotency_key)
 );
REVOKE ALL ON template_candidate,template_validation,template_governance_receipt,
 template_governance_action_receipt FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON template_candidate,template_governance_receipt,
 template_governance_action_receipt TO eid_api;
GRANT SELECT ON template_validation TO eid_api;
CREATE FUNCTION eid_template_validation_enqueue() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN INSERT INTO template_validation(candidate_id) VALUES (NEW.id); RETURN NEW; END $$;
CREATE TRIGGER template_validation_enqueue AFTER INSERT ON template_candidate
 FOR EACH ROW EXECUTE FUNCTION eid_template_validation_enqueue();
GRANT INSERT(candidate_id) ON template_validation TO eid_api;
REVOKE ALL ON FUNCTION eid_template_validation_enqueue() FROM PUBLIC,eid_api,eid_worker;
""")
    op.execute(f"""
CREATE FUNCTION eid_template_family_allowed_v1(p_template uuid,p_actor uuid,p_workspace uuid)
 RETURNS boolean LANGUAGE sql VOLATILE {security} AS $$
 SELECT EXISTS (
 SELECT 1 FROM template_governed_family g
 JOIN access_resource r ON r.id=g.resource_id AND r.workspace_id=g.workspace_id
 JOIN access_current_facts f ON f.actor_id=p_actor AND f.workspace_id=g.workspace_id
 WHERE g.template_id=p_template AND g.workspace_id=p_workspace AND r.kind='template'
 AND f.identity_active AND f.membership_active
 AND 'template_admin'=ANY(f.roles)
 AND f.roles <@ ARRAY['author','expert','quality','template_admin','knowledge_admin','approver','system_admin']::text[]
 AND f.approval_states <@ ARRAY['draft','in_review','approved','rejected']::text[]
 AND f.valid_from<=clock_timestamp() AND (f.valid_until IS NULL OR f.valid_until>clock_timestamp())
 AND r.valid_from<=clock_timestamp() AND (r.valid_until IS NULL OR r.valid_until>clock_timestamp())
 AND r.approval_state=ANY(f.approval_states)
 AND (f.owner_scope='any' OR r.owner_id=f.actor_id)
 AND r.classification BETWEEN 0 AND f.clearance
 AND f.classification BETWEEN 0 AND f.clearance AND f.clearance BETWEEN 0 AND 3
 AND (f.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (f.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (f.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (f.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
 AND f.workspace_epoch>0 AND f.policy_epoch>0 AND r.policy_epoch>0
 AND (r.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (r.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (r.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (r.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
 );
$$;
REVOKE ALL ON FUNCTION eid_template_family_allowed_v1(uuid,uuid,uuid) FROM PUBLIC,eid_api,eid_worker;
CREATE FUNCTION eid_template_candidate_allowed_v1(p_candidate uuid) RETURNS boolean
 LANGUAGE sql VOLATILE {security} AS $$
 SELECT EXISTS (SELECT 1 FROM template_candidate c JOIN access_current_facts f
 ON f.actor_id=c.actor_id AND f.workspace_id=c.workspace_id WHERE c.id=p_candidate
 AND c.classification BETWEEN 0 AND f.clearance
 AND eid_template_family_allowed_v1(c.template_id,c.actor_id,c.workspace_id));
$$;
REVOKE ALL ON FUNCTION eid_template_candidate_allowed_v1(uuid) FROM PUBLIC,eid_api,eid_worker;
CREATE FUNCTION eid_template_validation_pending_v1() RETURNS SETOF uuid
 LANGUAGE sql {security} AS $$
 SELECT candidate_id FROM template_validation
 WHERE session_user='eid_worker' AND (state='QUEUED' OR (state='RUNNING' AND lease_until<clock_timestamp()))
 ORDER BY updated_at,candidate_id LIMIT 10;
$$;
CREATE FUNCTION eid_template_validation_claim_v1(p_candidate uuid,p_owner uuid) RETURNS jsonb
 LANGUAGE plpgsql {security} AS $$
DECLARE candidate template_candidate; validation template_validation;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO candidate FROM template_candidate WHERE id=p_candidate;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=candidate.workspace_id FOR SHARE;
 SELECT * INTO validation FROM template_validation WHERE candidate_id=p_candidate FOR UPDATE;
 IF NOT FOUND OR NOT (validation.state='QUEUED' OR
  (validation.state='RUNNING' AND validation.lease_until<clock_timestamp())) THEN RETURN NULL; END IF;
 IF NOT eid_template_candidate_allowed_v1(p_candidate) THEN
  UPDATE template_validation SET state='BLOCKED',error_code='ACCESS_REVOKED',updated_at=clock_timestamp()
  WHERE candidate_id=p_candidate; RETURN NULL;
 END IF;
 IF validation.attempt>=3 THEN
  UPDATE template_validation SET state='REJECTED',error_code='ATTEMPTS_EXHAUSTED',updated_at=clock_timestamp()
  WHERE candidate_id=p_candidate; RETURN NULL;
 END IF;
 UPDATE template_validation SET state='RUNNING',lease_owner=p_owner,
  lease_until=clock_timestamp()+interval '60 seconds',attempt=attempt+1,updated_at=clock_timestamp()
 WHERE candidate_id=p_candidate;
 RETURN jsonb_build_object('id',candidate.id,'sha256',candidate.package_sha256,
  'package_base64',encode(candidate.package_bytes,'base64'));
END $$;
CREATE FUNCTION eid_template_validation_finish_v1(p_candidate uuid,p_owner uuid,p_report jsonb,p_error text)
 RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE candidate template_candidate; validation template_validation;
BEGIN
 IF session_user<>'eid_worker' THEN RETURN FALSE; END IF;
 SELECT * INTO candidate FROM template_candidate WHERE id=p_candidate;
 IF NOT FOUND THEN RETURN FALSE; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=candidate.workspace_id FOR SHARE;
 SELECT * INTO validation FROM template_validation WHERE candidate_id=p_candidate FOR UPDATE;
 IF NOT FOUND OR validation.state<>'RUNNING' OR validation.lease_owner IS DISTINCT FROM p_owner
  OR validation.lease_until<=clock_timestamp() THEN RETURN FALSE; END IF;
 IF NOT eid_template_candidate_allowed_v1(p_candidate) THEN
  UPDATE template_validation SET state='BLOCKED',report=NULL,error_code='ACCESS_REVOKED',
   lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE candidate_id=p_candidate;
  RETURN FALSE;
 END IF;
 IF p_report IS NOT NULL AND (p_error IS NOT NULL OR jsonb_typeof(p_report)<>'object'
  OR octet_length(p_report::text)>12582912
  OR p_report->>'source_sha256' IS DISTINCT FROM candidate.package_sha256
  OR p_report->>'validator_version' IS DISTINCT FROM 'template-archive-v1') THEN RETURN FALSE; END IF;
 IF p_report IS NULL AND (p_error IS NULL OR p_error !~ '^[A-Z_]{1,64}$') THEN RETURN FALSE; END IF;
 UPDATE template_validation SET state=CASE WHEN p_report IS NULL THEN 'REJECTED' ELSE 'VALIDATED' END,
  report=p_report,error_code=p_error,lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp()
 WHERE candidate_id=p_candidate; RETURN TRUE;
END $$;
REVOKE ALL ON FUNCTION eid_template_validation_pending_v1(),
 eid_template_validation_claim_v1(uuid,uuid),
 eid_template_validation_finish_v1(uuid,uuid,jsonb,text) FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_template_validation_pending_v1(),
 eid_template_validation_claim_v1(uuid,uuid),
 eid_template_validation_finish_v1(uuid,uuid,jsonb,text) TO eid_worker;
""")
