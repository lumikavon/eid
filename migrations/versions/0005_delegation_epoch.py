"""Invalidate stored worker capabilities when workspace policy changes."""
from alembic import op

revision = "0005_delegation_epoch"
down_revision = "0004_access_correlation"
branch_labels = None
depends_on = None


def upgrade():
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    op.execute(f"""
CREATE OR REPLACE FUNCTION eid_worker_access(delegation_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}
AS $$
 SELECT jsonb_build_object('facts',to_jsonb(f)||jsonb_build_object('evaluated_at',clock_timestamp()),
   'resource',to_jsonb(r),'delegation',to_jsonb(d))
 FROM access_delegation d JOIN access_current_facts f
 ON f.actor_id=d.actor_id AND f.workspace_id=d.workspace_id
 LEFT JOIN access_resource r ON r.id=d.resource_id AND r.workspace_id=d.workspace_id
 WHERE d.id=delegation_id AND d.active AND d.service_id='eid-worker'
 AND d.expires_at>CURRENT_TIMESTAMP AND session_user='eid_worker'
 AND d.issued_epoch=f.workspace_epoch
 AND (d.resource_id IS NULL OR r.id IS NOT NULL)
$$;
REVOKE ALL ON FUNCTION eid_worker_access(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION eid_worker_access(uuid) TO eid_worker;
""")


def downgrade():
    raise RuntimeError("Local access migrations are forward-only; preserve existing data")
