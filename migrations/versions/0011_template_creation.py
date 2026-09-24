"""Local development template catalog and immutable initial document versions.

Revision ID: 0011_template_creation
"""

import json
from uuid import NAMESPACE_URL, uuid5

from alembic import op


revision = "0011_template_creation"
down_revision = "0010_task_observation"
branch_labels = None
depends_on = None

WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
ACTOR_ID = "11111111-1111-4111-8111-111111111111"
FIXTURE_VERSION = "story-2.1-v1"

# These are labeled development examples, not approved enterprise standards.
EXAMPLES = (
    ("technical_solution", "技术方案", "enterprise", "技术方案", ("项目概述", "建设目标与需求分析", "总体技术方案", "实施计划", "安全与运维保障", "风险分析与应对")),
    ("bid", "标书", "department", "标书", ("投标概述", "商务响应", "技术响应", "合规矩阵")),
    ("prd", "PRD", "product_line", "PRD", ("产品概述", "用户与场景", "功能需求", "非功能需求", "验收标准")),
    ("test_plan", "测试方案", "project", "测试方案", ("测试目标", "测试范围", "测试策略", "测试环境", "验收准则")),
    ("project_summary", "项目总结", "personal", "项目总结", ("项目目标", "交付结果", "差异分析", "经验与改进")),
    ("technical_requirements", "技术要求", "enterprise", "技术要求", ("适用范围", "技术指标", "验证方法")),
    ("quality_outline", "质量大纲", "department", "质量大纲", ("质量目标", "组织职责", "质量控制", "验收记录")),
    ("project_plan", "项目计划", "project", "项目计划", ("项目目标", "里程碑", "资源与职责", "风险")),
    ("functional_test_outline", "功能测试大纲", "project", "功能测试", ("测试范围", "测试项", "需求覆盖", "准入与退出")),
    ("performance_test_outline", "性能测试大纲", "product_line", "性能测试", ("测试负载", "环境与数据", "指标与阈值", "测量方法")),
    ("production_form", "生产过程记录表单", "enterprise", "生产表单", ("表单说明", "记录字段", "人工确认")),
)


def _literal(value):
    return "'" + value.replace("'", "''") + "'"


