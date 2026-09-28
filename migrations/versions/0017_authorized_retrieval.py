"""Version-pinned local attachment index; worker cannot read protected source tables."""
from alembic import op

revision = "0017_authorized_retrieval"
down_revision = "0016_safe_attachments"
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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH VERSION '0.8.6'")
    installed = op.get_bind().exec_driver_sql(
        "SELECT extversion FROM pg_extension WHERE extname='vector'"
    ).scalar_one()
    if installed != "0.8.6":
        raise RuntimeError("pgvector 0.8.6 is required for this index")
    op.execute("""
CREATE TABLE attachment_search_index (
 attachment_id uuid NOT NULL, page_number integer NOT NULL, ordinal integer NOT NULL,
 workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 parser_version text NOT NULL CHECK (parser_version='attachment-v1'),
 source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 keyword_version text NOT NULL CHECK (keyword_version IN ('fts-simple-v1','fts-jieba-v1')),
 dictionary_version text NOT NULL CHECK (dictionary_version IN ('none','jieba-default-v1')),
 tokens tsvector NOT NULL,
 embedding vector(1024), embedding_version text,
 indexed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(attachment_id,page_number,ordinal),
 FOREIGN KEY(attachment_id,page_number,ordinal) REFERENCES attachment_chunk(attachment_id,page_number,ordinal),
 FOREIGN KEY(attachment_id,document_id) REFERENCES attachment(id,document_id),
 FOREIGN KEY(attachment_id,workspace_id) REFERENCES attachment(id,workspace_id),
 CHECK ((embedding IS NULL)=(embedding_version IS NULL)),
 CHECK (embedding_version IS NULL OR embedding_version='bge-m3-v1')
);
CREATE INDEX attachment_search_tokens ON attachment_search_index USING gin(tokens);
CREATE INDEX attachment_search_scope ON attachment_search_index(workspace_id,document_id);
CREATE INDEX attachment_search_vector ON attachment_search_index USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;
REVOKE ALL ON attachment_search_index FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT ON attachment_search_index TO eid_api;
""")
    op.execute(f"""
-- Index input is read from the canonical parser rows, never from worker-submitted text.
-- Indexer is gated by a *current* workbench read policy, not the expired parse delegation.
-- This permission does not grant any search reader access: API rechecks each reader separately.
CREATE FUNCTION eid_search_indexable_v1(p_id uuid) RETURNS boolean LANGUAGE sql VOLATILE {security} AS $$
 SELECT EXISTS(SELECT 1 FROM attachment a JOIN access_resource r ON r.id=a.document_id
 JOIN access_current_facts f ON f.actor_id=a.uploader_id AND f.workspace_id=a.workspace_id
 WHERE a.id=p_id AND r.workspace_id=a.workspace_id AND r.kind='document'
 AND f.identity_active AND f.membership_active AND cardinality(f.roles)>0
 AND f.valid_from<=clock_timestamp() AND (f.valid_until IS NULL OR f.valid_until>clock_timestamp())
 AND r.valid_from<=clock_timestamp() AND (r.valid_until IS NULL OR r.valid_until>clock_timestamp())
 AND r.approval_state=ANY(f.approval_states)
 AND (f.owner_scope='any' OR r.owner_id=f.actor_id)
 AND r.classification<=f.clearance AND a.classification<=f.clearance
 AND f.classification<=f.clearance AND f.clearance BETWEEN 0 AND 3
 AND (r.project_id=ANY(f.project_scope) OR '*'=ANY(f.project_scope))
 AND (r.customer_id=ANY(f.customer_scope) OR '*'=ANY(f.customer_scope))
 AND (r.product_id=ANY(f.product_scope) OR '*'=ANY(f.product_scope))
 AND (r.department=ANY(f.department_scope) OR '*'=ANY(f.department_scope))
 ); $$;
CREATE FUNCTION eid_search_pending_v1(p_semantic boolean,p_jieba boolean) RETURNS jsonb LANGUAGE sql {security} AS $$
 SELECT CASE WHEN session_user<>'eid_worker' THEN '[]'::jsonb ELSE COALESCE((
 SELECT jsonb_agg(jsonb_build_object('attachment_id',q.attachment_id,'page',q.page_number,
 'ordinal',q.ordinal,'text',q.content,'hash',q.content_hash)) FROM (
 SELECT c.attachment_id,c.page_number,c.ordinal,c.content,c.content_hash
 FROM attachment_chunk c JOIN attachment_parse p ON p.attachment_id=c.attachment_id
 LEFT JOIN attachment_search_index i ON i.attachment_id=c.attachment_id
 AND i.page_number=c.page_number AND i.ordinal=c.ordinal
 WHERE p.state IN ('SUCCEEDED','PARTIAL') AND p.parser_version='attachment-v1'
 AND eid_search_indexable_v1(c.attachment_id)
 AND (i.attachment_id IS NULL OR i.content_hash<>c.content_hash OR i.source_sha256<>p.source_sha256
 OR (p_semantic AND i.embedding IS NULL) OR (p_jieba AND i.keyword_version<>'fts-jieba-v1'))
 ORDER BY c.attachment_id,c.page_number,c.ordinal LIMIT 8) q), '[]'::jsonb) END;
$$;
CREATE FUNCTION eid_search_index_v1(p_id uuid,p_page integer,p_ordinal integer,p_hash text,
 p_embedding text,p_model text,p_terms text) RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE a attachment; p attachment_parse; c attachment_chunk; v vector(1024);
BEGIN
 IF session_user<>'eid_worker' THEN RETURN FALSE; END IF;
 SELECT * INTO a FROM attachment WHERE id=p_id;
 IF NOT FOUND THEN RETURN FALSE; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=a.workspace_id FOR SHARE;
 SELECT * INTO p FROM attachment_parse WHERE attachment_id=p_id FOR SHARE;
 SELECT * INTO c FROM attachment_chunk WHERE attachment_id=p_id AND page_number=p_page AND ordinal=p_ordinal FOR SHARE;
 IF NOT FOUND OR p.state NOT IN ('SUCCEEDED','PARTIAL') OR p.parser_version<>'attachment-v1'
 OR p.source_sha256<>a.sha256 OR c.content_hash<>p_hash OR NOT eid_search_indexable_v1(p_id)
 THEN RETURN FALSE; END IF;
 IF p_terms IS NOT NULL AND length(p_terms)>10000 THEN RETURN FALSE; END IF;
 IF p_embedding IS NOT NULL THEN
  IF p_model IS DISTINCT FROM 'bge-m3-v1' OR length(p_embedding)>16000 THEN RETURN FALSE; END IF;
  v:=p_embedding::vector(1024);
  IF vector_norm(v)=0 THEN RETURN FALSE; END IF;
 ELSE
  IF p_model IS NOT NULL THEN RETURN FALSE; END IF;
 END IF;
 INSERT INTO attachment_search_index(attachment_id,page_number,ordinal,workspace_id,document_id,
 parser_version,source_sha256,content_hash,keyword_version,dictionary_version,tokens,embedding,embedding_version)
 VALUES(p_id,p_page,p_ordinal,a.workspace_id,a.document_id,p.parser_version,p.source_sha256,
 c.content_hash,CASE WHEN p_terms IS NULL THEN 'fts-simple-v1' ELSE 'fts-jieba-v1' END,
 CASE WHEN p_terms IS NULL THEN 'none' ELSE 'jieba-default-v1' END,
 to_tsvector('simple',c.content) || to_tsvector('simple',COALESCE(p_terms,'')),v,p_model)
 ON CONFLICT (attachment_id,page_number,ordinal) DO UPDATE SET
 source_sha256=EXCLUDED.source_sha256,content_hash=EXCLUDED.content_hash,
 tokens=EXCLUDED.tokens,dictionary_version=EXCLUDED.dictionary_version,
 keyword_version=EXCLUDED.keyword_version,embedding=EXCLUDED.embedding,embedding_version=EXCLUDED.embedding_version,
 indexed_at=clock_timestamp();
 RETURN TRUE;
END $$;
REVOKE ALL ON FUNCTION eid_search_indexable_v1(uuid),eid_search_pending_v1(boolean,boolean),eid_search_index_v1(uuid,integer,integer,text,text,text,text)
 FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_search_pending_v1(boolean,boolean),eid_search_index_v1(uuid,integer,integer,text,text,text,text) TO eid_worker;
""")


def downgrade():
    raise RuntimeError("Forward-only: preserve source index provenance")
