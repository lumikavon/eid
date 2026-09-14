"""Current workspace policies, restricted delegation and atomic audit storage."""
from alembic import op

revision = "0003_current_access"
down_revision = "0002_worker_metadata_only"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE access_workspace (
 workspace_id uuid PRIMARY KEY REFERENCES workspace(id),
 tenant_id uuid NOT NULL, project_id text NOT NULL, customer_id text NOT NULL,
 product_id text NOT NULL, department text NOT NULL,
 classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 policy_epoch bigint NOT NULL DEFAULT 1 CHECK (policy_epoch > 0)
);
CREATE TABLE access_member (
 identity_id uuid NOT NULL, workspace_id uuid NOT NULL,
 roles text[] NOT NULL DEFAULT '{}', project_scope text[] NOT NULL DEFAULT '{}',
 customer_scope text[] NOT NULL DEFAULT '{}', product_scope text[] NOT NULL DEFAULT '{}',
 department_scope text[] NOT NULL DEFAULT '{}', owner_scope text NOT NULL DEFAULT 'self'
 CHECK (owner_scope IN ('self','any')), approval_states text[] NOT NULL DEFAULT '{}',
 clearance smallint NOT NULL DEFAULT 0 CHECK (clearance BETWEEN 0 AND 3),
 valid_from timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, valid_until timestamptz,
 policy_epoch bigint NOT NULL DEFAULT 1 CHECK (policy_epoch > 0),
 PRIMARY KEY(identity_id,workspace_id),
 FOREIGN KEY(identity_id,workspace_id) REFERENCES workspace_membership(identity_id,workspace_id),
 CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE TABLE access_resource (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 title text NOT NULL, kind text NOT NULL, project_id text NOT NULL,
 customer_id text NOT NULL, product_id text NOT NULL, department text NOT NULL,
 owner_id uuid NOT NULL REFERENCES identity_account(id),
 classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 approval_state text NOT NULL DEFAULT 'draft', publication_state text NOT NULL DEFAULT 'unpublished',
 head_ref uuid, policy_epoch bigint NOT NULL DEFAULT 1 CHECK (policy_epoch > 0),
 valid_from timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, valid_until timestamptz,
 CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE TABLE access_audit (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 actor_id uuid NOT NULL REFERENCES identity_account(id), target_id uuid NOT NULL,
 action text NOT NULL, before_policy jsonb NOT NULL, after_policy jsonb NOT NULL,
 request_id text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE access_invalidation (
 id uuid PRIMARY KEY REFERENCES access_audit(id), workspace_id uuid NOT NULL,
 actor_id uuid NOT NULL, policy_epoch bigint NOT NULL, created_at timestamptz NOT NULL
 DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE access_delegation (
 id uuid PRIMARY KEY, actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 resource_id uuid REFERENCES access_resource(id), operation text NOT NULL,
 purpose text NOT NULL CHECK (length(purpose) BETWEEN 1 AND 128),
 service_id text NOT NULL CHECK (service_id = 'eid-worker'),
 expires_at timestamptz NOT NULL, active boolean NOT NULL DEFAULT true,
 issued_epoch bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE VIEW access_current_facts AS
 SELECT i.id AS actor_id, i.subject, i.active AS identity_active,
 i.display_name, i.department AS actor_department,
 m.active AS membership_active, p.*, w.tenant_id, w.project_id, w.customer_id,
 w.product_id, w.department, w.classification,
 w.policy_epoch AS workspace_epoch, n.slug AS workspace_slug, n.name AS workspace_name
 FROM identity_account i JOIN workspace_membership m ON m.identity_id=i.id
 JOIN access_member p ON p.identity_id=m.identity_id AND p.workspace_id=m.workspace_id
 JOIN access_workspace w ON w.workspace_id=m.workspace_id
 JOIN workspace n ON n.id=w.workspace_id;
GRANT SELECT ON access_workspace,access_member,access_resource,access_audit,
 access_invalidation,access_delegation,access_current_facts TO eid_api;
GRANT UPDATE ON access_workspace,access_member,workspace_membership TO eid_api;
GRANT INSERT ON access_audit,access_invalidation,access_delegation TO eid_api;
REVOKE ALL ON access_workspace,access_member,access_resource,access_audit,
 access_invalidation,access_delegation,access_current_facts FROM eid_worker;
INSERT INTO access_workspace(workspace_id,tenant_id,project_id,customer_id,product_id,
 department,classification)
 SELECT id,id,slug,'local-customer','local-product','产品部',1 FROM workspace;
INSERT INTO access_member(identity_id,workspace_id,roles,project_scope,customer_scope,
 product_scope,department_scope,owner_scope,approval_states,clearance)
 SELECT m.identity_id,m.workspace_id,ARRAY['author'],ARRAY[w.project_id],
 ARRAY[w.customer_id],ARRAY[w.product_id],ARRAY[w.department],'self',ARRAY['draft'],1
 FROM workspace_membership m JOIN access_workspace w USING(workspace_id);
""")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    op.execute(f"""
CREATE FUNCTION eid_worker_access(delegation_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}
AS $$
 SELECT jsonb_build_object('facts',to_jsonb(f)||jsonb_build_object('evaluated_at',clock_timestamp()),'resource',to_jsonb(r),
   'delegation',to_jsonb(d))
 FROM access_delegation d JOIN access_current_facts f
 ON f.actor_id=d.actor_id AND f.workspace_id=d.workspace_id
 LEFT JOIN access_resource r ON r.id=d.resource_id AND r.workspace_id=d.workspace_id
 WHERE d.id=delegation_id AND d.active AND d.service_id='eid-worker'
 AND d.expires_at>CURRENT_TIMESTAMP AND session_user='eid_worker'
 AND (d.resource_id IS NULL OR r.id IS NOT NULL)
$$;
REVOKE ALL ON FUNCTION eid_worker_access(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_worker_access(uuid) TO eid_worker;
""")


def downgrade():
    raise RuntimeError("Local access migrations are forward-only; preserve existing data")