def upgrade():
    # Fail closed if this migration is pointed at an existing enterprise or production database.
    identity = op.get_bind().exec_driver_sql(
        "SELECT current_database(), shobj_description(oid,'pg_database') "
        "FROM pg_database WHERE datname=current_database()"
    ).one()
    if tuple(identity) != ("eid_local_dev", "eid-local-dev-v1"):
        raise RuntimeError("Story 2.1 migration requires the isolated EID local database")
    schema = op.get_bind().exec_driver_sql("SELECT current_schema()").scalar_one()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    security = f"SECURITY DEFINER SET search_path = pg_catalog, {quoted_schema}, pg_temp"
    op.execute("""
CREATE TABLE template (
 id uuid PRIMARY KEY,
 owner_id uuid REFERENCES identity_account(id)
);
CREATE TABLE template_version (
 id uuid PRIMARY KEY,
 template_id uuid NOT NULL REFERENCES template(id),
 version_label text NOT NULL CHECK (length(version_label) BETWEEN 1 AND 128),
 name text NOT NULL CHECK (length(name) BETWEEN 1 AND 256),
 description text NOT NULL CHECK (length(description) BETWEEN 1 AND 1024),
 scope text NOT NULL CHECK (scope IN ('enterprise','department','product_line','project','personal')),
 target_scope_value text,
 category text NOT NULL CHECK (length(category) BETWEEN 1 AND 128),
 document_type text NOT NULL CHECK (document_type IN
  ('technical_solution','bid','prd','test_plan','project_summary',
   'technical_requirements','quality_outline','project_plan',
   'functional_test_outline','performance_test_outline','production_form')),
 classification smallint NOT NULL CHECK (classification BETWEEN 0 AND 3),
 structure jsonb NOT NULL CHECK (jsonb_typeof(structure)='object'
  AND jsonb_typeof(structure->'sections')='array'),
 development_only boolean NOT NULL CHECK (development_only),
 fixture_owner text NOT NULL CHECK (fixture_owner='story-2.1'),
 fixture_version text NOT NULL CHECK (length(fixture_version) BETWEEN 1 AND 128),
 created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(created_at)),
 CHECK ((scope IN ('department','product_line','project')) = (target_scope_value IS NOT NULL)),
 CHECK (target_scope_value IS NULL OR length(target_scope_value) BETWEEN 1 AND 128),
 UNIQUE(template_id,version_label)
);
CREATE TABLE template_version_state (
 version_id uuid PRIMARY KEY REFERENCES template_version(id),
 status text NOT NULL CHECK (status IN ('active','deprecated')),
 updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP CHECK (isfinite(updated_at))
);
CREATE TABLE template_workspace (
 version_id uuid NOT NULL REFERENCES template_version(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 active boolean NOT NULL,
 PRIMARY KEY(version_id,workspace_id)
);
CREATE INDEX template_workspace_catalog ON template_workspace(workspace_id,active,version_id);
CREATE TABLE document_knowledge_scope_grant (
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 scope text NOT NULL CHECK (scope IN
  ('project_only','project_enterprise_quality','all_authorized')),
 active boolean NOT NULL,
 PRIMARY KEY(workspace_id,scope)
);
CREATE TABLE document (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 owner_id uuid NOT NULL REFERENCES identity_account(id),
 document_type text NOT NULL CHECK (document_type IN
  ('technical_solution','bid','prd','test_plan','project_summary',
   'technical_requirements','quality_outline','project_plan',
   'functional_test_outline','performance_test_outline','production_form')),
 knowledge_scope text NOT NULL CHECK (knowledge_scope IN
  ('project_only','project_enterprise_quality','all_authorized')),
 template_version_id uuid NOT NULL REFERENCES template_version(id),
 head_version_id uuid NOT NULL,
 revision bigint NOT NULL DEFAULT 1 CHECK (revision BETWEEN 1 AND 9007199254740991),
 created_at timestamptz NOT NULL CHECK (isfinite(created_at)),
 FOREIGN KEY(id,workspace_id) REFERENCES access_resource(id,workspace_id)
);
CREATE TABLE document_version (
 id uuid PRIMARY KEY,
 document_id uuid NOT NULL REFERENCES document(id),
 revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 9007199254740991),
 base_version_id uuid,
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 ast jsonb NOT NULL CHECK (jsonb_typeof(ast)='object'
  AND ast->>'schema_version'='1.0'
  AND jsonb_typeof(ast->'document')='object'
  AND jsonb_typeof(ast->'document'->'metadata')='object'
  AND jsonb_typeof(ast->'document'->'sections')='array'
  AND jsonb_typeof(ast->'document'->'claims')='array'
  AND jsonb_typeof(ast->'document'->'citations')='array'
  AND jsonb_typeof(ast->'document'->'review_state')='object'),
 created_by uuid NOT NULL REFERENCES identity_account(id),
 created_at timestamptz NOT NULL CHECK (isfinite(created_at)),
 UNIQUE(document_id,revision), UNIQUE(id,document_id),
 FOREIGN KEY(base_version_id,document_id) REFERENCES document_version(id,document_id)
);
ALTER TABLE document ADD CONSTRAINT document_head_own_version_fk
 FOREIGN KEY(head_version_id,id) REFERENCES document_version(id,document_id)
 DEFERRABLE INITIALLY DEFERRED;
CREATE INDEX document_workspace_owner ON document(workspace_id,owner_id,created_at DESC,id DESC);
CREATE TABLE document_creation_receipt (
 actor_id uuid NOT NULL REFERENCES identity_account(id),
 workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
 idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{1,128}$'),
 payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
 document_id uuid NOT NULL REFERENCES document(id),
 operation_id uuid NOT NULL UNIQUE REFERENCES access_audit(id),
 occurred_at timestamptz NOT NULL CHECK (isfinite(occurred_at)),
 PRIMARY KEY(actor_id,workspace_id,idempotency_key)
);
CREATE FUNCTION eid_immutable_template_document_version() RETURNS trigger
 LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Immutable version cannot be changed'; END $$;
CREATE TRIGGER template_version_immutable BEFORE UPDATE OR DELETE ON template_version
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
CREATE TRIGGER document_version_immutable BEFORE UPDATE OR DELETE ON document_version
 FOR EACH ROW EXECUTE FUNCTION eid_immutable_template_document_version();
REVOKE ALL ON template,template_version,template_version_state,template_workspace,
 document_knowledge_scope_grant,document,document_version,document_creation_receipt
 FROM PUBLIC,eid_api,eid_worker;
GRANT SELECT ON template,template_version,template_version_state,template_workspace,
 document_knowledge_scope_grant,document,document_version,document_creation_receipt TO eid_api;
GRANT INSERT ON document,document_version,document_creation_receipt TO eid_api;
GRANT INSERT (id,workspace_id,title,kind,project_id,customer_id,product_id,
 department,owner_id,classification,approval_state,publication_state,head_ref,valid_from)
 ON access_resource TO eid_api;
GRANT INSERT (resource_id,kind,created_by,created_at,updated_at,document_type,
 lifecycle,version_label,visibility,revision) ON discovery_record TO eid_api;
REVOKE ALL ON FUNCTION eid_immutable_template_document_version() FROM PUBLIC,eid_api,eid_worker;
""")
    # Row locks require UPDATE privilege in PostgreSQL. Give the API narrowly
    # scoped lock functions rather than UPDATE on catalog or grant tables.
    op.execute(f"""
CREATE FUNCTION eid_lock_document_knowledge_scope_v1(p_workspace uuid,p_scope text)
 RETURNS void LANGUAGE plpgsql {security} AS $$
BEGIN
 PERFORM 1 FROM document_knowledge_scope_grant
  WHERE workspace_id=p_workspace AND scope=p_scope FOR SHARE;
END $$;
REVOKE ALL ON FUNCTION eid_lock_document_knowledge_scope_v1(uuid,text)
 FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_lock_document_knowledge_scope_v1(uuid,text) TO eid_api;

CREATE FUNCTION eid_lock_template_creation_v1(p_workspace uuid,p_template uuid)
 RETURNS void LANGUAGE plpgsql {security} AS $$
BEGIN
 -- The root lock also excludes a concurrent new version referencing it.
 PERFORM 1 FROM template WHERE id=p_template FOR UPDATE;
 IF NOT FOUND THEN RETURN; END IF;
 PERFORM 1 FROM template_version v
  JOIN template_version_state s ON s.version_id=v.id
  JOIN template_workspace w ON w.version_id=v.id
  WHERE v.template_id=p_template AND w.workspace_id=p_workspace
  FOR SHARE OF s,w;
END $$;
REVOKE ALL ON FUNCTION eid_lock_template_creation_v1(uuid,uuid)
 FROM PUBLIC,eid_api,eid_worker;
GRANT EXECUTE ON FUNCTION eid_lock_template_creation_v1(uuid,uuid) TO eid_api;
""")
    # The fixture source is migration-controlled and restricted to this isolated database.
    # Broader knowledge scopes have no authoritative source ACL yet. Their UI
    # choices remain unavailable until separately granted by governed data.
    op.execute(
        "INSERT INTO document_knowledge_scope_grant(workspace_id,scope,active) VALUES "
        f"({_literal(WORKSPACE_ID)},'project_only',true)"
    )
    for type_id, label, scope, category, sections in EXAMPLES:
        template_id = str(uuid5(NAMESPACE_URL, f"eid-story-2.1-template-{type_id}"))
        version_id = str(uuid5(NAMESPACE_URL, f"eid-story-2.1-version-{type_id}"))
        structure = json.dumps({"sections": [{"title": title} for title in sections]}, ensure_ascii=False)
        owner = _literal(ACTOR_ID) if scope == "personal" else "NULL"
        target = {"department": "产品部", "product_line": "local-product",
                  "project": "eid-local"}.get(scope)
        target_literal = _literal(target) if target is not None else "NULL"
        op.execute(
            "INSERT INTO template(id,owner_id) VALUES "
            f"({_literal(template_id)},{owner});"
            "INSERT INTO template_version(id,template_id,version_label,name,description,scope,target_scope_value,"
            "category,document_type,classification,structure,development_only,fixture_owner,fixture_version) VALUES "
            f"({_literal(version_id)},{_literal(template_id)},'1.0',"
            f"{_literal(label + '开发样例')},{_literal('仅供本地开发，不代表正式模板或完整文种流程')},"
            f"{_literal(scope)},{target_literal},{_literal(category)},{_literal(type_id)},1,"
            f"{_literal(structure)}::jsonb,true,'story-2.1',{_literal(FIXTURE_VERSION)});"
            "INSERT INTO template_version_state(version_id,status) VALUES "
            f"({_literal(version_id)},'active');"
            "INSERT INTO template_workspace(version_id,workspace_id,active) VALUES "
            f"({_literal(version_id)},{_literal(WORKSPACE_ID)},true)"
        )


def downgrade():
    raise RuntimeError("Story 2.1 migration is forward-only; preserve document and template data")
