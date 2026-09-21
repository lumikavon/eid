"""仅扩展发现投影与私人集合；不清理已有记录或扩大 Worker 权限。"""
from alembic import op

revision = "0007_workspace_discovery"
down_revision = "0006_api_write_only"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE discovery_record (
 resource_id uuid PRIMARY KEY REFERENCES access_resource(id),
 kind text NOT NULL CHECK (kind IN ('document','knowledge','reference')),
 created_by uuid NOT NULL REFERENCES identity_account(id),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(created_at)),
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(updated_at)),
 document_type text CHECK (document_type IN ('technical','proposal','report','manual','other')),
 lifecycle text NOT NULL CHECK (lifecycle IN ('DRAFT','IN_REVIEW','APPROVED','ARCHIVED')),
 version_label text CHECK (length(version_label) BETWEEN 1 AND 128),
 visibility text NOT NULL DEFAULT 'visible' CHECK (visibility IN ('visible','recycled')),
 revision bigint NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
 fixture_owner text CHECK (length(fixture_owner) BETWEEN 1 AND 128),
 fixture_version text CHECK (length(fixture_version) BETWEEN 1 AND 128),
 CHECK ((fixture_owner IS NULL) = (fixture_version IS NULL)),
 CHECK ((kind='document') = (document_type IS NOT NULL)),
 CHECK (updated_at >= created_at)
);
CREATE INDEX discovery_record_page ON discovery_record(updated_at DESC, resource_id DESC);
CREATE TABLE discovery_participant (
 resource_id uuid NOT NULL REFERENCES discovery_record(resource_id),
 identity_id uuid NOT NULL REFERENCES identity_account(id),
 PRIMARY KEY (resource_id, identity_id)
);
CREATE TABLE discovery_favorite (
 resource_id uuid NOT NULL REFERENCES discovery_record(resource_id),
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 active boolean NOT NULL,
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9007199254740991),
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(updated_at)),
 PRIMARY KEY (resource_id, actor_id)
);
CREATE TABLE discovery_restore_policy (
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 kind text NOT NULL CHECK (kind='document'),
 version text NOT NULL CHECK (length(version) BETWEEN 1 AND 128),
 action text NOT NULL CHECK (action='restore_visibility'),
 required_operation text NOT NULL CHECK (required_operation='document:edit'),
 owner_only boolean NOT NULL CHECK (owner_only),
 environment_class text NOT NULL CHECK (environment_class IN ('production','isolated_development')),
 fixture_owner text CHECK (length(fixture_owner) BETWEEN 1 AND 128),
 fixture_version text CHECK (length(fixture_version) BETWEEN 1 AND 128),
 active boolean NOT NULL DEFAULT false,
 valid_from timestamptz NOT NULL CHECK (isfinite(valid_from)),
 valid_until timestamptz CHECK (isfinite(valid_until) AND valid_until>valid_from),
 PRIMARY KEY (workspace_id, kind),
 CHECK ((environment_class='isolated_development' AND fixture_owner IS NOT NULL
         AND fixture_version IS NOT NULL) OR
        (environment_class='production' AND fixture_owner IS NULL AND fixture_version IS NULL))
);
CREATE TABLE discovery_receipt (
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
 operation_id uuid NOT NULL UNIQUE REFERENCES access_audit(id),
 resource_id uuid NOT NULL REFERENCES discovery_record(resource_id),
 action text NOT NULL CHECK (action IN ('favorite.set','restore_visibility')),
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 occurred_at timestamptz NOT NULL CHECK (isfinite(occurred_at)),
 PRIMARY KEY (actor_id, workspace_id, idempotency_key)
);
GRANT SELECT ON discovery_record,discovery_participant,discovery_favorite,
 discovery_restore_policy,discovery_receipt TO eid_api;
GRANT INSERT ON discovery_favorite,discovery_receipt TO eid_api;
GRANT UPDATE (active,revision,updated_at) ON discovery_favorite TO eid_api;
GRANT UPDATE (visibility,revision,updated_at) ON discovery_record TO eid_api;
REVOKE ALL ON discovery_record,discovery_participant,discovery_favorite,
 discovery_restore_policy,discovery_receipt FROM PUBLIC,eid_worker;
""")


def downgrade():
    raise RuntimeError("发现迁移只允许向前修复；保留全部新表和既有数据")
