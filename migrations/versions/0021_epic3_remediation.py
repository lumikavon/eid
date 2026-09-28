"""Recheck current uploader policy for delayed work; honor explicit delegation revocation."""
from alembic import op

revision = "0021_epic3_remediation"
down_revision = "0020_claim_citation"
branch_labels = None
depends_on = None

def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ("eid_local_dev", "eid-local-dev-v1"):
        raise RuntimeError("Isolated EID development database required")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    security = 'SECURITY DEFINER SET search_path = pg_catalog, "' + schema.replace('"', '""') + '", pg_temp'
    # Existing referenced objects still live in the original bucket; do not make
    # them unreadable when newly uploaded objects move to the quarantine bucket.
    op.execute("""ALTER TABLE attachment ADD COLUMN storage_bucket text NOT NULL
        DEFAULT 'eid-local-artifacts' CHECK (storage_bucket IN
        ('eid-local-artifacts','eid-local-attachment-quarantine'))""")
    op.execute(f"""
CREATE OR REPLACE FUNCTION eid_attachment_allowed_v1(p_id uuid) RETURNS boolean LANGUAGE sql VOLATILE {security} AS $$
 SELECT EXISTS(SELECT 1 FROM attachment a JOIN document d ON d.id=a.document_id
 JOIN access_resource r ON r.id=d.id AND r.workspace_id=a.workspace_id
 JOIN attachment_parse p ON p.attachment_id=a.id
 JOIN access_delegation g ON g.id=p.delegation_id
 JOIN access_current_facts f ON f.actor_id=a.uploader_id AND f.workspace_id=a.workspace_id
 WHERE a.id=p_id AND g.actor_id=a.uploader_id AND g.workspace_id=a.workspace_id
 AND g.resource_id=r.id AND g.operation='resource:read' AND g.purpose='attachment:'||a.id::text
 AND g.service_id='eid-worker' AND g.active
 AND f.identity_active AND f.membership_active
 AND 'author'=ANY(f.roles) AND f.roles <@ ARRAY['author','expert','quality','template_admin','knowledge_admin','approver','system_admin']::text[]
 AND f.approval_states <@ ARRAY['draft','in_review','approved','rejected']::text[]
 AND f.valid_from<=clock_timestamp() AND (f.valid_until IS NULL OR f.valid_until>clock_timestamp())
 AND r.valid_from<=clock_timestamp() AND (r.valid_until IS NULL OR r.valid_until>clock_timestamp())
 AND r.kind='document' AND r.approval_state=ANY(f.approval_states)
 AND (f.owner_scope='any' OR r.owner_id=f.actor_id)
 AND r.classification<=f.clearance AND a.classification=r.classification
 AND f.classification<=f.clearance AND f.clearance BETWEEN 0 AND 3
 AND (r.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (r.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (r.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (r.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
 AND (f.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (f.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (f.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (f.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
 ); $$;
CREATE OR REPLACE FUNCTION eid_attachment_claim_v1(p_id uuid,p_owner uuid) RETURNS jsonb LANGUAGE plpgsql {security} AS $$
DECLARE a attachment; p attachment_parse;
BEGIN
 IF session_user<>'eid_worker' OR p_owner IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO a FROM attachment WHERE id=p_id; IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=a.workspace_id FOR SHARE;
 SELECT * INTO p FROM attachment_parse WHERE attachment_id=p_id FOR UPDATE;
 IF NOT FOUND OR NOT (p.state='QUEUED' OR (p.state='RUNNING' AND p.lease_until<clock_timestamp())) THEN RETURN NULL; END IF;
 IF NOT eid_attachment_allowed_v1(p_id) THEN
  UPDATE attachment_parse SET state='BLOCKED',error_code='ACCESS_REVOKED',lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE attachment_id=p_id;
  RETURN NULL;
 END IF;
 IF p.attempt>=3 THEN
  UPDATE attachment_parse SET state='FAILED',error_code='ATTEMPTS_EXHAUSTED',lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE attachment_id=p_id;
  RETURN NULL;
 END IF;
 UPDATE attachment_parse SET state='RUNNING',attempt=attempt+1,lease_owner=p_owner,
 lease_until=clock_timestamp()+interval '90 seconds',updated_at=clock_timestamp() WHERE attachment_id=p_id;
 RETURN jsonb_build_object('key',a.object_key,'bucket',a.storage_bucket,'hash',a.sha256,
   'length',a.byte_length,'kind',a.kind,'delegation',p.delegation_id);
END $$;
""")
    # Only tasks whose uploader is currently entitled can be reconsidered; claim
    # and finish still repeat the check under the workspace policy lock.
    op.execute("""UPDATE attachment_parse p SET state='QUEUED', error_code=NULL,
        lease_owner=NULL, lease_until=NULL, updated_at=clock_timestamp()
        WHERE p.state='BLOCKED' AND p.error_code='ACCESS_REVOKED'
        AND p.attempt<3 AND eid_attachment_allowed_v1(p.attachment_id)""")
    op.execute("""UPDATE attachment_parse p SET state='FAILED', error_code='ATTEMPTS_EXHAUSTED',
        lease_owner=NULL, lease_until=NULL, updated_at=clock_timestamp()
        WHERE p.state='BLOCKED' AND p.error_code='ACCESS_REVOKED'
        AND p.attempt>=3 AND eid_attachment_allowed_v1(p.attachment_id)""")

def downgrade():
    raise RuntimeError("Forward-only: preserve protected attachment content")
