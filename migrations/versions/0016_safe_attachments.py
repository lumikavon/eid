"""Private, versioned attachment quarantine and atomic page/chunk publication."""
from alembic import op

revision = "0016_safe_attachments"
down_revision = "0015_outline_confirmation"
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
    op.execute("""
CREATE TABLE attachment (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, document_id uuid NOT NULL,
 uploader_id uuid NOT NULL REFERENCES identity_account(id), object_key text NOT NULL UNIQUE,
 sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
 kind text NOT NULL CHECK (kind IN ('pdf','docx','xlsx','png','jpeg')),
 byte_length integer NOT NULL CHECK (byte_length BETWEEN 1 AND 10485760),
 classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 retention text NOT NULL DEFAULT 'formal' CHECK (retention IN ('formal','quarantine')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(document_id,workspace_id) REFERENCES document(id,workspace_id),
 CHECK (object_key ~ '^attachment-quarantine/[0-9a-f-]{36}/[0-9a-f-]{36}$'),
 UNIQUE(id,document_id), UNIQUE(id,workspace_id), UNIQUE(document_id,uploader_id,sha256,kind)
);
CREATE INDEX attachment_scope ON attachment(document_id,created_at DESC);
CREATE TABLE attachment_parse (
 attachment_id uuid PRIMARY KEY REFERENCES attachment(id),
 parser_version text NOT NULL CHECK (parser_version='attachment-v1'),
 source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 delegation_id uuid NOT NULL REFERENCES access_delegation(id),
 state text NOT NULL DEFAULT 'QUEUED' CHECK (state IN ('QUEUED','RUNNING','PARTIAL','SUCCEEDED','FAILED','BLOCKED')),
 lease_owner uuid, lease_until timestamptz, attempt integer NOT NULL DEFAULT 0 CHECK (attempt BETWEEN 0 AND 3),
 error_code text CHECK (error_code ~ '^[A-Z_]{1,64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(source_sha256,parser_version,attachment_id)
);
CREATE INDEX attachment_parse_pending ON attachment_parse(state,lease_until,updated_at);
CREATE TABLE attachment_page (
 attachment_id uuid NOT NULL REFERENCES attachment(id), page_number integer NOT NULL CHECK (page_number BETWEEN 1 AND 500),
 section text NOT NULL CHECK (length(section)<=256),
 state text NOT NULL CHECK (state IN ('PARSED','OCR','FAILED')),
 error_code text CHECK (error_code IS NULL OR error_code IN ('PAGE_FAILED','OCR_UNAVAILABLE','RESOURCE_LIMIT')),
 PRIMARY KEY(attachment_id,page_number),
 CHECK ((state='FAILED')=(error_code IS NOT NULL))
);
CREATE TABLE attachment_chunk (
 attachment_id uuid NOT NULL, page_number integer NOT NULL,
 ordinal integer NOT NULL CHECK (ordinal BETWEEN 1 AND 200),
 locator text NOT NULL CHECK (length(locator) BETWEEN 1 AND 512),
 content text NOT NULL CHECK (length(content) BETWEEN 1 AND 4000),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 PRIMARY KEY(attachment_id,page_number,ordinal),
 FOREIGN KEY(attachment_id,page_number) REFERENCES attachment_page(attachment_id,page_number)
);
REVOKE ALL ON attachment,attachment_parse,attachment_page,attachment_chunk FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT,INSERT ON attachment,attachment_parse TO eid_api;
GRANT SELECT ON attachment_page,attachment_chunk TO eid_api;
""")
    op.execute(f"""
-- The worker never receives table SELECT or INSERT; current policy is checked again
-- under a workspace share lock before each claim and atomic publication.
CREATE FUNCTION eid_attachment_allowed_v1(p_id uuid) RETURNS boolean LANGUAGE sql VOLATILE {security} AS $$
 SELECT EXISTS(SELECT 1 FROM attachment a JOIN document d ON d.id=a.document_id
 JOIN access_resource r ON r.id=d.id AND r.workspace_id=a.workspace_id
 JOIN attachment_parse p ON p.attachment_id=a.id
 JOIN access_delegation g ON g.id=p.delegation_id
 JOIN access_current_facts f ON f.actor_id=a.uploader_id AND f.workspace_id=a.workspace_id
 WHERE a.id=p_id AND g.actor_id=a.uploader_id AND g.workspace_id=a.workspace_id
 AND g.resource_id=r.id AND g.operation='resource:read' AND g.purpose='attachment:'||a.id::text
 AND g.service_id='eid-worker' AND g.active AND g.expires_at>clock_timestamp()
 AND g.issued_epoch=f.workspace_epoch AND f.identity_active AND f.membership_active
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
CREATE FUNCTION eid_attachment_pending_v1() RETURNS SETOF uuid LANGUAGE sql {security} AS $$
 SELECT attachment_id FROM attachment_parse WHERE session_user='eid_worker'
 AND (state='QUEUED' OR (state='RUNNING' AND lease_until<clock_timestamp()))
 ORDER BY updated_at LIMIT 10; $$;
CREATE FUNCTION eid_attachment_claim_v1(p_id uuid,p_owner uuid) RETURNS jsonb LANGUAGE plpgsql {security} AS $$
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
 RETURN jsonb_build_object('key',a.object_key,'hash',a.sha256,'length',a.byte_length,'kind',a.kind,'delegation',p.delegation_id);
END $$;
CREATE FUNCTION eid_attachment_finish_v1(p_id uuid,p_owner uuid,p_hash text,p_pages jsonb,p_error text)
 RETURNS boolean LANGUAGE plpgsql {security} AS $$
DECLARE a attachment; p attachment_parse; item jsonb; chunk jsonb; page_count integer:=0; total_chunks integer:=0; n integer; ord integer;
BEGIN
 IF session_user<>'eid_worker' THEN RETURN FALSE; END IF;
 SELECT * INTO a FROM attachment WHERE id=p_id; IF NOT FOUND THEN RETURN FALSE; END IF;
 PERFORM 1 FROM access_workspace WHERE workspace_id=a.workspace_id FOR SHARE;
 SELECT * INTO p FROM attachment_parse WHERE attachment_id=p_id FOR UPDATE;
 IF NOT FOUND OR p.state<>'RUNNING' OR p.lease_owner IS DISTINCT FROM p_owner OR p.lease_until<=clock_timestamp() OR p_hash<>a.sha256 THEN RETURN FALSE; END IF;
 IF NOT eid_attachment_allowed_v1(p_id) THEN
  UPDATE attachment_parse SET state='BLOCKED',error_code='ACCESS_REVOKED',lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE attachment_id=p_id;
  RETURN FALSE;
 END IF;
 IF p_error IS NOT NULL THEN
  IF p_error NOT IN ('UNSAFE_CONTENT','RESOURCE_LIMIT','INTEGRITY_FAILED','PARSER_FAILED') THEN RETURN FALSE; END IF;
  UPDATE attachment_parse SET state='FAILED',error_code=p_error,lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE attachment_id=p_id;
  RETURN TRUE;
 END IF;
 IF p_pages IS NULL OR jsonb_typeof(p_pages)<>'array' OR octet_length(p_pages::text)>1048576 OR jsonb_array_length(p_pages)>500 THEN RETURN FALSE; END IF;
 -- Validate all rows and bound output before publishing any rows (transaction rollback on error).
 FOR item IN SELECT value FROM jsonb_array_elements(p_pages) LOOP
  page_count:=page_count+1; n:=(item->>'number')::integer;
  IF n<>page_count OR item->>'state' NOT IN ('PARSED','OCR','FAILED') OR
   jsonb_typeof(item->'chunks')<>'array' OR jsonb_array_length(item->'chunks')>200 OR
   length(COALESCE(item->>'section',''))>256 OR
   (item->>'state'='FAILED')<>(item->>'error' IS NOT NULL) OR
   (item->>'error' IS NOT NULL AND item->>'error' NOT IN ('PAGE_FAILED','OCR_UNAVAILABLE','RESOURCE_LIMIT'))
  THEN RAISE EXCEPTION 'Invalid attachment parser page'; END IF;
  INSERT INTO attachment_page(attachment_id,page_number,section,state,error_code)
   VALUES(p_id,n,COALESCE(item->>'section',''),item->>'state',item->>'error');
  ord:=0;
  FOR chunk IN SELECT value FROM jsonb_array_elements(item->'chunks') LOOP
   ord:=ord+1; total_chunks:=total_chunks+1;
   IF total_chunks>1000 THEN RAISE EXCEPTION 'Attachment chunk limit'; END IF;
   IF item->>'state'='FAILED' OR length(chunk->>'text') NOT BETWEEN 1 AND 4000 OR
    length(chunk->>'locator') NOT BETWEEN 1 AND 512 OR
    chunk->>'sha256' !~ '^[0-9a-f]{{64}}$' THEN RAISE EXCEPTION 'Invalid attachment parser chunk'; END IF;
   INSERT INTO attachment_chunk(attachment_id,page_number,ordinal,locator,content,content_hash)
    VALUES(p_id,n,ord,chunk->>'locator',chunk->>'text',chunk->>'sha256');
  END LOOP;
 END LOOP;
 UPDATE attachment_parse SET state=CASE WHEN page_count=0 OR NOT EXISTS
   (SELECT 1 FROM attachment_page WHERE attachment_id=p_id AND state<>'FAILED') THEN 'FAILED'
  WHEN EXISTS(SELECT 1 FROM attachment_page WHERE attachment_id=p_id AND state='FAILED') THEN 'PARTIAL'
  ELSE 'SUCCEEDED' END,
  error_code=CASE WHEN page_count=0 OR NOT EXISTS
   (SELECT 1 FROM attachment_page WHERE attachment_id=p_id AND state<>'FAILED')
   THEN 'PARSER_FAILED' ELSE NULL END,
  lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() WHERE attachment_id=p_id;
 RETURN TRUE;
END $$;
CREATE FUNCTION eid_attachment_orphan_v1(p_key text) RETURNS boolean LANGUAGE sql VOLATILE {security} AS $$
 SELECT session_user='eid_worker'
 AND p_key ~ '^attachment-quarantine/[0-9a-f-]{{36}}/[0-9a-f-]{{36}}$'
 AND NOT EXISTS(SELECT 1 FROM attachment WHERE object_key=p_key);
$$;
REVOKE ALL ON FUNCTION eid_attachment_orphan_v1(text) FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_attachment_orphan_v1(text) TO eid_worker;
REVOKE ALL ON FUNCTION eid_attachment_allowed_v1(uuid),eid_attachment_pending_v1(),
 eid_attachment_claim_v1(uuid,uuid),eid_attachment_finish_v1(uuid,uuid,text,jsonb,text) FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_attachment_pending_v1(),eid_attachment_claim_v1(uuid,uuid),
 eid_attachment_finish_v1(uuid,uuid,text,jsonb,text) TO eid_worker;
""")


def downgrade():
    raise RuntimeError("Forward-only: preserve protected attachment content")
