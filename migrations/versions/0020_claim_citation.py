"""Version-pinned claims, exact evidence bindings and controlled citations."""
from alembic import op

revision = '0020_claim_citation'
down_revision = '0019_section_evidence'
branch_labels = None
depends_on = None


def upgrade():
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
        raise RuntimeError('Isolated EID development database required')
    op.execute("""
CREATE TABLE document_claim (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 document_version_id uuid NOT NULL REFERENCES document_version(id), section_id uuid NOT NULL,
 block_id uuid NOT NULL, start_offset integer NOT NULL CHECK(start_offset>=0),
 end_offset integer NOT NULL CHECK(end_offset>start_offset), statement text NOT NULL CHECK(length(statement) BETWEEN 1 AND 4000),
 claim_type text NOT NULL CHECK(length(claim_type) BETWEEN 1 AND 80), conditions text NOT NULL DEFAULT '' CHECK(length(conditions)<=512),
 value text NOT NULL CHECK(length(value) BETWEEN 1 AND 256), unit text NOT NULL DEFAULT '' CHECK(length(unit)<=64),
 critical boolean NOT NULL DEFAULT true, status text NOT NULL CHECK(status IN
 ('supported','partially_supported','conflicting','unsupported','unknown')),
 needs_review boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(document_version_id,block_id,start_offset,end_offset,claim_type)
);
CREATE INDEX document_claim_version ON document_claim(workspace_id,document_id,document_version_id);
CREATE TABLE claim_evidence_link (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, claim_id uuid NOT NULL,
 pack_id uuid NOT NULL REFERENCES section_evidence_pack(id), item_ordinal smallint NOT NULL,
 relation text NOT NULL CHECK(relation IN ('supports','conflicts','contextual')),
 chain text NOT NULL CHECK(chain IN ('attachment','enterprise')), source_id text NOT NULL,
 source_version text NOT NULL, chunk_hash text NOT NULL, locator text NOT NULL,
 quoted_text text NOT NULL CHECK(length(quoted_text) BETWEEN 1 AND 4000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,claim_id) REFERENCES document_claim(workspace_id,id),
 FOREIGN KEY(pack_id,item_ordinal) REFERENCES section_evidence_item(pack_id,ordinal),
 UNIQUE(workspace_id,claim_id,pack_id,item_ordinal)
);
CREATE TABLE document_citation (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 document_version_id uuid NOT NULL REFERENCES document_version(id), claim_id uuid NOT NULL,
 link_id uuid NOT NULL REFERENCES claim_evidence_link(id), section_id uuid NOT NULL,
 block_id uuid NOT NULL, start_offset integer NOT NULL, end_offset integer NOT NULL,
 selected_text text NOT NULL, quoted_text text NOT NULL, needs_review boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,claim_id) REFERENCES document_claim(workspace_id,id)
);
REVOKE ALL ON document_claim,claim_evidence_link,document_citation FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON document_claim,claim_evidence_link,document_citation TO eid_api;
GRANT UPDATE(status,needs_review) ON document_claim TO eid_api;
GRANT UPDATE(needs_review) ON document_citation TO eid_api;
""")


def downgrade():
    raise RuntimeError('Forward-only: preserve claim and citation provenance')
