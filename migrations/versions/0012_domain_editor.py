"""Minimal immutable document editing and authorized image references.

Revision ID: 0012_domain_editor
"""

from alembic import op


revision = "0012_domain_editor"
down_revision = "0011_template_creation"
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(), shobj_description(oid,'pg_database') "
        "FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ("eid_local_dev", "eid-local-dev-v1"):
        raise RuntimeError("Story 2.2 migration requires the isolated EID local database")
    op.execute("""
ALTER TABLE document ADD CONSTRAINT document_id_workspace_unique UNIQUE(id,workspace_id);
CREATE TABLE document_media (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES document(id),
 workspace_id uuid NOT NULL,
 uploader_id uuid NOT NULL REFERENCES identity_account(id),
 object_key text NOT NULL UNIQUE CHECK (length(object_key) BETWEEN 40 AND 255),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 content_type text NOT NULL CHECK (content_type='image/png'),
 byte_length integer NOT NULL CHECK (byte_length BETWEEN 1 AND 5242880),
 alt text NOT NULL CHECK (length(alt) BETWEEN 1 AND 512),
 width integer NOT NULL CHECK (width BETWEEN 1 AND 8192),
 height integer NOT NULL CHECK (height BETWEEN 1 AND 8192),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(created_at)),
 FOREIGN KEY(document_id,workspace_id) REFERENCES document(id,workspace_id),
 UNIQUE(id,document_id)
);
CREATE INDEX document_media_document ON document_media(document_id,id);
REVOKE ALL ON document_media FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON document_media TO eid_api;
GRANT UPDATE (head_version_id,revision) ON document TO eid_api;
GRANT UPDATE (title,head_ref) ON access_resource TO eid_api;
""")


def downgrade():
    raise RuntimeError("Story 2.2 migration is forward-only; preserve document versions and media")
