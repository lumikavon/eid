"""Immutable manually confirmed project context; forward-only on isolated EID database."""

from alembic import op

revision = "0014_project_context"
down_revision = "0013_template_governance"
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(), shobj_description(oid,'pg_database') "
        "FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ("eid_local_dev", "eid-local-dev-v1"):
        raise RuntimeError("Story 2.5 migration requires the isolated EID development database")
    op.execute("""
CREATE TABLE project_context_version (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES document(id),
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9007199254740991),
 base_version_id uuid,
 document_version_id uuid NOT NULL,
 document_revision bigint NOT NULL CHECK (document_revision BETWEEN 1 AND 9007199254740991),
 snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot)='object' AND octet_length(snapshot::text)<=131072),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 created_by uuid NOT NULL REFERENCES identity_account(id),
 created_at timestamptz NOT NULL CHECK (isfinite(created_at)),
 UNIQUE(document_id,revision), UNIQUE(id,document_id),
 FOREIGN KEY(base_version_id,document_id) REFERENCES project_context_version(id,document_id),
 FOREIGN KEY(document_version_id,document_id) REFERENCES document_version(id,document_id)
);
CREATE TRIGGER project_context_version_immutable BEFORE UPDATE OR DELETE ON project_context_version
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
CREATE TABLE project_context_head (
 document_id uuid PRIMARY KEY REFERENCES document(id),
 version_id uuid NOT NULL,
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9007199254740991),
 FOREIGN KEY(version_id,document_id) REFERENCES project_context_version(id,document_id)
 DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE project_context_confirmation (
 version_id uuid PRIMARY KEY,
 document_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 confirmed_at timestamptz NOT NULL CHECK (isfinite(confirmed_at)),
 ready_at_confirmation boolean NOT NULL,
 FOREIGN KEY(version_id,document_id) REFERENCES project_context_version(id,document_id)
);
CREATE TRIGGER project_context_confirmation_immutable BEFORE UPDATE OR DELETE ON project_context_confirmation
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
REVOKE ALL ON project_context_version,project_context_head,project_context_confirmation FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON project_context_version,project_context_head,project_context_confirmation TO eid_api;
GRANT UPDATE(version_id,revision) ON project_context_head TO eid_api;
""")


def downgrade():
    raise RuntimeError("Story 2.5 migration is forward-only; preserve context and confirmations")
