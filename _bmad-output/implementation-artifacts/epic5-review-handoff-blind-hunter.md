Conduct a review of CONTENT.
Look for what's missing, not only what's wrong.
Compute your finding floor N from the diff file's size: N = min(floor(sqrt(kB) + 1), 10), where kB is the file's size in kilobytes. State the arithmetic in one line, then find at least N issues to fix or improve.
Output a Markdown list of findings only — no severity, priority, or ranking.
If the content is empty, stop and say so.
If you have zero findings, re-check and keep thinking; do not stop with an empty list.

CONTENT:
diff --git a/_bmad-output/implementation-artifacts/sprint-status.yaml b/_bmad-output/implementation-artifacts/sprint-status.yaml
index ed9450f..01a46d3 100644
--- a/_bmad-output/implementation-artifacts/sprint-status.yaml
+++ b/_bmad-output/implementation-artifacts/sprint-status.yaml
@@ -79,7 +79,7 @@
 # Timestamps use MM-DD-YYYY HH:MM.
 
 generated: "09-09-2026 04:44"
-last_updated: "09-29-2026 00:00"
+last_updated: "09-30-2026 00:00"
 project: eid
 project_key: NOKEY
 tracking_system: file-system
@@ -130,7 +130,7 @@ development_status:
   5-2-review-inspection: review # 源码与离线编译/typecheck 完成；测试、迁移、服务及浏览器 not-run
   5-3-issue-disposition: review # 静态/编译/typecheck 完成；测试、迁移、服务与浏览器 not-run
   5-4-technical-solution: review # 本地规则与来源约束源码完成；测试、实际企业标准核验和服务 not-run
-  5-5-prd-composition: backlog
+  5-5-prd-composition: review # 结构化需求与受控来源绑定源码完成；编译/typecheck 通过，测试及运行验收 not-run
   5-6-test-traceability: backlog
   5-7-measurable-requirements: backlog
   epic-5-retrospective: optional
diff --git a/contracts/document-ast-v1.schema.json b/contracts/document-ast-v1.schema.json
index f7a7ee0..e6c12c9 100644
--- a/contracts/document-ast-v1.schema.json
+++ b/contracts/document-ast-v1.schema.json
@@ -47,7 +47,8 @@
       {"if": {"properties": {"type": {"enum": ["warning", "code", "diagram", "citation"]}}}, "then": {"properties": {"content": {"$ref": "#/$defs/textContent"}}}},
       {"if": {"properties": {"type": {"const": "table"}}}, "then": {"properties": {"content": {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array", "maxItems": 256, "items": {"type": "array", "maxItems": 64, "items": {"$ref": "#/$defs/cell"}}}}, "additionalProperties": true}}}},
       {"if": {"properties": {"type": {"const": "figure"}}}, "then": {"properties": {"content": {"type": "object", "required": ["resource_id", "alt", "width", "height"], "properties": {"resource_id": {"$ref": "#/$defs/id"}, "alt": {"type": "string", "minLength": 1, "maxLength": 512}, "width": {"type": "integer", "minimum": 1, "maximum": 8192}, "height": {"type": "integer", "minimum": 1, "maximum": 8192}}, "additionalProperties": true}}}},
-      {"if": {"properties": {"type": {"const": "requirement"}}}, "then": {"properties": {"content": {"type": "object", "required": ["requirement_id", "statement", "verification_method", "source_refs"], "properties": {"requirement_id": {"type": "string", "minLength": 1, "maxLength": 2048}, "statement": {"type": "string", "minLength": 1, "maxLength": 2048}, "verification_method": {"type": "string", "minLength": 1, "maxLength": 2048}, "source_refs": {"type": "array", "maxItems": 128, "items": {"$ref": "#/$defs/id"}}}, "additionalProperties": true}}}},
+      {"if": {"properties": {"type": {"const": "requirement"}}}, "then": {"properties": {"content": {"type": "object", "description": "Draft fields may be empty; Review enforces type-specific completeness and current provenance.", "properties": {"requirement_id": {"type": "string", "maxLength": 4096}, "statement": {"type": "string", "maxLength": 2048}, "verification_method": {"type": "string", "maxLength": 2048}, "condition": {"type": "string", "maxLength": 2048}, "metric": {"type": "string", "maxLength": 2048}, "unit": {"type": "string", "maxLength": 2048}, "threshold": {"type": "string", "maxLength": 2048}, "source_refs": {"type": "array", "uniqueItems": true, "maxItems": 128, "items": {"$ref": "#/$defs/id"}}}, "additionalProperties": true}}}},
+      {"if": {"properties": {"type": {"enum": ["test_item", "test_case", "acceptance"]}}}, "then": {"properties": {"content": {"type": "object", "properties": {"links": {"type": "array", "maxItems": 128, "items": {"type": "object", "required": ["document_id", "version_id", "section_id", "block_id"], "properties": {"document_id": {"$ref": "#/$defs/id"}, "version_id": {"$ref": "#/$defs/id"}, "section_id": {"$ref": "#/$defs/id"}, "block_id": {"$ref": "#/$defs/id"}}, "additionalProperties": false}}}, "additionalProperties": true}}}},
       {"if": {"properties": {"type": {"const": "form"}}}, "then": {"properties": {"content": {"type": "object", "required": ["field_id", "label"], "properties": {"field_id": {"type": "string", "minLength": 1, "maxLength": 128}, "label": {"type": "string", "minLength": 1, "maxLength": 256}, "value": {"type": "string", "maxLength": 4096}}, "additionalProperties": true}}}}
     ], "additionalProperties": true}
   }
diff --git a/deployment/compose.yaml b/deployment/compose.yaml
index 6a1e6b4..5a0619a 100644
--- a/deployment/compose.yaml
+++ b/deployment/compose.yaml
@@ -8,7 +8,7 @@ x-runtime-environment: &runtime
   EID_OIDC_JWKS_URL: http://keycloak:8080/realms/eid-local/protocol/openid-connect/certs
   EID_WORKER_NODE_NAME: eid-worker@worker
   EID_ENVIRONMENT_MARKER: eid-local-dev-v1
-  EID_REQUIRED_SCHEMA_REVISION: 0028_review_dispositions
+  EID_REQUIRED_SCHEMA_REVISION: 0029_requirement_trace
   EID_WORKER_HEALTH_TIMEOUT_SECONDS: "2"
 services:
   postgres:
diff --git a/edw-api/src/edw_api/documents/claim_routes.py b/edw-api/src/edw_api/documents/claim_routes.py
index 2232996..a2b0327 100644
--- a/edw-api/src/edw_api/documents/claim_routes.py
+++ b/edw-api/src/edw_api/documents/claim_routes.py
@@ -62,6 +62,16 @@ class Cite(Strict):
     quoted_text: str = Field(min_length=1, max_length=4000)
 
 
+class CiteRequirement(Strict):
+    base_version_id: UUID
+    revision: int = Field(ge=1)
+    section_id: UUID
+    block_id: UUID
+    claim_id: UUID
+    link_id: UUID
+    quoted_text: str = Field(min_length=1, max_length=4000)
+
+
 def changed():
     raise ApiError(409, 'CITATION_RESELECT', '选区、版本或来源已变化；请重新选择正文')
 
@@ -359,6 +369,100 @@ def create_router(settings, verify):
         return {'data': {'claim_id': claim_id, 'links': output,
                          'state': 'current' if output and len(output) == len(links) and not conflict_seen else 'needs_review'}}
 
+    @router.post('/requirements/citations')
+    def cite_requirement(workspace_id: UUID, document_id: UUID, command: CiteRequirement,
+                         request: Request, response: Response, current=Depends(actor)):
+        response.headers['Cache-Control'] = 'no-store'
+        with database() as conn:
+            head(conn, current.subject, workspace_id, document_id, command.base_version_id,
+                 command.revision, edit=True)
+            link = conn.execute('''SELECT l.*,c.document_version_id,c.section_id AS claim_section,
+                c.block_id AS claim_block,c.statement AS claim_statement,c.claim_type FROM claim_evidence_link l
+                JOIN document_claim c ON c.id=l.claim_id AND c.workspace_id=l.workspace_id
+                WHERE l.id=%s AND l.claim_id=%s AND l.workspace_id=%s AND c.document_id=%s''',
+                (command.link_id, command.claim_id, workspace_id, document_id)).fetchone()
+            if not link or link['relation'] != 'supports' or link['claim_type'] != 'prd_requirement' or link['document_version_id'] != command.base_version_id:
+                changed()
+        row, item, proof = source_proof(settings, current.subject, workspace_id, document_id,
+                                        link['pack_id'], link['item_ordinal'])
+        with database() as conn:
+            head(conn, current.subject, workspace_id, document_id, command.base_version_id,
+                 command.revision, edit=True)
+            text = live(conn, current.subject, workspace_id, document_id, row, item, proof)
+            conflicting = conn.execute('''SELECT 1 FROM claim_evidence_link WHERE claim_id=%s
+                AND workspace_id=%s AND relation='conflicts' LIMIT 1''',
+                (command.claim_id, workspace_id)).fetchone()
+            anchor, _, _ = scope(conn, current.subject, workspace_id, document_id, None)
+            governed = decorate(conn, anchor, [dict(item)], workspace_id)
+            if (conflicting or not governed or any(g.get('conflict_id') for g in governed[0].get('governance', []))
+                    or command.quoted_text != link['quoted_text'] or command.quoted_text not in text
+                    or link['claim_statement'] not in command.quoted_text
+                    or command.section_id != link['claim_section'] or command.block_id != link['claim_block']
+                    or command.section_id != row['section_id'] or item['chain'] != 'attachment'):
+                changed()
+            current_claim = conn.execute('''SELECT statement,claim_type FROM document_claim
+                WHERE id=%s AND workspace_id=%s AND document_id=%s AND document_version_id=%s''',
+                (command.claim_id, workspace_id, document_id, command.base_version_id)).fetchone()
+            if not current_claim or current_claim['claim_type'] != 'prd_requirement' or current_claim['statement'] != link['claim_statement']:
+                changed()
+            facts, _ = editable_document(conn, current.subject, workspace_id, document_id)
+            previous = _document_row(conn, facts, workspace_id, document_id)
+            ast = previous['ast']
+            if ast['document']['metadata']['document_type'] not in ('prd', 'technical_requirements'):
+                changed()
+            section = next((s for s in ast['document']['sections'] if s['id'] == str(command.section_id)), None)
+            block = next((b for b in section['blocks'] if b['id'] == str(command.block_id)), None) if section else None
+            if (not block or block['type'] != 'requirement' or
+                    block['content'].get('statement') != link['claim_statement'] or
+                    not block['content']['statement']):
+                changed()
+            references = block['content'].get('source_refs', [])
+            if not isinstance(references, list):
+                changed()
+            from ..review.routes import citation_rows, source_safe
+            retained = citation_rows(conn, workspace_id, document_id, command.base_version_id)
+            # Reattest every carried binding under the current transaction and policy.
+            source_safe(conn, workspace_id, anchor, current.subject, retained)
+            retained_ids = {str(c['id']) for c in retained}
+            if not set(references) <= retained_ids:
+                changed()
+            carried_ids = {str(c['id']): str(uuid4()) for c in retained}
+            for existing_section in ast['document']['sections']:
+                for existing_block in existing_section['blocks']:
+                    if existing_block['type'] == 'requirement':
+                        if not set(existing_block['content'].get('source_refs', [])) <= retained_ids:
+                            changed()
+                        existing_block['content']['source_refs'] = [carried_ids.get(ref, ref)
+                            for ref in existing_block['content'].get('source_refs', [])]
+            for existing_citation in ast['document']['citations']:
+                if existing_citation['id'] in carried_ids:
+                    existing_citation['id'] = carried_ids[existing_citation['id']]
+                    existing_citation['needs_review'] = False
+            citation_id = uuid4()
+            block['content']['source_refs'] = [*(carried_ids[ref] for ref in references), str(citation_id)]
+            ast['document']['citations'].append({'id': str(citation_id), 'claim_id': str(command.claim_id),
+                'link_id': str(command.link_id), 'section_id': str(command.section_id),
+                'block_id': str(command.block_id), 'start_offset': 0,
+                'end_offset': len(link['claim_statement']), 'marker': '', 'needs_review': False})
+            saved = save_document(conn, current.subject, workspace_id, document_id,
+                SimpleNamespace(base_version_id=command.base_version_id, revision=command.revision,
+                                ast=DomainAst.model_validate(ast)),
+                request.state.request_id, request.state.trace_id, controlled_citation=True)
+            for old_id, new_id in carried_ids.items():
+                conn.execute('''INSERT INTO document_citation(id,workspace_id,document_id,document_version_id,
+                claim_id,link_id,section_id,block_id,start_offset,end_offset,selected_text,quoted_text,needs_review)
+                SELECT %s,workspace_id,document_id,%s,claim_id,link_id,section_id,block_id,
+                start_offset,end_offset,selected_text,quoted_text,false FROM document_citation
+                WHERE workspace_id=%s AND document_id=%s AND document_version_id=%s AND id=%s''',
+                (new_id, saved['version_id'], workspace_id, document_id, command.base_version_id, old_id))
+            conn.execute('''INSERT INTO document_citation(id,workspace_id,document_id,document_version_id,
+                claim_id,link_id,section_id,block_id,start_offset,end_offset,selected_text,quoted_text,needs_review)
+                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,false)''',
+                (citation_id, workspace_id, document_id, saved['version_id'], command.claim_id,
+                 command.link_id, command.section_id, command.block_id,
+                 len(link['claim_statement']), link['claim_statement'], command.quoted_text))
+            return {'data': saved}
+
     @router.post('/citations')
     def cite(workspace_id: UUID, document_id: UUID, command: Cite, request: Request, response: Response, current=Depends(actor)):
         response.headers['Cache-Control'] = 'no-store'
diff --git a/edw-api/src/edw_api/documents/claims.py b/edw-api/src/edw_api/documents/claims.py
index 6a81d2f..5fc9305 100644
--- a/edw-api/src/edw_api/documents/claims.py
+++ b/edw-api/src/edw_api/documents/claims.py
@@ -38,6 +38,16 @@ def candidates(text):
 def extract_claims(conn, workspace_id, document_id, version_id, ast):
     for section in ast['document']['sections']:
         for block in section['blocks']:
+            if block['type'] == 'requirement' and ast['document']['metadata']['document_type'] in ('prd', 'technical_requirements'):
+                statement = block['content'].get('statement', '')
+                if isinstance(statement, str) and statement.strip() and len(statement) <= 2048:
+                    conn.execute('''INSERT INTO document_claim(id,workspace_id,document_id,document_version_id,
+                        section_id,block_id,start_offset,end_offset,statement,claim_type,conditions,value,unit,
+                        critical,status,needs_review) VALUES (%s,%s,%s,%s,%s,%s,0,%s,%s,'prd_requirement','',%s,'',true,'unsupported',true)
+                        ON CONFLICT (document_version_id,block_id,start_offset,end_offset,claim_type) DO NOTHING''',
+                        (uuid4(), workspace_id, document_id, version_id, section['id'], block['id'],
+                         len(statement), statement, statement[:256]))
+                continue
             if block['type'] not in ('paragraph', 'heading', 'warning', 'code'):
                 continue
             text = block['content']['text']
diff --git a/edw-api/src/edw_api/documents/editor_domain.py b/edw-api/src/edw_api/documents/editor_domain.py
index 96dbc27..31a28b0 100644
--- a/edw-api/src/edw_api/documents/editor_domain.py
+++ b/edw-api/src/edw_api/documents/editor_domain.py
@@ -11,7 +11,7 @@ from uuid import UUID
 
 
 BLOCK_KINDS = frozenset({"paragraph", "heading", "table", "figure", "diagram",
-                         "requirement", "citation", "warning", "code", "form"})
+                         "requirement", "test_item", "test_case", "acceptance", "citation", "warning", "code", "form"})
 MAX_AST_BYTES = 512 * 1024
 MAX_TEXT = 100_000
 
@@ -187,10 +187,64 @@ def validate_ast(ast, *, expected_template_id, document_type, knowledge_scope,
                 if kind == "paragraph" and content.get("list") not in (None, "bullet", "ordered"):
                     raise InvalidAst("Invalid list style")
             elif kind == "requirement":
-                for field in ("requirement_id", "statement", "verification_method"):
-                    _text(content.get(field), 2048, empty=False)
+                old_block = next((entry for old in original_sections for entry in old['blocks']
+                                  if entry.get('id') == block_id and entry.get('type') == 'requirement'), None)
+                old_content = old_block.get('content', {}) if old_block else {}
+                prd_fields = ("requirement_id", "name", "role", "scenario", "prerequisites",
+                              "normal_flow", "exception_flow", "rules", "inputs", "outputs",
+                              "permissions", "nfr", "acceptance_criteria")
+                if document_type == "prd":
+                    if isinstance(content.get('requirement_id'), str) and content['requirement_id'].strip():
+                        identifier = content['requirement_id'].strip().casefold()
+                        for prior in sections[:index]:
+                            for existing in prior.get('blocks', []):
+                                other = existing.get('content', {}).get('requirement_id')
+                                if existing.get('type') == 'requirement' and isinstance(other, str) and other.strip().casefold() == identifier:
+                                    raise InvalidAst("Duplicate PRD requirement ID")
+                        for existing in section.get('blocks', [])[:block_index]:
+                            other = existing.get('content', {}).get('requirement_id')
+                            if existing.get('type') == 'requirement' and isinstance(other, str) and other.strip().casefold() == identifier:
+                                raise InvalidAst("Duplicate PRD requirement ID")
+                    for field in prd_fields:
+                        if field in content:
+                            _text(content[field], 4096)
+                    if content.get("requirement_id") and not re.fullmatch(
+                            r"FR-[A-Za-z0-9][A-Za-z0-9._-]{0,126}", content["requirement_id"]) and content.get('requirement_id') != old_content.get('requirement_id'):
+                        raise InvalidAst("Invalid PRD requirement ID")
+                    _text(content.get("statement", ""), 2048)
+                    _text(content.get("verification_method", ""), 2048)
+                elif document_type == 'technical_requirements':
+                    for field in ('requirement_id', 'statement', 'condition', 'metric', 'unit',
+                                  'threshold', 'verification_method'):
+                        _text(content.get(field, ''), 2048)
+                    if old_content.get('source_refs') and any(
+                            content.get(field) != old_content.get(field)
+                            for field in ('condition', 'metric', 'unit', 'threshold')):
+                        raise InvalidAst('Source-backed threshold cannot be replaced without new provenance')
+                else:
+                    for field in ("requirement_id", "statement", "verification_method"):
+                        _text(content.get(field), 2048, empty=False)
                 for ref in _array(content.get("source_refs"), 128):
                     _id(ref)
+                if document_type in ("prd", "technical_requirements"):
+                    refs = content.get('source_refs', [])
+                    if len(set(refs)) != len(refs):
+                        raise InvalidAst("Duplicate PRD source reference")
+                    previous_refs = old_content.get('source_refs', [])
+                    if not controlled_citation and content.get('source_refs', []) != previous_refs:
+                        raise InvalidAst("PRD sources require a controlled command")
+            elif kind in ('test_item', 'test_case', 'acceptance'):
+                if document_type != 'test_plan':
+                    raise InvalidAst('Test blocks require a test plan')
+                for field in ('identifier', 'statement', 'condition', 'metric', 'unit',
+                              'threshold', 'verification_method'):
+                    _text(content.get(field, ''), 2048)
+                for ref in _array(content.get('links', []), 128):
+                    ref = _object(ref)
+                    if set(ref) != {'document_id', 'version_id', 'section_id', 'block_id'}:
+                        raise InvalidAst('A trace requires exact version and block locators')
+                    for value in ref.values():
+                        _id(value)
             elif kind == "table":
                 for row in _array(content.get("rows"), 256):
                     for cell in _array(row, 64):
diff --git a/edw-api/src/edw_api/documents/editor_repository.py b/edw-api/src/edw_api/documents/editor_repository.py
index a376aad..8469d62 100644
--- a/edw-api/src/edw_api/documents/editor_repository.py
+++ b/edw-api/src/edw_api/documents/editor_repository.py
@@ -104,6 +104,8 @@ def save_document(conn, subject, workspace_id, document_id, command, request_id,
                                  controlled_citation=controlled_citation)
     except InvalidAst as exc:
         raise ApiError(422, "INVALID_DOCUMENT_AST", str(exc)) from exc
+    from .traceability import validate_links, project
+    validate_links(conn, subject, workspace_id, document_id, ast, previous['ast'])
     media = conn.execute(
         "SELECT id,width,height FROM document_media WHERE document_id=%s AND workspace_id=%s "
         "AND id=ANY(%s::uuid[])",
@@ -160,6 +162,7 @@ def save_document(conn, subject, workspace_id, document_id, command, request_id,
     )
     from .claims import extract_claims
     extract_claims(conn, workspace_id, document_id, version_id, ast)
+    project(conn, workspace_id, document_id, version_id, ast)
     # Old version findings remain for provenance, but cannot certify the new head.
     conn.execute("UPDATE document_claim SET needs_review=true WHERE workspace_id=%s AND document_id=%s AND document_version_id<>%s", (workspace_id, document_id, version_id))
     conn.execute("UPDATE document_citation SET needs_review=true WHERE workspace_id=%s AND document_id=%s AND document_version_id<>%s", (workspace_id, document_id, version_id))
diff --git a/edw-api/src/edw_api/documents/editor_routes.py b/edw-api/src/edw_api/documents/editor_routes.py
index 18ce86c..7aaea82 100644
--- a/edw-api/src/edw_api/documents/editor_routes.py
+++ b/edw-api/src/edw_api/documents/editor_routes.py
@@ -89,6 +89,29 @@ def create_router(settings, verify):
         response.headers["Cache-Control"] = "no-store"
         return DocumentResponse(data=result)
 
+    @router.get('/documents/{document_id}/test-coverage')
+    def test_coverage(workspace_id: UUID, document_id: UUID, response: Response, current=Depends(actor)):
+        response.headers['Cache-Control'] = 'no-store'
+        with database() as conn:
+            checked(conn, current.subject, workspace_id, 'resource:read', document_id)
+            row = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
+                               (document_id, workspace_id)).fetchone()
+            if not row:
+                raise AccessDenied()
+            value = read_version(conn, current.subject, workspace_id, document_id, row['head_version_id'])
+            from .traceability import coverage
+            result = coverage(conn, current.subject, workspace_id, value['ast'])
+            reverse = []
+            for link in conn.execute('''SELECT t.* FROM requirement_trace t JOIN document d
+                    ON d.id=t.document_id AND d.head_version_id=t.version_id
+                    WHERE t.workspace_id=%s AND t.target_document_id=%s''', (workspace_id, document_id)).fetchall():
+                try:
+                    read_version(conn, current.subject, workspace_id, link['document_id'], link['version_id'])
+                    reverse.append({**dict(link), 'state': 'current' if link['target_version_id'] == row['head_version_id'] else 'stale'})
+                except (AccessDenied, ApiError):
+                    continue
+            return {'data': {**result, 'reverse': reverse}}
+
     @router.post("/documents/{document_id}/images", status_code=201)
     async def upload(workspace_id: UUID, document_id: UUID, request: Request,
                      current=Depends(actor)):
diff --git a/edw-api/src/edw_api/review/routes.py b/edw-api/src/edw_api/review/routes.py
index ed83ea1..61ee181 100644
--- a/edw-api/src/edw_api/review/routes.py
+++ b/edw-api/src/edw_api/review/routes.py
@@ -61,7 +61,7 @@ def current(conn, subject, workspace_id, document_id, *, review=False):
 
 
 def source_safe(conn, workspace_id, anchor, subject, citations):
-    from ..knowledge.governance import local_source
+    from ..knowledge.governance import local_source, decorate
     for citation in citations:
         if citation['needs_review'] or citation['chain'] != 'attachment':
             raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')
@@ -86,10 +86,13 @@ def source_safe(conn, workspace_id, anchor, subject, citations):
             raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验') from exc
         if text != citation['excerpt'] or citation['quoted_text'] not in text:
             raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')
+        governed = decorate(conn, anchor, [dict(hit)], workspace_id)
+        if not governed or any(g.get('conflict_id') for g in governed[0].get('governance', [])):
+            raise ApiError(409, 'REVIEW_SOURCE_CHANGED', '引用来源需要重新核验')
 
 
 def citation_rows(conn, workspace_id, document_id, version_id):
-    return conn.execute('''SELECT c.section_id,c.block_id,c.selected_text,c.needs_review,
+    return conn.execute('''SELECT c.id,c.section_id,c.block_id,c.selected_text,c.needs_review,
         l.source_id,l.source_version,l.chain,l.chunk_hash,l.locator,l.quoted_text,l.item_ordinal,
         i.excerpt,p.content,p.content_hash AS pack_hash FROM document_citation c JOIN claim_evidence_link l
         ON l.id=c.link_id AND l.workspace_id=c.workspace_id
@@ -124,7 +127,7 @@ def snapshot(conn, subject, workspace_id, document_id, version_id, ast):
 
 
 def source_snapshot(citations):
-    return [{key: row[key] for key in ('section_id', 'block_id', 'selected_text', 'needs_review',
+    return [{key: row[key] for key in ('id', 'section_id', 'block_id', 'selected_text', 'needs_review',
             'source_id', 'source_version', 'chain', 'chunk_hash', 'locator', 'quoted_text',
             'item_ordinal', 'excerpt')} for row in citations]
 
@@ -188,7 +191,7 @@ def issue_filters(severity, section_id, status, keyword):
     return severity, section_id, status, keyword.strip() or None if keyword else None
 
 
-def filtered_issues(conn, run_id, filters, *, sources_current, current_version_id=None, offset=0, limit=100):
+def filtered_issues(conn, run_id, filters, *, sources_current, citations=(), current_version_id=None, offset=0, limit=100):
     severity, section_id, status, keyword = filters
     # The keyword predicate must use exactly the same safe fields as issue_view.
     # Source-linked quotes are excluded here; their authorization is checked per issue later.
@@ -199,11 +202,16 @@ def filtered_issues(conn, run_id, filters, *, sources_current, current_version_i
              WHEN d.action='handled' THEN 'HANDLED' WHEN d.action='reject' THEN 'REJECTED'
              WHEN d.action='modify' THEN 'MODIFY' WHEN d.action='accept' THEN 'PENDING_RECHECK'
              END,'OPEN')=%s)
-        AND (%s::text IS NULL OR ((%s::boolean AND i.source_id IS NULL AND i.quote ILIKE '%%' || %s || '%%')
+        AND (%s::text IS NULL OR ((%s::boolean AND (i.source_id IS NULL OR EXISTS
+              (SELECT 1 FROM jsonb_to_recordset(%s::jsonb) AS c(source_id text,section_id uuid,block_id uuid)
+               WHERE c.source_id=i.source_id AND c.section_id=i.section_id AND c.block_id=i.block_id))
+              AND i.quote ILIKE '%%' || %s || '%%')
              OR i.impact ILIKE '%%' || %s || '%%' OR i.suggestion ILIKE '%%' || %s || '%%'
              OR i.rule_id ILIKE '%%' || %s || '%%'))'''
     params = (run_id, severity, severity, section_id, section_id, status, current_version_id, status,
-               keyword, sources_current, keyword, keyword, keyword, keyword)
+               keyword, sources_current, Jsonb([{'source_id': str(c['source_id']),
+                   'section_id': str(c['section_id']), 'block_id': str(c['block_id'])} for c in citations]),
+               keyword, keyword, keyword, keyword)
     tables = ''' FROM review_issue i LEFT JOIN LATERAL
         (SELECT * FROM review_disposition WHERE issue_id=i.id ORDER BY (action='handled') DESC,created_at DESC,id DESC LIMIT 1)
         d ON true LEFT JOIN review_run rr ON rr.id=d.recheck_run_id '''
@@ -286,7 +294,7 @@ def version_comparison(pinned, current_ast):
 def same_defect(issue, other):
     return (issue['category'] == other['category'] and issue['rule_id'] == other['rule_id']
             and issue['section_id'] == other['section_id'] and issue['block_id'] == other['block_id']
-            and issue['claim_id'] == other['claim_id'])
+            and ((issue.get('details') or {}).get('field') == (other.get('details') or {}).get('field')))
 
 
 def disposition_digest(command):
@@ -361,7 +369,7 @@ def disposition(conn, subject, workspace_id, document_id, run_id, issue_id, comm
                                  initial, views, None)
         patch_id, result_id, result_revision = patch['data']['id'], patch['data']['version_id'], patch['data']['revision']
     if command.action == 'handled':
-        if earlier and earlier[0]['action'] != 'accept':
+        if earlier and earlier[0]['action'] not in ('accept', 'modify'):
             raise ApiError(409, 'REVIEW_ALREADY_DISPOSED', '既有决议保持未解决；须对新审校问题作出处置')
         if earlier and earlier[0]['action'] == 'accept' and (
                 row['document_version_id'] == head['head_version_id'] or
@@ -470,6 +478,23 @@ def execute(settings, workspace_id, document_id, run_id):
                 sources_current = True
                 outcomes, issues = inspect(head['ast'], fresh_structure, fresh_claims,
                     project_facts=fresh_facts, citations=fresh_citations)
+                if head['ast']['document']['metadata']['document_type'] == 'test_plan':
+                    from ..documents.traceability import coverage
+                    trace = coverage(conn, job['subject'], workspace_id, head['ast'])
+                    defects = [*trace['unlinked'],
+                               *(link for link in trace['links'] if link['state'] != 'current'),
+                               *(entry for entry in trace['requirements'] if entry['state'] != 'covered')]
+                    for defect in defects:
+                        # Baseline locators belong to a different document. Keep them
+                        # in details; never present them as blocks of this test plan.
+                        external = 'document_id' in defect
+                        issues.append({'id': str(uuid4()), 'category': 'requirement',
+                            'rule_id': 'test_coverage_' + defect.get('state', 'unlinked'), 'severity': 'high',
+                            'section_id': None if external else defect['section_id'],
+                            'block_id': None if external else defect['block_id'],
+                            'claim_id': None, 'source_id': None, 'quote': '测试追踪待核验',
+                            'impact': '需求覆盖缺失、冗余或版本/阈值不一致',
+                            'suggestion': '核对当前基线与测试链，不替换批准阈值', 'details': defect})
             except ApiError as exc:
                 if exc.code != 'REVIEW_SOURCE_CHANGED':
                     raise
@@ -603,9 +628,14 @@ def create_router(settings, verify):
                 current_actor.subject, workspace_id, document_id, results)
             ast, sources_current, citations = inspection(conn, row, head, current_actor.subject, workspace_id, document_id)
             issues, total = filtered_issues(conn, run_id, filters, sources_current=sources_current,
+                                             citations=citations,
                                             current_version_id=head['head_version_id'], offset=offset)
             visible = [issue_view(item, ast, sources_current=sources_current, citations=citations,
-                                   current_version_id=head['head_version_id']) for item in issues]
+                                    current_version_id=head['head_version_id']) for item in issues]
+            coverage_metric = {'numerator': None, 'denominator': None, 'state': 'unevaluated'}
+            if payload['current_eligible'] and ast['document']['metadata']['document_type'] == 'test_plan':
+                from ..documents.traceability import coverage
+                coverage_metric = coverage(conn, current_actor.subject, workspace_id, ast)
             # A ratio is defined only for this concrete, bounded result set's count, not a quality score.
             return {'data': {**payload, 'results': [dict(item) for item in results],
                              'issues': visible, 'issue_count': total, 'returned_count': len(visible),
@@ -617,8 +647,7 @@ def create_router(settings, verify):
                                                          'state': 'count'},
                                          'score': {'numerator': None, 'denominator': None,
                                                    'state': 'unevaluated'},
-                                         'coverage': {'numerator': None, 'denominator': None,
-                                                      'state': 'unevaluated'}},
+                                          'coverage': coverage_metric},
                              'version': {'id': row['document_version_id'], 'revision': row['document_revision'],
                                          'current_id': head['head_version_id'], 'current_revision': head['revision'],
                                          'comparison': version_comparison(ast, head['ast'])}}}
diff --git a/edw-api/src/edw_api/review/rules.py b/edw-api/src/edw_api/review/rules.py
index 51b63cf..8e5441d 100644
--- a/edw-api/src/edw_api/review/rules.py
+++ b/edw-api/src/edw_api/review/rules.py
@@ -5,7 +5,11 @@ from uuid import uuid4
 
 CATEGORIES = ('structure', 'fact', 'requirement', 'technical', 'quality',
               'consistency', 'style', 'safety')
-RULE_VERSION = 'local-review-3'
+RULE_VERSION = 'local-review-5'
+PRD_FIELDS = {'requirement_id': 'FR-ID', 'name': '名称', 'role': '角色', 'scenario': '场景',
+              'prerequisites': '前置条件', 'normal_flow': '正常流程', 'exception_flow': '异常流程',
+              'rules': '业务规则', 'inputs': '输入', 'outputs': '输出', 'permissions': '权限',
+              'nfr': '非功能要求', 'acceptance_criteria': '验收条件'}
 VAGUE = re.compile(r'\b(?:fast|robust|scalable|high.performance)\b|快速|高效|稳定|先进|适当', re.I)
 STANDARD_HINT = re.compile(r'标准|\bstandard\b', re.I)
 STANDARD = re.compile(r'\b(?:GB(?:/T)?|ISO|IEC|IEEE)\s*[- ]?\s*\d{3,6}(?:[.\-]\d+)*(?:[-:]\d{4})?\b', re.I)
@@ -41,8 +45,10 @@ def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_
     terms = defaultdict(list)
     facts = {fact['key'].casefold(): fact for fact in project_facts if fact.get('confirmed')}
     technical = ast['document'].get('metadata', {}).get('document_type') == 'technical_solution'
+    prd = ast['document'].get('metadata', {}).get('document_type') == 'prd'
     citations = tuple(citations)
     claims = tuple(claims)
+    requirement_ids = defaultdict(list)
 
     def add(category, rule, severity, section, block, quote, impact, suggestion, **details):
         issues.append({'id': str(uuid4()), 'category': category, 'rule_id': rule,
@@ -77,9 +83,73 @@ def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_
         for block in section['blocks']:
             content = block.get('content', {})
             text = content.get('text') or content.get('statement') or ''
+            # Scan every nested textual field, including tables and structured flows.
+            def strings(value, path=''):
+                if isinstance(value, str):
+                    yield path, value
+                elif isinstance(value, dict):
+                    for key, entry in value.items():
+                        yield from strings(entry, f'{path}.{key}' if path else key)
+                elif isinstance(value, list):
+                    for index, entry in enumerate(value):
+                        yield from strings(entry, f'{path}[{index}]')
+            for field, value in strings(content):
+                if SECRET.search(value):
+                    add('safety', 'sensitive_literal', 'critical', section, block, '[REDACTED]',
+                        '结构字段疑似包含敏感凭据', '移除凭据并重新核验', field=field)
+                if field not in ('text', 'statement') and VAGUE.search(value):
+                    add('quality', 'vague_statement', 'medium', section, block, VAGUE.search(value).group(),
+                        '结构字段缺少可衡量条件', '补充有来源的指标和验证方式', field=field)
             if not isinstance(text, str):
                 continue
             if block['type'] == 'requirement':
+                if ast['document'].get('metadata', {}).get('document_type') == 'technical_requirements':
+                    for field in ('requirement_id', 'statement', 'condition', 'metric', 'unit',
+                                  'threshold', 'verification_method'):
+                        if not isinstance(content.get(field), str) or not content[field].strip():
+                            add('requirement', 'measurable_missing_field', 'high', section, block, field,
+                                '技术要求不可测量', '补齐有来源的条件、指标、单位、阈值和验证方法', field=field)
+                    for field in ('condition', 'metric', 'unit', 'threshold'):
+                        value = content.get(field)
+                        if value and not any(str(c.get('id')) in content.get('source_refs', [])
+                                and str(c.get('section_id')) == section['id']
+                                and str(c.get('block_id')) == block['id']
+                                and not c.get('needs_review') and c.get('chain') == 'attachment'
+                                and value in c.get('quoted_text', '') for c in citations):
+                            add('fact', 'unsupported_threshold', 'high', section, block, value,
+                                '测量字段没有当前来源依据', '保留待确认，不生成替代数值', field=field)
+                if prd:
+                    for field, label in {**PRD_FIELDS, 'statement': '需求陈述'}.items():
+                        value = content.get(field)
+                        if not isinstance(value, str) or not value.strip():
+                            add('requirement', 'prd_missing_field', 'high', section, block, label,
+                                'PRD 结构化需求字段缺失', '在需求块填写该字段并保存', field=field)
+                    identifier = content.get('requirement_id')
+                    if isinstance(identifier, str) and identifier.strip():
+                        requirement_ids[identifier.strip().casefold()].append((section, block))
+                        if not re.fullmatch(r'FR-[A-Za-z0-9][A-Za-z0-9._-]{0,126}', identifier):
+                            add('requirement', 'prd_invalid_id', 'high', section, block, identifier,
+                                'PRD 需求编号格式待修正', '使用稳定且唯一的 FR-ID', field='requirement_id')
+                    refs = content.get('source_refs', [])
+                    if not isinstance(refs, list):
+                        refs = []
+                    elif len(refs) != len(set(str(ref) for ref in refs)):
+                        add('requirement', 'prd_duplicate_source_ref', 'medium', section, block, text,
+                            '需求重复关联同一来源', '核对并保留唯一引用')
+                    for ref in refs:
+                        matches = [citation for citation in citations if str(citation.get('id')) == str(ref)]
+                        if not any(str(c.get('section_id')) == section['id'] and
+                                   str(c.get('block_id')) == block['id'] and
+                                   c.get('selected_text') == content.get('statement') and
+                                   isinstance(c.get('selected_text'), str) and bool(c.get('selected_text')) and
+                                   c['selected_text'] in c.get('quoted_text', '') and
+                                   not c.get('needs_review') and c.get('chain') == 'attachment'
+                                   for c in matches):
+                            add('fact', 'prd_source_unverified', 'high', section, block, str(ref),
+                                '需求来源不属于当前授权区块引用', '重新关联当前可核验的引用', source_ref=str(ref))
+                    if not refs:
+                        add('fact', 'prd_source_unverified', 'high', section, block, text,
+                            '需求缺少当前授权的来源关联', '为需求关联当前区块引用')
                 if not content.get('verification_method'):
                     add('requirement', 'missing_verification', 'high', section, block, text,
                         '需求缺少验证方法', '填写验证方法')
@@ -93,9 +163,6 @@ def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_
             if STANDARD_HINT.search(text) and not STANDARD.search(text):
                 add('technical', 'standard_identifier', 'medium', section, block, text,
                     '标准标识无法精确核对', '提供现行适用的标准编号和来源')
-            for match in SECRET.finditer(text):
-                add('safety', 'sensitive_literal', 'critical', section, block, '[REDACTED]',
-                    '正文疑似包含敏感凭据', '移除凭据并按安全流程核验')
             for match in METRIC.finditer(text):
                 prefix = text[max(0, match.start() - 45):match.start()]
                 key = re.split(r'[。；;，,\n]', prefix)[-1].strip(' :：\t').casefold()
@@ -147,6 +214,13 @@ def inspect(ast, template_structure=None, claims=(), *, project_facts=(), stale_
                 add('style', 'text_format', 'low', section, block, '[格式片段]',
                     '文字格式不一致', '核对段落空格或重复标点')
 
+    for identifier, entries in requirement_ids.items():
+        if len(entries) > 1:
+            for section, block in entries:
+                add('requirement', 'prd_duplicate_id', 'high', section, block, identifier,
+                    'PRD 的 FR-ID 重复', '人工核对来源后分配唯一编号',
+                    counterparts=[{'section_id': other['id'], 'block_id': peer['id']}
+                                  for other, peer in entries if peer['id'] != block['id']])
     for key, entries in candidates.items():
         if len({value for value, _, _ in entries}) > 1:
             for value, section, block in entries:
diff --git a/edw-web/src/features/knowledge/ClaimPanel.tsx b/edw-web/src/features/knowledge/ClaimPanel.tsx
index 090edec..e37eac8 100644
--- a/edw-web/src/features/knowledge/ClaimPanel.tsx
+++ b/edw-web/src/features/knowledge/ClaimPanel.tsx
@@ -2,7 +2,7 @@ import {useEffect,useRef,useState} from 'react';
 import type {WorkspaceAccess} from '../../app/access-api';
 import {bindClaim,declareClaim,extractClaims,getClaims,getTrace,type Bookmark,type Claim,type Trace} from './claim-api';
 
-export default function ClaimPanel({current,documentId,bookmark,onCite,onBindReady}:{current:WorkspaceAccess;documentId:string;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>;onBindReady?:(handler:((packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>void)|null)=>void}){
+export default function ClaimPanel({current,documentId,bookmark,onCite,requirementTarget,onCiteRequirement,onBindReady}:{current:WorkspaceAccess;documentId:string;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>;requirementTarget?:{section_id:string;block_id:string}|null;onCiteRequirement?:(claimId:string,linkId:string,quote:string)=>Promise<void>;onBindReady?:(handler:((packId:string,index:number,excerpt:string,relation:'supports'|'conflicts'|'contextual')=>void)|null)=>void}){
  const [claims,setClaims]=useState<Claim[]>([]);const [selected,setSelected]=useState('');const [trace,setTrace]=useState<Trace|null>(null);
  const [version,setVersion]=useState('');const [revision,setRevision]=useState(0);const [message,setMessage]=useState('');
  const [kind,setKind]=useState('unknown');const [value,setValue]=useState('');const [conditions,setConditions]=useState('');const [unit,setUnit]=useState('');const request=useRef<AbortController|null>(null);const generation=useRef(0);
@@ -36,6 +36,6 @@ export default function ClaimPanel({current,documentId,bookmark,onCite,onBindRea
   {bookmark&&<p role="status">已固定选区：{bookmark.selected_text}（版本 {bookmark.revision}）</p>}
   <button onClick={scan}>扫描本版确定性候选</button>{bookmark&&<div className="knowledge-controls"><label>声明类型（可保留未知类型）<input value={kind} maxLength={80} onChange={event=>setKind(event.target.value)}/></label><label>条件<input value={conditions} maxLength={512} onChange={event=>setConditions(event.target.value)}/></label><label>值<input value={value} maxLength={256} onChange={event=>setValue(event.target.value)}/></label><label>单位<input value={unit} maxLength={64} onChange={event=>setUnit(event.target.value)}/></label><button onClick={declare}>声明所选 Claim · 待确认</button></div>}
   <label>选择 Claim / 问题<select aria-label="选择 Claim" value={selected} onChange={event=>choose(event.target.value)}><option value="">清空追溯</option>{claims.map(item=><option key={item.id} value={item.id}>{item.claim_type} · {item.statement} · {item.status}{item.needs_review?' · 待复核':''}</option>)}</select></label>
-  {message&&<p role="alert">{message}</p>}{selected&&<div aria-label="当前 Claim 追溯">{trace?.state==='needs_review'&&<p>部分来源不可用或存在冲突，仍待复核；旧快照不授权。</p>}{trace?.links.map(link=><article key={link.id} className="knowledge-viewer"><p>{link.quoted_text}</p><small>{link.relation} · {link.source_id} · 版本 {link.version} · {link.locator} · chunk {link.chunk_hash}</small>{bookmark&&onCite&&trace.state==='current'&&link.can_cite&&link.relation==='supports'&&<button disabled={claims.find(x=>x.id===selected)?.block_id!==bookmark.block_id} onClick={()=>{request.current?.abort();generation.current++;setTrace(null);void onCite(selected,link.id,link.quoted_text).then(()=>load()).catch(()=>{setMessage('引用未确认；请核对版本并重新选择');load()})}}>确认插入当前选区</button>}</article>)}</div>}
+   {message&&<p role="alert">{message}</p>}{selected&&<div aria-label="当前 Claim 追溯">{trace?.state==='needs_review'&&<p>部分来源不可用或存在冲突，仍待复核；旧快照不授权。</p>}{trace?.links.map(link=><article key={link.id} className="knowledge-viewer"><p>{link.quoted_text}</p><small>{link.relation} · {link.source_id} · 版本 {link.version} · {link.locator} · chunk {link.chunk_hash}</small>{bookmark&&onCite&&trace.state==='current'&&link.can_cite&&link.relation==='supports'&&<button disabled={claims.find(x=>x.id===selected)?.block_id!==bookmark.block_id} onClick={()=>{request.current?.abort();generation.current++;setTrace(null);void onCite(selected,link.id,link.quoted_text).then(()=>load()).catch(()=>{setMessage('引用未确认；请核对版本并重新选择');load()})}}>确认插入当前选区</button>}{requirementTarget&&onCiteRequirement&&trace?.state==='current'&&link.can_cite&&link.relation==='supports'&&claims.some(x=>x.id===selected&&x.claim_type==='prd_requirement'&&x.section_id===requirementTarget.section_id&&x.block_id===requirementTarget.block_id)&&<button onClick={()=>{request.current?.abort();generation.current++;setTrace(null);void onCiteRequirement(selected,link.id,link.quoted_text).then(()=>load()).catch(()=>{setMessage('需求来源未确认；请核对版本与授权');load()})}}>绑定当前 PRD 需求引用</button>}</article>)}</div>}
  </section>;
 }
diff --git a/edw-web/src/features/knowledge/KnowledgePanel.tsx b/edw-web/src/features/knowledge/KnowledgePanel.tsx
index 827e3b7..ea24814 100644
--- a/edw-web/src/features/knowledge/KnowledgePanel.tsx
+++ b/edw-web/src/features/knowledge/KnowledgePanel.tsx
@@ -8,7 +8,7 @@ import type {Bookmark} from './claim-api';
 
 const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
 const labels:Record<Category,string>={all:'全部',attachment:'附件',enterprise:'企业',golden:'Golden'};
-export default function KnowledgePanel({current,documentId,onReject,onRefresh,compact=false,bookmark,onCite}:{current:WorkspaceAccess;documentId?:string;onReject:(error:unknown)=>void;onRefresh:()=>void;compact?:boolean;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>}){
+export default function KnowledgePanel({current,documentId,onReject,onRefresh,compact=false,bookmark,onCite,requirementTarget,onCiteRequirement}:{current:WorkspaceAccess;documentId?:string;onReject:(error:unknown)=>void;onRefresh:()=>void;compact?:boolean;bookmark?:Bookmark|null;onCite?:(claimId:string,linkId:string,quote:string)=>Promise<void>;requirementTarget?:{section_id:string;block_id:string}|null;onCiteRequirement?:(claimId:string,linkId:string,quote:string)=>Promise<void>}){
  const [contextId,setContextId]=useState(documentId??'');const [query,setQuery]=useState('');const [category,setCategory]=useState<Category>('all');
  const [classification,setClassification]=useState('');const [version,setVersion]=useState('');const [contextVersion,setContextVersion]=useState('');
  const [result,setResult]=useState<SearchResult|null>(null);const [selected,setSelected]=useState<Hit|null>(null);
@@ -56,7 +56,7 @@ export default function KnowledgePanel({current,documentId,onReject,onRefresh,co
  return <section className={`knowledge-panel${compact?' compact':''}`} aria-label="授权知识检索" data-testid="knowledge-panel">
   {!compact&&<header className="page-header"><h1>知识库 · 授权检索</h1></header>}
   {documentId&&<EvidencePanel key={`${documentId}:${current.actor_id}:${current.policy_epoch.join(':')}`} current={current} documentId={documentId} onReject={onReject} onRefresh={onRefresh} onSelectionChange={()=>{reset();setClaimGeneration(n=>n+1)}} onBind={(packId,index,excerpt,relation)=>binder.current?.(packId,index,excerpt,relation)}/>}
-  {documentId&&<ClaimPanel key={`${documentId}:${claimGeneration}`} current={current} documentId={documentId} bookmark={bookmark} onCite={onCite} onBindReady={handler=>{binder.current=handler}}/>}
+   {documentId&&<ClaimPanel key={`${documentId}:${claimGeneration}`} current={current} documentId={documentId} bookmark={bookmark} onCite={onCite} requirementTarget={requirementTarget} onCiteRequirement={onCiteRequirement} onBindReady={handler=>{binder.current=handler}}/>}
   <p>仅查询当前项目内有权的真实来源；发现页标题和模型常识不是证据。检索可能不完整。</p>
   <div className="knowledge-controls"><label>上下文文档 ID<input aria-label="上下文文档 ID" value={contextId} readOnly={!!documentId} onChange={e=>{reset();setContextId(e.target.value)}} placeholder="当前项目文档 UUID"/></label>
    <label>关键词或精确标识符<input aria-label="知识查询" value={query} maxLength={128} onChange={e=>{reset();setQuery(e.target.value)}} onKeyDown={e=>{if(e.key==='Enter')submit()}}/></label>
diff --git a/edw-web/src/features/knowledge/claim-api.ts b/edw-web/src/features/knowledge/claim-api.ts
index 1c7066a..e2315f0 100644
--- a/edw-web/src/features/knowledge/claim-api.ts
+++ b/edw-web/src/features/knowledge/claim-api.ts
@@ -24,9 +24,12 @@ export async function getTrace(current:WorkspaceAccess,documentId:string,claimId
 }
 export async function extractClaims(current:WorkspaceAccess,documentId:string,signal:AbortSignal){return call(current,documentId,'/claims/extract',signal,{})}
 export async function declareClaim(current:WorkspaceAccess,documentId:string,body:Bookmark&{claim_type:string;conditions:string;value:string;unit:string;critical:boolean},signal:AbortSignal){
- const {selected_text:_,...command}=body;return call(current,documentId,'/claims',signal,command);
+ const command=Object.fromEntries(Object.entries(body).filter(([key])=>key!=='selected_text'));return call(current,documentId,'/claims',signal,command);
 }
 export async function bindClaim(current:WorkspaceAccess,documentId:string,claimId:string,body:{base_version_id:string;revision:number;pack_id:string;item_ordinal:number;relation:'supports'|'conflicts'|'contextual';quoted_text:string},signal:AbortSignal){return call(current,documentId,`/claims/${claimId}/links`,signal,body)}
 export async function citeClaim(current:WorkspaceAccess,documentId:string,body:Bookmark&{claim_id:string;link_id:string;quoted_text:string},signal:AbortSignal):Promise<DocumentData>{
- return document(await call(current,documentId,'/citations',signal,body),current,documentId);
+  return document(await call(current,documentId,'/citations',signal,body),current,documentId);
+}
+export async function citeRequirement(current:WorkspaceAccess,documentId:string,body:{base_version_id:string;revision:number;section_id:string;block_id:string;claim_id:string;link_id:string;quoted_text:string},signal:AbortSignal):Promise<DocumentData>{
+ return document(await call(current,documentId,'/requirements/citations',signal,body),current,documentId);
 }
diff --git a/edw-web/src/features/templates/DomainEditor.tsx b/edw-web/src/features/templates/DomainEditor.tsx
index 51da10f..de06d85 100644
--- a/edw-web/src/features/templates/DomainEditor.tsx
+++ b/edw-web/src/features/templates/DomainEditor.tsx
@@ -8,15 +8,17 @@ import type {WorkspaceAccess} from '../../app/access-api';
 import {getDocument,getImage,saveDocument,uploadImage,TemplateError,type DocumentData,type SaveTiming} from './template-api';
 import {sameDomainValue} from './domain-merge';
 import VersionHistory from './VersionHistory';
+import TestTraceEditor from './TestTraceEditor';
 import ProjectContext from './ProjectContext';
 import OutlineEditor from './OutlineEditor';
 import KnowledgePanel from '../knowledge/KnowledgePanel';
-import {citeClaim,type Bookmark} from '../knowledge/claim-api';
+import {citeClaim,citeRequirement,type Bookmark} from '../knowledge/claim-api';
 import {registerDocumentHistoryGuard} from './navigation-guard';
 import {DomainAtom,DomainHeading,DomainParagraph,DomainTable,domainToEditor,editorToDomain,type DomainAst,type DomainSection} from './domain-adapter';
 
 const extensions=[StarterKit.configure({paragraph:false,heading:false,blockquote:false,codeBlock:false,horizontalRule:false,strike:false,code:false,link:{openOnClick:false,autolink:false}}),DomainParagraph,DomainHeading,DomainAtom,TableKit.configure({table:false}),DomainTable,TextAlign.configure({types:['paragraph','heading']}),TextStyleKit];
 const uuid=()=>crypto.randomUUID();
+const prdFields=[['requirement_id','FR-ID'],['name','名称'],['role','角色'],['scenario','场景'],['prerequisites','前置条件'],['normal_flow','正常流程'],['exception_flow','异常流程'],['rules','业务规则'],['inputs','输入'],['outputs','输出'],['permissions','权限'],['nfr','非功能要求'],['acceptance_criteria','验收条件']] as const;
 function SectionCanvas({section,onChange,onEditor,onValidityChange,editable}: {section:DomainSection;onChange:(value:DomainSection)=>void;onEditor:(editor:Editor|null)=>void;onValidityChange:(valid:boolean)=>void;editable:boolean}){
  const source=useRef(section);source.current=section;
  const update=useRef(onChange);update.current=onChange;
@@ -73,6 +75,7 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
  const onContextObserved=useCallback(()=>setContextEpoch(epoch=>epoch+1),[]);
  const [knowledgeOpen,setKnowledgeOpen]=useState(false);
  const [bookmark,setBookmark]=useState<Bookmark|null>(null);
+ const [requirementTarget,setRequirementTarget]=useState<{section_id:string;block_id:string}|null>(null);
  const [outlineOpen,setOutlineOpen]=useState(false);
  const [outlinePending,setOutlinePending]=useState(false);const outlinePendingRef=useRef(false);
  const onOutlinePending=useCallback((pending:boolean)=>{outlinePendingRef.current=pending;setOutlinePending(pending)},[]);
@@ -91,7 +94,9 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
    if(!section?.blocks.some(item=>item.id===blockId)){setStatus('审校块已失效，请重新读取文档和审校');return}
    setActive(sectionId);setTargetBlock(blockId);setStatus('已定位审校块；修改并保存后重新审校');
   });return()=>onRegisterBlockNavigation(null)},[onRegisterBlockNavigation,historyMode,unknown]);
-  useEffect(()=>{if(!editor||!targetBlock||section?.id!==active)return;
+  useEffect(()=>{if(!targetBlock||section?.id!==active)return;
+    if(section.blocks.some(block=>block.id===targetBlock&&block.type==='requirement')){document.getElementById(`requirement-${targetBlock}`)?.scrollIntoView({block:'center'});setTargetBlock('');return}
+    if(!editor)return;
    let found=false;editor.state.doc.descendants((node,pos)=>{if(node.attrs?.blockId===targetBlock){if(node.type.name==='domainAtom')editor.commands.setNodeSelection(pos);else editor.commands.setTextSelection(pos+1);editor.commands.focus();found=true;return false}return true});
    if(found)setTargetBlock('');else setStatus('目标块不在当前编辑画布，需重新读取');
   },[editor,active,section?.id,targetBlock]);
@@ -99,6 +104,7 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
  useEffect(()=>{const warn=(event:BeforeUnloadEvent)=>{if(!dirtyRef.current&&!contextPendingRef.current&&!outlinePendingRef.current)return;event.preventDefault();event.returnValue='' };window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[]);
  useEffect(()=>{
   if(serverVersion.current===value.version_id)return;
+  setRequirementTarget(null);
   serverVersion.current=value.version_id;
   if(dirtyRef.current){setStatus('服务端版本已变化，本地草稿未被替换；请比较版本');setAutoBlocked(true);setHistoryMode('conflict');return}
   setBookmark(null);
@@ -106,8 +112,10 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
   const nextBase={version_id:value.version_id,revision:value.revision};baseRef.current=nextBase;setBase(nextBase);confirmedRef.current=value;setConfirmed(value);
   setActive(refreshed.document.sections[0]?.id??'');setPreview('');setStatus('已重新读取最新版本');
  },[value]);
- const revise=(next:DomainAst)=>{setBookmark(null);draftRef.current=next;setDraft(next);dirtyRef.current=true;setDirty(true);if(!unknown&&historyMode!=='conflict')setAutoBlocked(false);setStatus(online?'尚未保存 · 空闲 1000ms 后自动保存':'离线 · 本地草稿未保存')};
+ const revise=(next:DomainAst)=>{setBookmark(null);setRequirementTarget(null);draftRef.current=next;setDraft(next);dirtyRef.current=true;setDirty(true);if(!unknown&&historyMode!=='conflict')setAutoBlocked(false);setStatus(online?'尚未保存 · 空闲 1000ms 后自动保存':'离线 · 本地草稿未保存')};
  const updateSection=(next:DomainSection)=>revise({...draft,document:{...draft.document,sections:draft.document.sections.map(item=>item.id===next.id?next:item)}});
+ const addRequirement=()=>{if(!section)return;const block={id:uuid(),type:'requirement',content:{statement:'',verification_method:'',source_refs:[],...Object.fromEntries(prdFields.map(([key])=>[key,'']))}};updateSection({...section,blocks:[...section.blocks,block]});setCanvasGeneration(n=>n+1)};
+ const editRequirement=(id:string,key:string,text:string)=>{if(!section)return;updateSection({...section,blocks:section.blocks.map(block=>block.id===id?{...block,content:{...block.content,[key]:text}}:block)});setCanvasGeneration(n=>n+1)};
  const changeTitle=(title:string)=>revise({...draft,document:{...draft.document,metadata:{...draft.document.metadata,title}}});
  const persist=async(mode:'auto'|'explicit'='explicit',debounceMs=0):Promise<boolean>=>{
   if(!dirtyRef.current||savingRef.current||!valid||unknown||historyMode)return false;
@@ -212,6 +220,21 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
   }catch(problem){setBookmark(null);setStatus('引用未确认或来源已失效；请核对文档并重新选择');throw problem}
   finally{savingRef.current=false;setSaving(false)}
  };
+  const citePrdRequirement=async(claimId:string,linkId:string,quotedText:string)=>{
+   const target=requirementTarget;
+   if(!target||dirtyRef.current||savingRef.current||historyMode||unknown)throw Error('需求定位已失效，请重新选择');
+   savingRef.current=true;setSaving(true);
+   try{
+    const result=await citeRequirement(current,value.id,{base_version_id:baseRef.current.version_id,
+     revision:baseRef.current.revision,...target,claim_id:claimId,link_id:linkId,quoted_text:quotedText},new AbortController().signal);
+    setBookmark(null);setRequirementTarget(null);serverVersion.current=result.version_id;confirmedRef.current=result;setConfirmed(result);onConfirmed(result);
+    const saved=result.ast as DomainAst;draftRef.current=saved;setDraft(saved);setCanvasGeneration(n=>n+1);
+    const nextBase={version_id:result.version_id,revision:result.revision};baseRef.current=nextBase;setBase(nextBase);
+    setLastSavedAt(new Date().toISOString());setStatus('PRD 需求来源已绑定当前版本；仍须审校和人工核查');
+   }catch(problem){setRequirementTarget(null);setStatus('需求来源未确认或已失效；请重新核对');throw problem}
+   finally{savingRef.current=false;setSaving(false)}
+  };
+  const selectRequirement=(blockId:string)=>{if(!section||dirtyRef.current||savingRef.current||historyMode||unknown){setStatus('请先保存并核对当前版本，再绑定需求来源');return}setBookmark(null);setRequirementTarget({section_id:section.id,block_id:blockId});setKnowledgeOpen(false);setContextOpen(false);setOutlineOpen(false);setStatus('在当前章节选择 PRD 需求 Claim、证据 Pack，并绑定支持引用')};
  const applyLink=()=>{if(!editor)return;try{const parsed=new URL(link);if(!['https:','http:'].includes(parsed.protocol)||parsed.username||parsed.password)throw new Error();editor.chain().focus().setLink({href:parsed.toString()}).run();setLink('')}catch{setStatus('仅支持安全的 HTTP(S) 链接')}};
  return <><div className="editor-layout" data-testid="domain-editor"><section className="editor-main"><div className="doc-top"><b>领域 AST 草稿</b><span>文档版本 {base.version_id}</span><span>修订 {base.revision}</span><span role="status">{status}</span>{lastSavedAt&&<time dateTime={lastSavedAt}>本机确认：{new Date(lastSavedAt).toLocaleTimeString()}</time>}{timing&&<span title="分层保存计时">空闲 {timing.debounce_ms}ms · 客户端请求 {Math.round(timing.client_request_ms)}ms · 服务端 {timing.server_processing_ms===null?'未提供':`${timing.server_processing_ms}ms`}</span>}{unknown&&<button onClick={()=>void reconcile()}>核对原提交</button>}<button onClick={()=>setHistoryMode('history')}>版本历史</button><button onClick={()=>{setContextOpen(open=>!open);setOutlineOpen(false)}} aria-expanded={contextOpen} aria-controls="projectContextPanel">{contextOpen?'收起项目上下文':'检查项目上下文'}</button><button onClick={()=>{setOutlineOpen(open=>!open);setContextOpen(false)}} aria-expanded={outlineOpen} aria-controls="outlinePanel">{outlineOpen?'收起生成前大纲':'编辑生成前大纲'}</button><button onClick={()=>{setKnowledgeOpen(open=>!open);setOutlineOpen(false);setContextOpen(false)}} aria-expanded={knowledgeOpen}>检索授权证据</button><button className="btn primary" disabled={!dirty||saving||!valid||!!unknown||historyMode!==null} onClick={()=>void persist('explicit')}>保存</button></div>
   <fieldset className="doc-toolbar" aria-label="结构化编辑工具栏" disabled={historyMode!==null}>
@@ -224,7 +247,9 @@ export default function DomainEditor({current,value,onReject,onRefresh,onRegiste
    <input aria-label="链接地址" type="url" value={link} onChange={event=>setLink(event.target.value)} placeholder="https://…"/><button onClick={applyLink} disabled={!editor}>设置链接</button>
    <button onClick={()=>editor?.chain().focus().insertTable({rows:2,cols:2,withHeaderRow:false}).run()} disabled={!editor}>插入表格</button>
    <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp" style={{display:'none'}} aria-label="选择图片" onChange={event=>{void insertImage(event.target.files?.[0]??null);event.target.value=''}}/><button onClick={()=>fileInput.current?.click()} disabled={!editor}>插入图片</button>
-  </fieldset>
-  <div className="doc-scroll"><article className="paper" aria-label="结构化文档编辑画布"><label htmlFor="docTitle">文档标题</label><input id="docTitle" value={String(draft.document.metadata.title??'')} onChange={event=>changeTitle(event.target.value)} maxLength={256} disabled={historyMode!==null}/>{section&&<section key={`${section.id}:${canvasGeneration}`}><h2>{section.title}</h2><SectionCanvas section={section} onChange={updateSection} onEditor={setEditor} onValidityChange={setValid} editable={historyMode===null}/></section>}</article></div>
+    </fieldset>
+    {section&&['prd','test_plan','technical_requirements'].includes(value.document_type)&&<TestTraceEditor current={current} documentId={value.id} versionId={base.version_id} type={value.document_type} section={section} onChange={next=>{updateSection(next);setCanvasGeneration(n=>n+1)}} disabled={historyMode!==null||saving} onProtected={onReject} onNavigateTo={onNavigateTo}/>}
+    {requirementTarget&&<div className="ai-body context-panel"><button onClick={()=>setRequirementTarget(null)}>关闭需求来源</button><KnowledgePanel key={`${requirementTarget.block_id}:${base.version_id}`} current={current} documentId={value.id} compact requirementTarget={requirementTarget} onCiteRequirement={citePrdRequirement} onReject={onReject} onRefresh={onRefresh}/></div>}
+   <div className="doc-scroll"><article className="paper" aria-label="结构化文档编辑画布"><label htmlFor="docTitle">文档标题</label><input id="docTitle" value={String(draft.document.metadata.title??'')} onChange={event=>changeTitle(event.target.value)} maxLength={256} disabled={historyMode!==null}/>{section&&<section key={`${section.id}:${canvasGeneration}`}><h2>{section.title}</h2><SectionCanvas section={section} onChange={updateSection} onEditor={setEditor} onValidityChange={setValid} editable={historyMode===null}/></section>}{value.document_type==='prd'&&section&&<section aria-label="结构化 PRD 需求"><h3>本节结构化需求</h3><p>需求字段随文档版本保存；来源引用须通过当前授权证据绑定并重新审校。</p><button onClick={addRequirement} disabled={historyMode!==null||saving}>新增需求</button>{section.blocks.filter(block=>block.type==='requirement').map(block=><fieldset key={block.id} id={`requirement-${block.id}`}><legend>需求 · {String(block.content.requirement_id||block.id.slice(0,8))}</legend>{prdFields.map(([key,label])=><label key={key}>{label}<textarea value={String(block.content[key]??'')} maxLength={4096} disabled={historyMode!==null||saving} onChange={event=>editRequirement(block.id,key,event.target.value)}/>{!String(block.content[key]??'').trim()&&<small>待补充：{label}</small>}</label>)}<label>需求陈述<textarea value={String(block.content.statement??'')} maxLength={256} onChange={event=>editRequirement(block.id,'statement',event.target.value)} disabled={historyMode!==null||saving}/></label><label>验证方法<textarea value={String(block.content.verification_method??'')} maxLength={2048} onChange={event=>editRequirement(block.id,'verification_method',event.target.value)} disabled={historyMode!==null||saving}/></label><p>来源引用：{Array.isArray(block.content.source_refs)?block.content.source_refs.length:0} 条；请在授权证据流程中绑定。</p><button disabled={dirty||saving||historyMode!==null||!!unknown||!String(block.content.statement??'').trim()} onClick={()=>selectRequirement(block.id)}>选择或更新当前需求来源</button></fieldset>)}</section>}</article></div>
  </section><aside className="ai-side"><div className="ai-tabs"><button className="active" disabled>文档结构</button></div><div className="ai-body" hidden={contextOpen||outlineOpen||knowledgeOpen}><p>内容保存为领域 AST；未知未来节点只读保留。图像仅使用当前授权资源。</p><nav id="docTree" aria-label="文档章节">{draft.document.sections.map(item=><button key={item.id} className={item.id===section?.id?'active':''} onClick={()=>{setBookmark(null);setActive(item.id);setPreview('');setValid(true)}} disabled={!valid&&item.id!==section?.id}>{item.title}</button>)}</nav><p>保存使用 1000ms 空闲防抖；冲突需要逐项确认，不会自动覆盖。</p>{figures.length>0&&<section aria-label="本节图片"><h3>受控图片</h3>{figures.map(block=><button key={block.id} onClick={()=>setPreview(String(block.content.resource_id))}>{String(block.content.alt)}</button>)}{selectedFigure&&<ImagePreview current={current} documentId={value.id} resourceId={preview} alt={String(selectedFigure.content.alt)}/>}</section>}</div>{knowledgeOpen&&<div className="ai-body context-panel"><KnowledgePanel key={`${active}:${base.version_id}`} current={current} documentId={value.id} compact bookmark={bookmark} onCite={cite} onReject={onReject} onRefresh={onRefresh}/></div>}<div id="projectContextPanel" className="ai-body context-panel" hidden={!contextOpen}><ProjectContext current={current} document={confirmed} documentDirty={dirty} onPending={onContextPending} onContextObserved={onContextObserved} onReject={onReject} onRefresh={onRefresh}/></div><div id="outlinePanel" className="ai-body context-panel" hidden={!outlineOpen}><OutlineEditor current={current} document={confirmed} documentDirty={dirty} contextPending={contextPending} contextEpoch={contextEpoch} onPending={onOutlinePending} onReject={onReject} onRefresh={onRefresh}/></div></aside></div>{historyMode&&<VersionHistory current={current} documentId={value.id} base={confirmed} local={draft} mode={historyMode} onMerge={merge} blocked={!!unknown} onReconcile={reconcile} onClose={()=>setHistoryMode(null)} onProtected={error=>{if(error instanceof TemplateError&&error.failure==='authentication')onReject(error);else onRefresh()}}/>}{leaveOpen&&<div className="version-mask"><div role="dialog" aria-modal="true" aria-label="离开未保存草稿" className="version-dialog"><h2>本地草稿尚未保存</h2><p>离开将丢弃内存中的修改。可先保存，若保存失败仍留在此页。{contextPending?'项目上下文仍有未提交输入，请先在检查器保存或明确放弃。':''}{outlinePending?'生成前大纲仍有未提交输入，请先保存或明确放弃。':''}{unknown?'原提交结果未知，离开不能撤销可能已在服务端完成的保存。':''}</p><button onClick={()=>setLeaveOpen(false)}>继续编辑</button><button disabled={saving||!!unknown||!valid||contextPending||outlinePending} onClick={()=>{void persist('explicit').then(ok=>{if(ok){setLeaveOpen(false);leave()}})}}>保存后离开</button><button disabled={saving} onClick={()=>{setLeaveOpen(false);leave()}}>{unknown?'放弃核对并离开（原提交结果未知）':'明确丢弃本地草稿并离开'}</button></div></div>}</>;
 }
diff --git a/edw-web/src/features/templates/ReviewStatus.tsx b/edw-web/src/features/templates/ReviewStatus.tsx
index 217a8e4..f451350 100644
--- a/edw-web/src/features/templates/ReviewStatus.tsx
+++ b/edw-web/src/features/templates/ReviewStatus.tsx
@@ -8,7 +8,7 @@ const categories=['structure','fact','requirement','technical','quality','consis
 const labels=['结构','事实','需求','技术','质量','一致性','风格','安全'];
 type Issue={id:string;category:string;rule_id:string;severity:string;status:string;blocking:boolean;reason:string|null;section_id:string|null;section_title:string|null;block_id:string|null;block_type:string|null;claim_id:string|null;source_id:string|null;quote:string;impact:string;suggestion:string;source_state:string;trace:{source_id:string;version:string;locator:string;quoted_text:string}[]};
 type Run={id:string;state:string;document_version_id:string;document_revision:number;current_eligible:boolean;error_code:string|null;results?:{category:string;state:string;execution_kind:string}[];issues?:Issue[];issue_count?:number;returned_count?:number;offset?:number;page_size?:number;source_state?:string;sections?:{id:string;title:string}[];metrics?:{score:{state:string};coverage:{state:string}};version?:{id:string;revision:number;current_id:string;current_revision:number;comparison:{added_blocks:number;removed_blocks:number;changed_blocks:number}}};
-type Filters={severity:string;section_id:string;status:string;keyword:string};
+ type Filters={severity:string;section_id:string;status:string;keyword:string};
 const initial:Filters={severity:'',section_id:'',status:'',keyword:''};
 const tabs=['结果','追溯','版本比较','历史'] as const;
 
@@ -77,9 +77,10 @@ export default function ReviewStatus({current,document,onNavigateToBlock,onDocum
      <label>关键词<input value={filters.keyword} maxLength={128} onChange={event=>change({keyword:event.target.value})}/></label></div>
     <p>匹配问题 {run.issue_count??0} 条 · 当前显示 {Math.min(offset+1,run.issue_count??0)}–{offset+(run.returned_count??0)} · 质量评分：未评估（无定义分子/分母） · 覆盖率：未评估（无定义分子/分母）</p>
     {(run.issue_count??0)>100&&<div><button disabled={offset===0} onClick={()=>{setSelected('');setOffset(Math.max(0,offset-100))}}>上一页</button><button disabled={offset+100>=(run.issue_count??0)} onClick={()=>{setSelected('');setOffset(offset+100)}}>下一页</button></div>}
-     {issues.length===0?<p>当前组合筛选无匹配问题。</p>:<div className="review-columns"><div className="review-issues">{issues.map(item=><button className="issue" key={item.id} onClick={()=>choose(item.id)} aria-pressed={selected===item.id}>{item.severity} · {item.status} · {item.section_title??'全篇'} · {item.rule_id} · {item.id}</button>)}</div>
+      {issues.length===0?<p>当前组合筛选无匹配问题。</p>:<div className="review-columns"><div className="review-issues">{issues.map(item=><button className="issue" key={item.id} onClick={()=>choose(item.id)} aria-pressed={selected===item.id}>{item.severity} · {item.status} · {item.section_title??'全篇'} · {item.rule_id} · {item.id}</button>)}</div>
       <aside className="detail-panel" aria-label="问题详情">{issue?<><h3>{issue.rule_id} · {issue.severity}</h3><p>ID：{issue.id} · 状态：{issue.status} · {issue.blocking?'仍阻断':'重审确认关闭'}</p>{issue.reason&&<p>拒绝理由：{issue.reason}</p>}<p>位置：{issue.section_title??'全篇'} / {issue.section_id??'—'} / {issue.block_id??'—'} · Claim：{issue.claim_id??'—'}</p><p>引文：{issue.quote}</p><p>影响：{issue.impact}</p><p>建议：{issue.suggestion}</p><p>来源：{issue.source_id??'无当前授权来源'} · {issue.source_state}</p>{issue.trace.map((link,index)=><p key={index}>追溯：{link.source_id} · {link.version} · {link.locator} · {link.quoted_text}</p>)}{(issue.status==='OPEN'||issue.status==='PENDING_RECHECK')&&<div>{issue.status==='OPEN'&&<><label>拒绝理由<input value={reason} maxLength={4000} onChange={event=>{setReason(event.target.value);setPending(null)}}/></label><label>合法 Patch 运行 ID<input value={patchId} onChange={event=>{setPatchId(event.target.value);setPending(null)}}/></label></>}<label>后续重审运行 ID<input value={recheckId} onChange={event=>{setRecheckId(event.target.value);setPending(null)}}/></label><p>拒绝、修改与接受均不关闭缺陷；正文变化后须重新审校。无配置豁免不可用。</p>{(issue.status==='OPEN'?['accept','reject','modify','handled'] as const:['handled'] as const).map(action=><button key={action} disabled={busy||!current.operations.includes('document:review')||!run.current_eligible&&action!=='handled'||action==='modify'&&(!issue.block_id||!current.operations.includes('document:edit'))} onClick={()=>void decide(action)}>{{accept:'接受',reject:'拒绝',modify:'修改',handled:'已处理'}[action]}</button>)}</div>}</>:<p>选择问题查看当前筛选集合的详情。</p>}</aside></div>}</>}
-   {tab==='追溯'&&<><h3>来源追溯</h3>{run.source_state==='denied'?<p>当前来源不可访问，历史引文不能用作授权。</p>:issues.some(item=>item.trace.length)?issues.flatMap(item=>item.trace.map((link,index)=><p key={`${item.id}:${index}`}>{item.id} → {link.source_id} · {link.version} · {link.locator} · {link.quoted_text}</p>)):<p>选定运行没有可展示的授权来源追溯。</p>}</>}
+    {issue?.status==='MODIFY'&&<div><p>人工修改记录保留；保存新版本并独立重审后可关闭原问题。</p><label>后续重审运行 ID<input value={recheckId} onChange={event=>setRecheckId(event.target.value)}/></label><button disabled={busy||!current.operations.includes('document:review')} onClick={()=>void decide('handled')}>重审后标记已处理</button></div>}
+    {tab==='追溯'&&<><h3>来源追溯</h3>{run.source_state==='denied'?<p>当前来源不可访问，历史引文不能用作授权。</p>:issues.some(item=>item.trace.length)?issues.flatMap(item=>item.trace.map((link,index)=><p key={`${item.id}:${index}`}>{item.id} → {link.source_id} · {link.version} · {link.locator} · {link.quoted_text}</p>)):<p>选定运行没有可展示的授权来源追溯。</p>}</>}
    {tab==='版本比较'&&<><h3>版本比较</h3><p>审校固定版本 {run.version?.revision}（{run.version?.id}）→ 当前版本 {run.version?.current_revision}（{run.version?.current_id}）</p><p>区块新增 {run.version?.comparison.added_blocks??0} · 删除 {run.version?.comparison.removed_blocks??0} · 变化 {run.version?.comparison.changed_blocks??0}</p><p>{run.current_eligible?'版本与当前权限一致':'历史运行不可证明当前版本；需要重新审校。'}</p></>}
    {tab==='历史'&&<><h3>审校历史</h3>{runs.map(item=><button key={item.id} className="issue" onClick={()=>{setSelected('');setOffset(0);setRunId(item.id);setTab('结果')}}>版本 {item.document_revision} · {item.state} · {item.id}</button>)}</>}
   </>}
diff --git a/edw-web/src/features/templates/TemplateWorkspace.tsx b/edw-web/src/features/templates/TemplateWorkspace.tsx
index 48a9119..05919c0 100644
--- a/edw-web/src/features/templates/TemplateWorkspace.tsx
+++ b/edw-web/src/features/templates/TemplateWorkspace.tsx
@@ -2,7 +2,7 @@ import {useEffect,useLayoutEffect,useRef,useState} from 'react';
 import {useQuery,useQueryClient} from '@tanstack/react-query';
 import {useLocation,useNavigate} from 'react-router-dom';
 import type {WorkspaceAccess} from '../../app/access-api';
-import {createDocument,getDocument,getTemplateDetail,getTemplates,getTypeCatalog,TemplateError,templateScopes,type CreateDocument,type DocumentType,type TemplateCard,type TemplateFilters,type TemplateScope} from './template-api';
+import {createDocument,getDocument,getDocumentVersion,getTemplateDetail,getTemplates,getTypeCatalog,TemplateError,templateScopes,type CreateDocument,type DocumentType,type TemplateCard,type TemplateFilters,type TemplateScope} from './template-api';
 import DomainEditor from './DomainEditor';
 import SectionGeneration from './SectionGeneration';
 import CopilotPanel from './CopilotPanel';
@@ -21,19 +21,23 @@ const clearTemplateQueries=(cache:ReturnType<typeof useQueryClient>)=>{
  for(const queryKey of [['template-catalog'],['template-list'],['template-detail'],['template-document']]){void cache.cancelQueries({queryKey});cache.removeQueries({queryKey})}
 };
 function DocumentView({current,documentId,onReject,onRefresh,onRegisterNavigationGuard,onNavigateTo}:Props&{documentId:string}){
+  const location=useLocation();
+  const pinnedVersion=new URLSearchParams(location.search).get('version');
  const navigate=useNavigate();const cache=useQueryClient();const base=`/workspaces/${current.workspace_id}`;const scope=contextKey(current);
  const [blocked,setBlocked]=useState(false);const handled=useRef<unknown>(null);
   const backRef=useRef<()=>void>(()=>navigate(`${base}/documents`));
   const blockRef=useRef<(sectionId:string,blockId:string)=>void>(()=>{});
- const document=useQuery({queryKey:['template-document',scope,documentId],queryFn:({signal})=>getDocument(current,documentId,signal),retry:false,gcTime:0,enabled:!blocked});
+ const document=useQuery({queryKey:['template-document',scope,documentId,pinnedVersion??'head'],queryFn:({signal})=>pinnedVersion?getDocumentVersion(current,documentId,pinnedVersion,signal):getDocument(current,documentId,signal),retry:false,gcTime:0,enabled:!blocked});
  const fatal=document.error instanceof TemplateError&&protectedFailure(document.error)?document.error:null;
  useLayoutEffect(()=>{if(!fatal||handled.current===fatal)return;handled.current=fatal;setBlocked(true);if(fatal.failure==='authentication')onReject(fatal);else onRefresh()},[fatal,onReject,onRefresh]);
  useEffect(()=>{if(blocked)clearTemplateQueries(cache)},[blocked,cache]);
- const value=!blocked&&!fatal?document.data:undefined;
+  const value=!blocked&&!fatal?document.data:undefined;
+  useEffect(()=>{const params=new URLSearchParams(location.search);const section=params.get('section');const block=params.get('block');if(value&&section&&block){if(pinnedVersion)window.document.getElementById(`pinned-${section}-${block}`)?.scrollIntoView({block:'center'});else blockRef.current(section,block)}},[value,location.search,pinnedVersion]);
+  if(value&&pinnedVersion)return <div className="template-document"><header className="page-header"><h1>{value.name} · 固定版本 v{value.revision}</h1><button className="btn" onClick={()=>navigate(`${base}/documents/${documentId}`)}>读取当前版本</button></header><p>版本 {value.version_id} · 只读来源快照，当前授权已重新核验。</p>{value.ast.document.sections.map(section=><section key={section.id}><h2>{section.title}</h2>{section.blocks.map((raw,index)=>{const block=raw as {id:string;type:string;content:Record<string,unknown>};return <article id={`pinned-${section.id}-${block.id}`} key={block.id??index}><h3>{block.type} · {block.id}</h3><pre>{JSON.stringify(block.content,null,2)}</pre></article>})}</section>)}</div>;
   return <div className="template-document" data-testid="template-document"><header className="page-header"><div><h1>{value?.name??'文档初始结构'}</h1><p>文档 ID：{documentId}</p></div><span className="grow"/><button className="btn" onClick={()=>backRef.current()}>返回项目文档</button></header>
    {value?.document_type==='technical_solution'&&<p className="template-state">技术方案：核对固定模板版本与必需章节，确认项目上下文及大纲，选取当前授权证据 Pack，逐章接受提案，再审校参数、架构 Claim 和标准适用性。未经证实的数字与标准留作待确认。</p>}
   {blocked||fatal?<div className="template-state" role="alert"><p>{errorText(fatal??document.error??new Error('当前权限已变化，请重新读取'))}</p><button className="btn" onClick={()=>{setBlocked(false);void document.refetch()}}>重新读取</button></div>:document.isFetching||document.isPending?<p className="template-state" role="status">正在读取当前授权文档…</p>:document.error?<div className="template-state" role="alert"><p>{errorText(document.error)}</p><button className="btn" onClick={()=>void document.refetch()}>重新读取</button></div>:null}
-   {value&&<DomainEditor key={value.id} current={current} value={value} onReject={onReject} onRefresh={onRefresh} onRegisterBack={handler=>{backRef.current=handler}} onRegisterBlockNavigation={handler=>{blockRef.current=handler??(()=>{})}} onNavigateBack={()=>navigate(`${base}/documents`)} onConfirmed={saved=>cache.setQueryData(['template-document',scope,documentId],saved)} onRegisterNavigationGuard={onRegisterNavigationGuard} onNavigateTo={onNavigateTo}/>}
+   {value&&<DomainEditor key={value.id} current={current} value={value} onReject={onReject} onRefresh={onRefresh} onRegisterBack={handler=>{backRef.current=handler}} onRegisterBlockNavigation={handler=>{blockRef.current=handler??(()=>{})}} onNavigateBack={()=>navigate(`${base}/documents`)} onConfirmed={saved=>cache.setQueryData(['template-document',scope,documentId,'head'],saved)} onRegisterNavigationGuard={onRegisterNavigationGuard} onNavigateTo={onNavigateTo}/>}
   {value&&<SectionGeneration key={value.version_id} current={current} document={value} onReject={onReject}/>}
   {value&&<CopilotPanel key={`copilot:${value.version_id}`} current={current} document={value}/>}
    {value&&<ReviewStatus key={`review:${value.version_id}`} current={current} document={value} onNavigateToBlock={(sectionId,blockId)=>blockRef.current(sectionId,blockId)} onDocumentChanged={()=>void document.refetch()}/>}
diff --git a/edw-web/src/features/templates/domain-adapter.ts b/edw-web/src/features/templates/domain-adapter.ts
index 3dce636..8471189 100644
--- a/edw-web/src/features/templates/domain-adapter.ts
+++ b/edw-web/src/features/templates/domain-adapter.ts
@@ -6,9 +6,9 @@ import {Table} from '@tiptap/extension-table';
 export type DomainBlock={id:string;type:string;content:Record<string,unknown>;[key:string]:unknown};
 export type DomainSection={id:string;title:string;blocks:DomainBlock[];[key:string]:unknown};
 export type DomainAst={schema_version:'1.0';document:{metadata:Record<string,unknown>;sections:DomainSection[];claims:unknown[];citations:unknown[];review_state:Record<string,unknown>;[key:string]:unknown};[key:string]:unknown};
-const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
+const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
 const safeLink=(value:unknown):value is string=>{if(typeof value!=='string'||/[\s\\]/.test(value))return false;try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!!url.hostname&&!url.username&&!url.password&&url.port!=='0'}catch{return false}};
-const known=new Set(['paragraph','heading','table','figure','diagram','requirement','citation','warning','code','form']);
+const known=new Set(['paragraph','heading','table','figure','diagram','requirement','test_item','test_case','acceptance','citation','warning','code','form']);
 const asRecord=(value:unknown):Record<string,unknown>=>value!==null&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{};
 const text=(value:unknown):string=>typeof value==='string'?value:'';
 
diff --git a/edw-web/src/features/templates/template-api.ts b/edw-web/src/features/templates/template-api.ts
index 47c19fd..e870c6d 100644
--- a/edw-web/src/features/templates/template-api.ts
+++ b/edw-web/src/features/templates/template-api.ts
@@ -92,6 +92,10 @@ export async function getDocumentVersions(current:WorkspaceAccess,id:string,befo
 export async function getDocumentVersion(current:WorkspaceAccess,id:string,versionId:string,signal?:AbortSignal):Promise<DocumentData>{
  if(!validId(id)||!validId(versionId))throw new TemplateError('validation','历史版本标识无效');const value=(await request(current,`/documents/${id}/versions/${versionId}`,signal)).value;const result=document(value,current,id);if(result.version_id!==versionId)return invalid();return result;
 }
+export async function getTestCoverage(current:WorkspaceAccess,id:string,signal?:AbortSignal):Promise<unknown>{
+ if(!validId(id))throw new TemplateError('validation','文档标识无效');
+ return (await request(current,`/documents/${id}/test-coverage`,signal)).value;
+}
 export async function getImage(current:WorkspaceAccess,id:string,mediaId:string,signal?:AbortSignal):Promise<Blob>{
  ensureContext(current);if(!validId(id)||!validId(mediaId))throw new TemplateError('validation','图片标识无效');
  const accessToken=token();if(!accessToken)throw new TemplateError('authentication','登录已失效，请重新登录',401);
diff --git a/tests/contract/test_citation_trace_remediation.py b/tests/contract/test_citation_trace_remediation.py
index d9e8d40..465fec3 100644
--- a/tests/contract/test_citation_trace_remediation.py
+++ b/tests/contract/test_citation_trace_remediation.py
@@ -39,7 +39,7 @@ def test_historical_link_traces_against_current_scope(monkeypatch):
     def connection(_settings):
         yield Conn()
 
-    monkeypatch.setattr(db, 'connection', connection)
+    monkeypatch.setattr(claim_routes, 'connection', connection)
     monkeypatch.setattr(claim_routes, 'checked', lambda *_: (None, {'kind': 'document'}, context))
     monkeypatch.setattr(claim_routes, 'scope', lambda *_: ({'project_id': 'p'}, context, state))
     monkeypatch.setattr(claim_routes, 'pinned', lambda *_: (_ for _ in ()).throw(AssertionError('old head')))
diff --git a/tests/security/test_review_inspection_boundary.py b/tests/security/test_review_inspection_boundary.py
index 2089497..7870c90 100644
--- a/tests/security/test_review_inspection_boundary.py
+++ b/tests/security/test_review_inspection_boundary.py
@@ -9,7 +9,7 @@ def test_history_and_issue_detail_recheck_current_access_and_pinned_run():
     assert "WHERE run_id=%s AND id=%s" in source
     assert 'source_safe(conn, workspace_id, anchor, subject, citations)' in source
     assert "'score': {'numerator': None, 'denominator': None" in source
-    assert "'coverage': {'numerator': None, 'denominator': None" in source
+    assert "'coverage': coverage_metric" in source
 
 
 def test_ui_discards_cross_run_and_cross_filter_selection():
diff --git a/tests/security/test_technical_solution_review_boundary.py b/tests/security/test_technical_solution_review_boundary.py
index 9fab43e..211acda 100644
--- a/tests/security/test_technical_solution_review_boundary.py
+++ b/tests/security/test_technical_solution_review_boundary.py
@@ -14,7 +14,7 @@ def test_pinned_policy_context_and_citation_identity_affect_review_input():
     assert 'source_safe(conn, workspace_id, anchor, job[' in routes
     assert 'citations=fresh_citations' in routes
     assert 'citations=(), stale_sources=fresh_citations' in routes
-    assert "content_hash(structure) != job['template_hash']" in routes
+    assert "content_hash(fresh_structure) != job['template_hash']" in routes
     baseline = input_hash([], [{'key': '吞吐', 'value': '100', 'confirmed': True}], [])
     assert baseline != input_hash([], [{'key': '吞吐', 'value': '200', 'confirmed': True}], [])
 

diff --git a/_bmad-output/implementation-artifacts/epic5-verification-progress-20260930.md b/_bmad-output/implementation-artifacts/epic5-verification-progress-20260930.md
new file mode 100644
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/epic5-verification-progress-20260930.md
@@ -0,0 +1,46 @@
+# Epic 5 验证进展（未关闭）
+
+## 已执行结果
+
+- 本地精选合同/安全回归：35 passed（本轮最近一次 1.04s）；随后新增撤权追踪用例及上游链检查，尚未重跑。
+- 前端领域适配器与文档 API：27 passed；发现 UUID 正则遗漏第四段并已修复。
+- 前端 typecheck 通过；build 通过，有大 chunk 警告；lint 0 errors、21 warnings。
+- 前端 TemplateWorkspace 测试套件在 Node 环境因 `window is not defined` 收集失败，不能标记通过。
+- 全量 `uv run --no-sync pytest -q tests/contract tests/security tests/ops --maxfail=20`：12 failed、769 passed、1 skipped、8 errors（30.84s）。尚未逐项完成基线归因。日志：`C:\Users\virtualink\.local\share\opencode\tool-output\tool_0f17d1063001yvrQO6AtS7OwbW`。
+
+## 同候选打包与远端验证
+
+- 验证主机：seadee-test，openEuler 24.03 LTS-SP2、x86_64；Docker 18.09（API 1.39），Compose v2.39.4 通过 `/usr/local/lib/docker/cli-plugins/docker-compose` 直接运行。
+- 打包镜像：`openeuler/openeuler:24.03-lts-sp2`；已核对容器 `/etc/os-release`。远端从 Docker Hub 拉取超时，使用本地 save/scp/load。
+- 候选 03 源码摘要：`27316df60fb9bc713d744009bf72c7e5b76f4fbc93f24502e970699d25c1998a`。
+- 本地候选：`C:\Users\VIRTUA~1\AppData\Local\Temp\opencode\eid-epic5-candidate-03`。
+- 远端目录：`/opt/eid-test/epic5-20260930-03`。
+- 本地和远端 Compose `run --rm pack` 均退出 0；逐文件 SOURCE.sha256 校验成功；`cmp eid-candidate.tar.gz output/eid-candidate.tar.gz` 退出 0。
+- 产物 SHA256：`769ce2cc697221fa38f0938cc4147c51878c6f1c3a7fd150c5078427370466cd`。
+- 避免旧 daemon 的 platform API 错误，打包容器内显式验证 `uname -m = x86_64`。
+- 候选 03 在本地与远端相同验证镜像中执行只读、无网络精选回归：均 33 passed（5.54s / 2.28s）。验证镜像是 Python 应用基础镜像加 pytest/Pillow，**不是 openEuler 应用运行镜像**；候选源码通过只读挂载/PYTHONPATH 加载，未使用镜像内旧源码作为结果。
+- 未启动十服务应用栈、未执行真实数据库迁移或授权 API/worker/web 端到端验证。以上证据只证明容器打包与离线回归。
+- 候选 03 后又修复 UUID、增加撤权回归和上游链检查，**当前工作树已不同于远端候选 03**，需生成下一候选并重新验证。
+
+## 独立审查与剩余事项
+
+- Codex 文件读取审查因本机沙箱启动失败而超时；Claude CLI 也超时，未得到审查结论。
+- 将关键后端 diff 直接交给独立 Codex 会话后获得静态发现（无工具执行）。这不是完整 BMAD 三层审查，也不是批准。
+- 已按发现修复：需求引用先核验编辑权再读取链接；核验所有保留 source_refs；跨文档覆盖问题不再伪装成本测试方案区块；不可访问链接返回 unavailable；same_defect 容忍空 details。
+- 初步排除：投影调用遗漏（editor_repository.save_document 已调用 project）；modify 缺少当前复查（accessible_result 已重新校验）；旧链接静默通过（coverage 已标 stale）；引用偏移需与目标正文对齐，非来源全文偏移。
+- 待继续核实：显式基线范围（目前仅引用到的需求文档）、完整链覆盖分子、同文档链接保存后的过期策略、多 Claim 稳定缺陷身份、技术要求 UI 的来源绑定入口、数据库事务与独立并发授权回归。
+- BMAD step-04 要求同级模型三层独立子代理；当前没有子代理工具。按其降级协议生成三个自包含交接 Prompt，并暂停等待独立审查结果。
+
+## 七故事验收状态
+
+| 故事 | 本轮状态 |
+|---|---|
+| 5.1 固定版本八类审校 | 已检查相关版本/来源逻辑及精选回归，完整运行链未验证 |
+| 5.2 筛选、溯源与历史 | 引用关键字匹配与真实覆盖初版，UI 交互/筛选一致性未完整验证 |
+| 5.3 人工处置 | Modify 后独立复查关闭路径初版，事务与端到端未验证 |
+| 5.4 技术方案 | 相关规则回归通过，完整创建→生成→接受→审校未验证 |
+| 5.5 PRD | 保留用户工作并修复引用续接/字段检查，完整来源事务未验证 |
+| 5.6 测试链 | 双向投影/版本导航/覆盖初版；链分子与显式分母仍待完善 |
+| 5.7 可测量技术要求 | 结构字段/阈值保护/规则初版；来源 UI 与完整改写接受链未验证 |
+
+未提交或推送 Git；未修改 seadee-develop；未删除既有远端数据。规格保持 in-review，所有未完成执行项保持未勾选。

diff --git a/_bmad-output/implementation-artifacts/spec-5-5-prd-composition.md b/_bmad-output/implementation-artifacts/spec-5-5-prd-composition.md
new file mode 100644
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/spec-5-5-prd-composition.md
@@ -0,0 +1,73 @@
+---
+title: 'Story 5.5 结构完整的 PRD 编制'
+type: 'feature'
+created: '2026-09-29'
+status: 'in-review'
+route: 'dispatch'
+baseline_commit: 'c58df95'
+review_loop_iteration: 0
+context:
+  - '_bmad-output/implementation-artifacts/epic-5-context.md'
+  - '_bmad-output/planning-artifacts/epic-5-review-core-types.md'
+---
+
+<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">
+
+## Intent
+
+**Problem:** 当前通用 `requirement` 区块仅校验需求编号、陈述、验证方式和来源 ID，不能保证 PRD 的角色、场景、前置条件、正常/异常流程、业务规则、输入输出、权限、NFR 与验收条件以可定位字段保存。叙述性摘要不能替代结构化需求，重复编号或缺项也不能可靠地呈现在 Review 中。
+
+**Approach:** 沿现有 PRD 固定模板→项目上下文→大纲确认→授权 Evidence Pack→章节提案→人工接受→版本审校路径，为 PRD 的 `requirement` 区块增加版本化结构化字段和保存校验、稳定 FR-ID/区块定位与来源关联，并在八类 Review 中定位重复编号、空缺字段及无效来源；Web 编辑器提供字段录入、缺项提示和问题定位。保留旧版本合法数据，未经授权的引用不被视作有效证据。
+
+## Boundaries & Constraints
+
+**Always:** PRD 需求字段包含 FR-ID、名称、角色、场景、前置条件、正常流程、异常流程、规则、输入、输出、权限、NFR、验收条件；持久化保留 section/block/source 定位。保存路径维持原有 AST/CAS、版本、权限和引用保护；Review 必须以当前固定版本及当前授权来源检查，不把正文段落冒充结构字段。对现存非 PRD 文种与历史合法区块保持兼容；缺项时保留已录入值并返回字段级、区块级问题，不用模板或模型臆补。
+
+**Never:** 不由本地规则声明产品质量、批准或可发布；不以推测的来源或虚构 FR-ID 补全数据。不运行测试套件、迁移、服务、浏览器、外部模型或真实环境验收；只做源码/静态检查及离线编译，本轮推进到 `review`，不做独立质量门禁。
+
+## I/O & Edge-Case Matrix
+
+| 场景 | 输入/状态 | 预期 | 错误处理 |
+|---|---|---|---|
+| 完整需求 | PRD 版本模板、已确认上下文、当前授权引用及完整结构字段 | 需求和编号稳定持久化，字段与来源可按章节/区块复核 | 不等同于正式审批 |
+| 字段缺失 | 异常流程、权限或验收条件为空，或仅写在普通正文 | 指出确切字段与需求区块；已有值原样保留 | 不用叙述性摘要抵消缺项 |
+| 编号冲突 | 两个需求使用同一 FR-ID 或缺失编号 | 定位全部冲突区块及缺编号字段 | 不自动重编号导致引用漂移 |
+| 来源变更 | 引用撤权、版本过期、来源与当前区块不匹配 | 当前审校不认证支持状态，保留历史记录 | 不泄露已撤权内容 |
+| 旧文档 | 既有通用 requirement/其他文种 | 仍可读取和按既有规则编辑；PRD 缺字段明确提示 | 不破坏旧版本或静默丢字段 |
+
+</frozen-after-approval>
+
+## Code Map
+
+- `edw-api/src/edw_api/documents/editor_domain.py` — AST `requirement` 结构校验、版本与未知字段兼容。
+- `edw-api/src/edw_api/documents/` — 需求投影/版本保存及模板文种路径；确认实际持久化和 source_refs 的语义后选定最小改动。
+- `edw-api/src/edw_api/review/{rules,routes}.py` — 固定输入、PRD 字段/编号/来源检查和精确定位。
+- `edw-web/src/features/templates/` — 需求字段编辑与 Review 导航，沿用现有编辑/生成/接受流程。
+- `tests/contract/`、`tests/security/` — 正反例源码契约，仅编译不运行。
+
+## Tasks & Acceptance
+
+**Execution:**
+- [x] 定义并校验 PRD requirement 字段，保持稳定标识、来源及现有版本化保存语义。
+- [x] 接入当前模板/上下文/来源的 PRD 文种审校，报告缺失、重复与过期/无权来源。
+- [x] 在现有编辑器暴露结构化录入、字段缺项和精确问题定位，不破坏既有界面主层级。
+- [x] 编写契约与安全用例源码；仅运行允许的编译、typecheck、diff 检查。
+
+**Acceptance Criteria:**
+- Given PRD 模板、上下文和授权来源，when 作者创建、接受、保存并审校结构化需求，then 所有约定字段、稳定 FR-ID、章节/区块和来源引用被持久化且可复核。
+- Given 重复/缺失编号、异常/权限/验收缺项或撤权来源，when 保存或 Review，then 精确报告缺陷、保留此前合法输入，普通段落不能抵充需求字段。
+
+## Spec Change Log
+
+- 初步实现结构化字段编辑、保存校验和审校定位；发现现有引用命令仅支持正文选区，`requirement.source_refs` 缺少受控的当前版本来源绑定路径。不能把该字段的手填 ID 或旧版本引用认作已授权证据。该项尚未满足验收。
+- 后续补充了 `prd_requirement` Claim 的当前版本候选、受控引用命令及编辑器来源入口；API 在事务前后复核 Pack/项目权限/版本/冲突，原子写入文档版本及对应引用记录。普通编辑不能添加或替换引用 ID；陈述等正文修改继续沿用版本化保存，再次编辑产生新版本时旧引用不再认证，须通过受控命令重新绑定。历史合法需求编号与最长 2048 字陈述可在普通修改时保留，旧编号由 Review 报告，不使旧文档无法编辑。
+- 此来源绑定只覆盖受控附件，且要求当前 Pack 的精确陈述。无可核验来源时仍保持高优先级待确认；不声称企业来源或历史来源已验证。
+
+## Review Triage Log
+
+- 静态核对：受控来源写入与 `save_document` 同事务，当前 Pack、附件原文、冲突、Claim/章节/区块、文档头及编辑权在提交前复核。普通保存拒绝伪造引用；旧版本引用经版本失效处理，不认证当前需求。
+- 用户明确要求本轮推进至 `review`；按已批准的静态验证政策登记 `in-review`，不将未执行的矩阵测试视为通过，也不声明独立质量门禁或运行验收完成。
+
+## Verification
+
+`python -m compileall -q edw-api/src edw-worker/src migrations/versions tests/contract tests/security`、`npm --prefix edw-web run typecheck`、`git diff --check` 通过。矩阵测试源码尚未运行，因此不得按 workflow 的矩阵测试门禁宣称验收完成。测试、迁移、服务、浏览器、外部模型与运行验收均 `not-run`。

diff --git a/_bmad-output/implementation-artifacts/spec-epic-5-review-pack-remote.md b/_bmad-output/implementation-artifacts/spec-epic-5-review-pack-remote.md
new file mode 100644
--- /dev/null
+++ b/_bmad-output/implementation-artifacts/spec-epic-5-review-pack-remote.md
@@ -0,0 +1,81 @@
+---
+title: 'Epic 5 全量审查修复、openEuler 打包与远端验证'
+type: 'bugfix'
+created: '2026-09-30'
+status: 'in-review'
+baseline_commit: 'c58df950f84679e96359d21ac3b89f94d9583731'
+route: 'dispatch'
+review_loop_iteration: 0
+context:
+  - '_bmad-output/planning-artifacts/epic-5-review-core-types.md'
+---
+
+<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">
+
+## Intent
+
+**Problem:** Epic 5 的已实现故事存在审校状态、引用版本、安全检查与界面契约缺陷；尚无独立 openEuler Compose 打包环境及 seadee-test 验证证据。
+
+**Approach:** 审查全部七个故事，修复确认的问题，提供容器化打包入口，并通过 SSH 对同一候选源码执行可复现验证。保留并纳入用户已确认的未提交 Story 5.5 工作。
+
+**用户范围决策：** 同时实现 backlog 的 Story 5.6 和 5.7；容器目标采用已确认的 openEuler 24.03 LTS-SP2，替代原请求的 24.04；允许在 seadee-test 安装并启用 Docker/Compose，在 `/opt/eid-test` 创建隔离测试环境。
+
+## Boundaries & Constraints
+
+**Always:** 按故事验收条件核对，使用独立审查和有意义的回归验证；稳定区块身份、当前授权来源、固定版本和人工决策必须一致。新请求授权运行本地及远端测试，覆盖旧文档仅静态验证的限制；历史证据原样保留。产物记录实际源码校验和，排除本地凭据与缓存，运行时密钥不写入产物。远端使用隔离测试目录、Compose 项目和数据卷。
+
+**Never:** 不把高分或规则通过等同正式批准；不关闭仍存在的严重缺陷，不伪造来源、模型准确率或未执行结果；不删除既有远端数据或修改 seadee-develop 部署。不提交或推送 Git。
+
+## I/O & Edge-Case Matrix
+
+| 场景 | 输入/状态 | 预期输出/行为 | 错误处理 |
+|---|---|---|---|
+| 跨版本复查 | 无关编辑后同一缺陷仍存在 | 保留阻断，以稳定区块及规则身份匹配 | 不以新 Claim UUID 误判修复 |
+| 多条需求引用 | 顺序绑定两个需求来源 | 当前版本保留经重新核验的全部有效绑定 | 过期、冲突或撤权来源拒绝认证 |
+| 手工修改 | Modify 后保存并独立复查 | 缺陷消失方可 handled，保留历史决策 | 严重未解决问题不可关闭 |
+| 结构化需求 | 字段内敏感信息或缺项 | 字段级安全及完整性问题可定位 | 不只检查 statement |
+| 来源搜索 | 当前获授权的可见引用原文 | 搜索、数量与展示一致 | 禁止检索暴露撤权原文 |
+| 容器打包 | 明确 openEuler 镜像及候选源码 | Compose 打包产物、清单及校验和 | 镜像或输入缺失时明确失败 |
+| 远端验证 | SSH 可达、隔离运行环境 | 记录真实执行命令、结果及环境 | 前置失败记录阻塞，不宣称通过 |
+
+</frozen-after-approval>
+
+## Code Map
+
+- `edw-api/src/edw_api/review/routes.py`：版本资格、来源复核、筛选与决策；修复 same_defect 及 modify 闭环。
+- `edw-api/src/edw_api/review/rules.py`：八类规则及 PRD 字段检查；遍历结构化内容并保留定位。
+- `edw-api/src/edw_api/documents/{claim_routes,claims,editor_repository,editor_domain}.py`：引用命令、Claim 投影、版本保存与 AST 校验；保持事务/CAS 权限边界。
+- `edw-api/src/edw_api/knowledge/governance.py`：当前适用性、冲突及来源治理复核。
+- `contracts/document-ast-v1.schema.json`：对齐 PRD 草稿与完整需求约束。
+- `edw-web/src/features/templates/{ReviewStatus,DomainEditor}.tsx`：人工修改闭环与字段展示，复用现有布局。
+- `scripts/remote_environment.py`、`deployment/compose.yaml`：现有打包及十服务运行栈；原脚本绑定 seadee-develop，避免直接用于新测试主机。
+- `deployment/{python,web}.Dockerfile`、`deployment/images.lock.json`：锁定工具、镜像及应用构建输入。
+- `tests/{contract,security,ops}/`：复用并补充真实行为回归；不以源码字符串断言代替事务验证。
+
+## Tasks & Acceptance
+
+**Execution:**
+- [ ] `edw-api/src/edw_api/documents/`、`review/`、`edw-web/src/features/templates/`、`migrations/versions/` — 实现 5.6 双向版本化需求/测试项/用例/验收链接、真实覆盖分母与缺失/冗余/过期提示，保护批准阈值；实现 5.7 条件、指标、单位、阈值、验证方式与来源的结构化字段和审校，拒绝无依据阈值替换。
+- [ ] `edw-api/src/edw_api/review/`、`documents/`、`knowledge/` — 核实并修复已发现状态、引用、授权和字段检查问题。
+- [ ] `contracts/document-ast-v1.schema.json`、`edw-web/src/features/templates/` — 对齐草稿契约并恢复手工修改后的关闭路径。
+- [ ] `tests/contract/`、`tests/security/` — 补充跨版本、顺序引用、治理变化、字段敏感信息和人工复查用例。
+- [ ] `deployment/`、`scripts/`、`docs/` — 添加 Compose 打包容器、产物校验及使用说明。
+- [ ] `_bmad-output/implementation-artifacts/` — 汇总七故事审查、独立复核、测试与远端证据，准确记录未完成项。
+
+**Acceptance Criteria:**
+- Given 已实现故事与候选工作树，when 审查修复并独立复核，then 已确认问题有修复及回归证据，故事范围不被静默扩大或缩减。
+- Given 明确的 openEuler 目标，when 运行 Compose 打包，then 产生包含部署输入、源码清单及校验和的可核验产物。
+- Given seadee-test 隔离测试环境，when 通过 SSH 验证候选产物，then 记录环境、执行结果及失败原因，不能借用历史证据证明通过。
+
+## Implementation Notes
+
+## Spec Change Log
+
+## Review Triage Log
+
+## Verification
+
+- `uv run --no-sync pytest -q tests/contract tests/security tests/ops`：按实际改动选择相关用例并处理失败。
+- `npm --prefix edw-web run typecheck`、前端 lint/build：成功。
+- `git diff --check`：无空白错误。
+- SSH `seadee-test`：候选源码/产物校验、容器打包与隔离运行验证，保留退出码及脱敏证据。

diff --git a/deployment/pack.compose.yaml b/deployment/pack.compose.yaml
new file mode 100644
--- /dev/null
+++ b/deployment/pack.compose.yaml
@@ -0,0 +1,26 @@
+name: eid-openeuler-pack
+services:
+  pack:
+    image: openeuler/openeuler:24.03-lts-sp2
+    network_mode: none
+    read_only: true
+    user: "0:0"
+    cap_drop: [ALL]
+    security_opt: ["no-new-privileges:true"]
+    tmpfs: ["/tmp:size=67108864"]
+    volumes:
+      - "${EID_CANDIDATE_DIR:?Set the verified candidate directory}:/candidate:ro"
+      - "${EID_PACKAGE_DIR:?Set a new output directory}:/output"
+    entrypoint: ["/bin/bash", "-ec"]
+    command:
+      - >-
+        test "$$(uname -m)" = x86_64 &&
+        grep -q 'openEuler' /etc/os-release &&
+        grep -q 'LTS-SP2' /etc/os-release &&
+        cd /candidate && sha256sum -c SOURCE.sha256 &&
+        test ! -e /output/eid-candidate.tar.gz &&
+        cp /etc/os-release /output/pack-os-release.txt &&
+        tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -czf /output/eid-candidate.tar.gz . &&
+        cp SOURCE.sha256 /output/SOURCE.sha256 &&
+        cp SOURCE.json /output/SOURCE.json &&
+        cd /output && sha256sum eid-candidate.tar.gz > ARTIFACT.sha256

diff --git a/docs/epic5-openeuler-pack.md b/docs/epic5-openeuler-pack.md
new file mode 100644
--- /dev/null
+++ b/docs/epic5-openeuler-pack.md
@@ -0,0 +1,14 @@
+# Epic 5 openEuler 打包与隔离验证
+
+目标为 openEuler 24.03 LTS-SP2（linux/amd64）。该入口打包显式候选源码，包含部署输入、测试、逐文件 SHA-256、候选源码摘要和基线提交；不是预构建镜像或运行验收证明。
+
+```powershell
+uv run --no-sync python -m scripts.epic5_candidate --output .local/epic5/candidate
+$env:EID_CANDIDATE_DIR = (Resolve-Path .local/epic5/candidate).Path
+$env:EID_PACKAGE_DIR = (Resolve-Path .local/epic5/package).Path
+docker compose -f deployment/pack.compose.yaml run --rm pack
+```
+
+输出目录须预先创建且为空。镜像或候选输入缺失、校验错误、输出已存在都会失败。Compose 不挂载工作树、Docker socket 或凭据目录；打包无网络。`SOURCE.json` 记录实际候选内容，`ARTIFACT.sha256` 记录 tar.gz。记录实际镜像 ID/RepoDigest，标签本身不是不可变镜像身份。
+
+远端只使用 SSH `seadee-test` 和新建 `/opt/eid-test/<候选标识>`；不要调用绑定 seadee-develop 的 `remote_environment.py` 部署操作。检查主机、sudo、Docker/Compose，校验上传候选的 SOURCE.sha256 后运行相同打包 Compose。运行栈必须将 Compose 项目、命名卷和监听端口改为该候选独有值；不得接管已有目录或卷。运行时 wake/model 密钥在主机私有环境文件中创建，不能加入源码或打包目录。迁移使用隔离数据库 eid_local_dev / eid-local-dev-v1；记录命令、退出码、镜像身份、服务状态与真实测试结果。失败写入证据，不能沿用历史通过结果。

diff --git a/edw-api/src/edw_api/documents/traceability.py b/edw-api/src/edw_api/documents/traceability.py
new file mode 100644
--- /dev/null
+++ b/edw-api/src/edw_api/documents/traceability.py
@@ -0,0 +1,132 @@
+"""版本固定的测试链与真实需求分母；当前授权始终重新核验。"""
+from ..errors import ApiError
+from ..access.policy import AccessDenied
+from .editor_repository import read_version
+
+KINDS = {'requirement': 'test_item', 'test_item': 'test_case', 'test_case': 'acceptance'}
+MEASUREMENT = ('condition', 'metric', 'unit', 'threshold', 'verification_method')
+
+
+def blocks(ast):
+    return {(s['id'], b['id']): b for s in ast['document']['sections'] for b in s['blocks']}
+
+
+def resolve(conn, subject, workspace_id, ref):
+    value = read_version(conn, subject, workspace_id, ref['document_id'], ref['version_id'])
+    head = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
+                        (ref['document_id'], workspace_id)).fetchone()
+    block = blocks(value['ast']).get((ref['section_id'], ref['block_id']))
+    return value, block, bool(head and str(head['head_version_id']) == ref['version_id'])
+
+
+def validate_links(conn, subject, workspace_id, document_id, ast, old_ast):
+    previous = blocks(old_ast)
+    for locator, block in blocks(ast).items():
+        if block['type'] not in ('test_item', 'test_case', 'acceptance'):
+            continue
+        old = previous.get(locator)
+        for ref in block['content'].get('links', []):
+            # Local links use the base version as an immutable pin. A new version makes
+            # them stale, so link chains normally use separately versioned documents.
+            value, target, current = resolve(conn, subject, workspace_id, ref)
+            if not target or KINDS.get(target['type']) != block['type']:
+                raise ApiError(422, 'TEST_TRACE_INVALID', '测试链的目标类型或区块不匹配')
+            unchanged = old == block
+            if not current and not unchanged:
+                raise ApiError(409, 'TEST_TRACE_STALE', '测试链目标已产生新版本')
+            if target['type'] == 'requirement' and value['document_type'] not in ('prd', 'technical_requirements'):
+                raise ApiError(422, 'TEST_TRACE_INVALID', '测试基线须为结构化需求文档')
+            for field in MEASUREMENT:
+                expected = target['content'].get(field)
+                if expected and block['content'].get(field) != expected:
+                    raise ApiError(422, 'TEST_THRESHOLD_MISMATCH', f'测试不得替换来源字段：{field}')
+
+
+def coverage(conn, subject, workspace_id, ast):
+    """分母包含被引用需求文档的全部当前需求，而非只计算已有测试。"""
+    baseline = {}
+    links = []
+    baseline_documents = set()
+    def collect_baseline(ref, seen):
+        key = tuple(ref[f] for f in ('document_id', 'version_id', 'section_id', 'block_id'))
+        if key in seen or len(seen) >= 32:
+            return
+        value, target, _ = resolve(conn, subject, workspace_id, ref)
+        if not target:
+            return
+        if target['type'] == 'requirement' and ref['document_id'] not in baseline_documents:
+            baseline_documents.add(ref['document_id'])
+            head = conn.execute('SELECT head_version_id FROM document WHERE id=%s AND workspace_id=%s',
+                                (ref['document_id'], workspace_id)).fetchone()
+            live = read_version(conn, subject, workspace_id, ref['document_id'], head['head_version_id'])
+            for (s, b), requirement in blocks(live['ast']).items():
+                if requirement['type'] == 'requirement':
+                    baseline_key = (ref['document_id'], str(live['version_id']), s, b)
+                    baseline[baseline_key] = {'document_id': baseline_key[0], 'version_id': baseline_key[1],
+                        'section_id': s, 'block_id': b, 'requirement_id': requirement['content'].get('requirement_id')}
+        elif target['type'] in ('test_item', 'test_case'):
+            for parent in target['content'].get('links', []):
+                collect_baseline(parent, seen | {key})
+    def upstream(ref, seen):
+        key = tuple(ref[f] for f in ('document_id', 'version_id', 'section_id', 'block_id'))
+        if key in seen or len(seen) >= 32:
+            return False
+        _, target, current = resolve(conn, subject, workspace_id, ref)
+        if not target or not current:
+            return False
+        if target['type'] == 'requirement':
+            return True
+        parents = target['content'].get('links', [])
+        return bool(parents) and all(upstream(parent, seen | {key}) for parent in parents)
+    for (section_id, block_id), block in blocks(ast).items():
+        if block['type'] not in ('test_item', 'test_case', 'acceptance'):
+            continue
+        for ref in block['content'].get('links', []):
+            try:
+                value, target, current = resolve(conn, subject, workspace_id, ref)
+            except (AccessDenied, ApiError) as exc:
+                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
+                    raise
+                links.append({'section_id': section_id, 'block_id': block_id,
+                              'target': ref, 'state': 'unavailable'})
+                continue
+            state = 'current' if current and target and KINDS.get(target['type']) == block['type'] else 'stale'
+            try:
+                if state == 'current' and not upstream(ref, set()):
+                    state = 'stale'
+            except (AccessDenied, ApiError) as exc:
+                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
+                    raise
+                state = 'unavailable'
+            if target and any(target['content'].get(f) and target['content'][f] != block['content'].get(f)
+                              for f in MEASUREMENT):
+                state = 'threshold_mismatch'
+            links.append({'section_id': section_id, 'block_id': block_id, 'target': ref, 'state': state})
+            try:
+                collect_baseline(ref, set())
+            except (AccessDenied, ApiError) as exc:
+                if isinstance(exc, ApiError) and exc.status_code not in (403, 404):
+                    raise
+    rows = []
+    covered = 0
+    for key, requirement in baseline.items():
+        peers = [link for link in links if link['state'] == 'current'
+                 and tuple(link['target'][f] for f in ('document_id', 'version_id', 'section_id', 'block_id')) == key]
+        covered += bool(peers)
+        rows.append({**requirement, 'tests': peers, 'state': 'uncovered' if not peers else
+                     'redundant' if len(peers) > 1 else 'covered'})
+    return {'numerator': covered, 'denominator': len(baseline),
+            'state': 'evaluated' if baseline else 'unevaluated', 'requirements': rows, 'links': links,
+            'unlinked': [{'section_id': s, 'block_id': b} for (s, b), block in blocks(ast).items()
+                         if block['type'] in ('test_item', 'test_case', 'acceptance')
+                         and not block['content'].get('links')]}
+
+
+def project(conn, workspace_id, document_id, version_id, ast):
+    for (section_id, block_id), block in blocks(ast).items():
+        for ref in block['content'].get('links', []) if block['type'] in ('test_item', 'test_case', 'acceptance') else []:
+            conn.execute('''INSERT INTO requirement_trace(workspace_id,document_id,version_id,section_id,
+                block_id,target_document_id,target_version_id,target_section_id,target_block_id)
+                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
+                (workspace_id, document_id, version_id, section_id, block_id,
+                 ref['document_id'], ref['version_id'], ref['section_id'], ref['block_id']))

diff --git a/edw-web/src/features/templates/TestTraceEditor.tsx b/edw-web/src/features/templates/TestTraceEditor.tsx
new file mode 100644
--- /dev/null
+++ b/edw-web/src/features/templates/TestTraceEditor.tsx
@@ -0,0 +1,23 @@
+import {useEffect,useState} from 'react';
+import {useNavigate} from 'react-router-dom';
+import type {WorkspaceAccess} from '../../app/access-api';
+import {getTestCoverage,TemplateError} from './template-api';
+import type {DomainSection} from './domain-adapter';
+
+const fields=[['identifier','编号'],['statement','陈述'],['condition','条件'],['metric','指标'],['unit','单位'],['threshold','阈值'],['verification_method','验证方式']] as const;
+type Ref={document_id:string;version_id:string;section_id:string;block_id:string};
+type Coverage={numerator:number;denominator:number;state:string;requirements:{document_id:string;version_id:string;section_id:string;block_id:string;state:string;requirement_id:string}[];reverse:{document_id:string;version_id:string;section_id:string;block_id:string;state:string}[];links:{section_id:string;block_id:string;state:string;target:Ref}[]};
+export default function TestTraceEditor({current,documentId,versionId,type,section,onChange,disabled,onProtected,onNavigateTo}:{current:WorkspaceAccess;documentId:string;versionId:string;type:string;section:DomainSection;onChange:(value:DomainSection)=>void;disabled:boolean;onProtected:(error:unknown)=>void;onNavigateTo?:(destination:string)=>void}){
+ const workspaceId=current.workspace_id;
+ const routerNavigate=useNavigate();
+ const [coverage,setCoverage]=useState<Coverage|null>(null);const [error,setError]=useState('');
+ const [target,setTarget]=useState<Ref>({document_id:'',version_id:'',section_id:'',block_id:''});
+ useEffect(()=>{const controller=new AbortController();setCoverage(null);setError('');void getTestCoverage(current,documentId,controller.signal).then(body=>{if(controller.signal.aborted)return;const value=body as Coverage;if(!value||!Array.isArray(value.requirements)||!Array.isArray(value.links)||!Array.isArray(value.reverse)||!Number.isSafeInteger(value.numerator)||!Number.isSafeInteger(value.denominator))throw Error('覆盖数据无效');setCoverage(value)}).catch(problem=>{if(controller.signal.aborted)return;setCoverage(null);setError(String(problem));if(problem instanceof TemplateError&&['authentication','forbidden','missing','context'].includes(problem.failure))onProtected(problem)});return()=>controller.abort()},[current,documentId,versionId,onProtected]);
+ const edit=(id:string,key:string,value:unknown)=>onChange({...section,blocks:section.blocks.map(block=>block.id===id?{...block,content:{...block.content,[key]:value}}:block)});
+ const add=(kind:string)=>onChange({...section,blocks:[...section.blocks,{id:crypto.randomUUID(),type:kind,content:{...Object.fromEntries(fields.map(([key])=>[key,''])),requirement_id:'',source_refs:[],links:[]}}]});
+ const navigate=(ref:Ref)=>{const destination=`/workspaces/${workspaceId}/documents/${ref.document_id}?version=${ref.version_id}&section=${ref.section_id}&block=${ref.block_id}`;if(onNavigateTo)onNavigateTo(destination);else routerNavigate(destination)};
+ return <section aria-label="版本化需求与测试追踪"><h3>版本化需求与测试追踪</h3>{error&&<p role="alert">{error}</p>}{coverage&&<><p>覆盖：{coverage.state==='evaluated'?`${coverage.numerator}/${coverage.denominator}`:'未评估（无需求基线）'}；不代表批准。</p>{coverage.requirements.map(row=><p key={row.block_id}><button onClick={()=>navigate(row)}>{row.requirement_id} · {row.state} · {row.version_id}</button></p>)}{coverage.links.map((row,index)=><p key={index}><button onClick={()=>navigate(row.target)}>{row.block_id} → {row.target.block_id} · {row.state}</button></p>)}{coverage.reverse.map((row,index)=><p key={index}><button onClick={()=>navigate(row)}>反向测试：{row.block_id} · {row.version_id} · {row.state}</button></p>)}</>}
+ {type==='test_plan'&&<fieldset disabled={disabled}><legend>固定来源定位</legend>{Object.keys(target).map(key=><label key={key}>{key}<input value={target[key as keyof Ref]} onChange={event=>setTarget({...target,[key]:event.target.value})}/></label>)}{['test_item','test_case','acceptance'].map(kind=><button key={kind} onClick={()=>add(kind)}>新增 {kind}</button>)}</fieldset>}
+ {type==='technical_requirements'&&<button disabled={disabled} onClick={()=>add('requirement')}>新增可测量要求</button>}
+ {section.blocks.filter(block=>['test_item','test_case','acceptance'].includes(block.type)||type==='technical_requirements'&&block.type==='requirement').map(block=><fieldset key={block.id} disabled={disabled}><legend>{block.type} · {block.id}</legend>{(type==='technical_requirements'?([['requirement_id','需求编号'],...fields.filter(([key])=>key!=='identifier')] as const):fields).map(([key,label])=><label key={key}>{label}<textarea maxLength={2048} value={String(block.content[key]??'')} onChange={event=>edit(block.id,key,event.target.value)}/></label>)}{type==='test_plan'&&<><button onClick={()=>{if(Object.values(target).every(value=>/^[0-9a-f-]{36}$/i.test(value)))edit(block.id,'links',[...(Array.isArray(block.content.links)?block.content.links:[]),target]);else setError('所有来源定位须为有效 UUID')}}>绑定固定版本来源</button><p>{JSON.stringify(block.content.links??[])}</p></>}</fieldset>)}</section>;
+}

diff --git a/migrations/versions/0029_requirement_trace.py b/migrations/versions/0029_requirement_trace.py
new file mode 100644
--- /dev/null
+++ b/migrations/versions/0029_requirement_trace.py
@@ -0,0 +1,30 @@
+"""保存双向版本化需求测试链接。"""
+from alembic import op
+
+revision = '0029_requirement_trace'
+down_revision = '0028_review_dispositions'
+branch_labels = None
+depends_on = None
+
+
+def upgrade():
+    identity = op.get_bind().exec_driver_sql(
+        "SELECT current_database(),shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
+    ).one()
+    if tuple(identity) != ('eid_local_dev', 'eid-local-dev-v1'):
+        raise RuntimeError('Isolated EID development database required')
+    op.execute('''CREATE TABLE requirement_trace (
+        workspace_id uuid NOT NULL REFERENCES access_workspace(workspace_id),
+        document_id uuid NOT NULL REFERENCES document(id), version_id uuid NOT NULL REFERENCES document_version(id),
+        section_id uuid NOT NULL, block_id uuid NOT NULL,
+        target_document_id uuid NOT NULL REFERENCES document(id),
+        target_version_id uuid NOT NULL REFERENCES document_version(id),
+        target_section_id uuid NOT NULL, target_block_id uuid NOT NULL,
+        PRIMARY KEY(version_id,block_id,target_version_id,target_block_id));
+        CREATE INDEX requirement_trace_reverse ON requirement_trace(workspace_id,target_document_id,target_block_id);
+        REVOKE ALL ON requirement_trace FROM PUBLIC,eid_api,eid_worker;
+        GRANT SELECT,INSERT ON requirement_trace TO eid_api;''')
+
+
+def downgrade():
+    raise RuntimeError('Forward-only: preserve trace history')

diff --git a/scripts/epic5_candidate.py b/scripts/epic5_candidate.py
new file mode 100644
--- /dev/null
+++ b/scripts/epic5_candidate.py
@@ -0,0 +1,40 @@
+"""生成明确白名单候选源码及校验清单，不包含运行时密钥。"""
+import argparse
+import hashlib
+import json
+from pathlib import Path
+import subprocess
+
+from scripts.remote_environment import ROOT, source_files, source_digest
+
+
+def prepare(output):
+    output = Path(output).resolve()
+    if output.exists():
+        raise ValueError('候选目录已存在，拒绝覆盖')
+    files = source_files(ROOT)
+    for name in ('deployment/pack.compose.yaml',):
+        files[name] = (ROOT / name).read_bytes()
+    for path in (ROOT / 'tests').rglob('*.py'):
+        if '__pycache__' not in path.parts and not path.is_symlink():
+            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
+    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
+    output.mkdir(parents=True)
+    for name, data in files.items():
+        path = output / name
+        path.parent.mkdir(parents=True, exist_ok=True)
+        path.write_bytes(data)
+    metadata = {'schema_version': 1, 'source_sha256': source_digest(files), 'files': manifest,
+                'baseline': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
+                'target': 'openEuler 24.03 LTS-SP2', 'runtime_verified': False}
+    (output / 'SOURCE.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8')
+    hashes = manifest | {'SOURCE.json': hashlib.sha256((output / 'SOURCE.json').read_bytes()).hexdigest()}
+    (output / 'SOURCE.sha256').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(hashes.items())), encoding='utf-8')
+    return metadata
+
+
+if __name__ == '__main__':
+    parser = argparse.ArgumentParser()
+    parser.add_argument('--output', required=True)
+    args = parser.parse_args()
+    print(json.dumps(prepare(args.output), ensure_ascii=False))

diff --git a/tests/contract/test_epic5_regressions.py b/tests/contract/test_epic5_regressions.py
new file mode 100644
--- /dev/null
+++ b/tests/contract/test_epic5_regressions.py
@@ -0,0 +1,92 @@
+"""跨版本、结构字段及真实基线分母的行为回归。"""
+from copy import deepcopy
+from uuid import uuid4
+
+import pytest
+
+from edw_api.documents import traceability
+from edw_api.documents.domain import initial_ast
+from edw_api.documents.editor_domain import InvalidAst, validate_ast
+from edw_api.errors import ApiError
+from edw_api.review.routes import same_defect
+from edw_api.review.rules import inspect
+
+
+def test_claim_reextraction_does_not_hide_persistent_defect():
+    original = dict(category='fact', rule_id='unsupported_critical', section_id='s', block_id='b',
+                    claim_id=str(uuid4()), details={})
+    assert same_defect(original, dict(original, claim_id=str(uuid4())))
+    assert not same_defect(dict(original, details={'field': 'unit'}),
+                           dict(original, details={'field': 'threshold'}))
+    assert same_defect(dict(original, details=None), dict(original, details=None))
+
+
+def test_secret_in_nested_prd_field_is_located_and_redacted():
+    ast = {'document': {'metadata': {'document_type': 'prd'}, 'sections': [
+        {'id': 's', 'title': '需求', 'blocks': [{'id': 'b', 'type': 'requirement',
+         'content': {'statement': '查询', 'exception_flow': 'api_key=private123',
+                     'nested': {'flows': ['password=hidden123']}}}]}]}}
+    _, issues = inspect(ast)
+    secrets = [issue for issue in issues if issue['rule_id'] == 'sensitive_literal']
+    assert {issue['details']['field'] for issue in secrets} == {'exception_flow', 'nested.flows[0]'}
+    assert all(issue['quote'] == '[REDACTED]' for issue in secrets)
+
+
+def test_measurable_fields_and_source_backed_threshold_cannot_be_silently_replaced():
+    template = uuid4()
+    ast = initial_ast('要求', 'technical_requirements', 'project_only', template,
+                      {'sections': [{'title': '要求'}]})
+    content = dict(requirement_id='TR-1', statement='响应', condition='并发10', metric='响应时间',
+                   unit='ms', threshold='100', verification_method='负载测试', source_refs=[str(uuid4())])
+    ast['document']['sections'][0]['blocks'].append({'id': str(uuid4()), 'type': 'requirement', 'content': content})
+    changed = deepcopy(ast)
+    changed['document']['sections'][0]['blocks'][-1]['content']['threshold'] = '200'
+    with pytest.raises(InvalidAst, match='threshold'):
+        validate_ast(changed, expected_template_id=template, document_type='technical_requirements',
+                     knowledge_scope='project_only', old_ast=ast)
+    _, issues = inspect(ast)
+    assert any(i['rule_id'] == 'unsupported_threshold' and i['details']['field'] == 'threshold' for i in issues)
+
+
+def baseline(monkeypatch):
+    requirements = {'document': {'sections': [{'id': 's', 'blocks': [
+        {'id': 'r1', 'type': 'requirement', 'content': {'requirement_id': 'FR-1', 'threshold': '100'}},
+        {'id': 'r2', 'type': 'requirement', 'content': {'requirement_id': 'FR-2'}}]}]}}
+    monkeypatch.setattr(traceability, 'read_version', lambda *_: {
+        'ast': requirements, 'version_id': 'v1', 'document_type': 'prd'})
+    class Conn:
+        def execute(self, *_):
+            return self
+        def fetchone(self):
+            return {'head_version_id': 'v1'}
+    return Conn()
+
+
+def test_coverage_counts_uncovered_and_redundant_baseline_rows(monkeypatch):
+    conn = baseline(monkeypatch)
+    ref = dict(document_id='d1', version_id='v1', section_id='s', block_id='r1')
+    ast = {'document': {'sections': [{'id': 't', 'blocks': [
+        {'id': identifier, 'type': 'test_item', 'content': {'threshold': '100', 'links': [ref]}}
+        for identifier in ('t1', 't2')]}]}}
+    result = traceability.coverage(conn, 'author', 'workspace', ast)
+    assert (result['numerator'], result['denominator']) == (1, 2)
+    assert {row['state'] for row in result['requirements']} == {'uncovered', 'redundant'}
+    ast['document']['sections'][0]['blocks'][0]['content']['threshold'] = '200'
+    with pytest.raises(ApiError) as error:
+        traceability.validate_links(conn, 'author', 'workspace', 'tests', ast, {'document': {'sections': []}})
+    assert error.value.code == 'TEST_THRESHOLD_MISMATCH'
+    ref['version_id'] = 'v0'
+    result = traceability.coverage(conn, 'author', 'workspace', ast)
+    assert result['numerator'] == 0 and result['denominator'] == 2
+    assert all(link['state'] != 'current' for link in result['links'])
+
+
+def test_revoked_trace_is_unavailable_without_reading_protected_baseline(monkeypatch):
+    def denied(*_):
+        raise ApiError(404, 'DOCUMENT_VERSION_NOT_FOUND', '不可见')
+    monkeypatch.setattr(traceability, 'read_version', denied)
+    ast = {'document': {'sections': [{'id': 's', 'blocks': [{'id': 't', 'type': 'test_item',
+        'content': {'links': [dict(document_id='d', version_id='v', section_id='s', block_id='r')]}}]}]}}
+    result = traceability.coverage(None, 'actor', 'workspace', ast)
+    assert result['links'][0]['state'] == 'unavailable'
+    assert result['requirements'] == [] and result['state'] == 'unevaluated'

diff --git a/tests/contract/test_prd_composition.py b/tests/contract/test_prd_composition.py
new file mode 100644
--- /dev/null
+++ b/tests/contract/test_prd_composition.py
@@ -0,0 +1,47 @@
+"""PRD 结构字段的源码契约；本阶段不运行测试套件。"""
+from edw_api.review.rules import inspect
+
+
+def document(*blocks):
+    return {'document': {'metadata': {'document_type': 'prd'},
+                         'sections': [{'id': 's1', 'title': '功能需求', 'blocks': list(blocks)}]}}
+
+
+def requirement(identifier, **changes):
+    content = dict(requirement_id=identifier, name='查询', role='作者', scenario='项目中',
+                   prerequisites='登录', normal_flow='提交查询', exception_flow='无结果提示',
+                   rules='范围校验', inputs='关键词', outputs='结果', permissions='项目成员',
+                   nfr='待确认', acceptance_criteria='结果可定位', statement='查询需求',
+                   verification_method='人工核对', source_refs=[])
+    content.update(changes)
+    return {'id': identifier + '-block', 'type': 'requirement', 'content': content}
+
+
+def test_duplicate_and_missing_fields_have_exact_block_locations():
+    first = requirement('FR-1', exception_flow='')
+    second = requirement('FR-1', permissions='', acceptance_criteria='')
+    second['id'] = 'another-block'
+    _, issues = inspect(document(first, second))
+    duplicates = [issue for issue in issues if issue['rule_id'] == 'prd_duplicate_id']
+    assert {issue['block_id'] for issue in duplicates} == {'FR-1-block', 'another-block'}
+    missing = {(issue['block_id'], issue['details']['field']) for issue in issues if issue['rule_id'] == 'prd_missing_field'}
+    assert {('FR-1-block', 'exception_flow'), ('another-block', 'permissions'),
+            ('another-block', 'acceptance_criteria')} <= missing
+
+
+def test_prose_does_not_supply_structured_prd_fields():
+    block = requirement('', name='', source_refs=['citation-1'])
+    prose = {'id': 'prose', 'type': 'paragraph', 'content': {'text': 'FR-ID: FR-3；名称：查询'}}
+    _, issues = inspect(document(prose, block), citations=[])
+    rules = {issue['rule_id'] for issue in issues}
+    assert {'prd_missing_field', 'prd_source_unverified'} <= rules
+
+
+def test_current_exact_requirement_citation_passes_bounded_source_check():
+    block = requirement('FR-4', source_refs=['citation-4'])
+    citation = {'id': 'citation-4', 'section_id': 's1', 'block_id': block['id'],
+                'selected_text': block['content']['statement'],
+                'quoted_text': '证据支持查询需求', 'chain': 'attachment', 'needs_review': False}
+    _, issues = inspect(document(block), citations=[citation])
+    assert not any(issue['rule_id'] in ('prd_missing_field', 'prd_duplicate_id',
+                                       'prd_source_unverified') for issue in issues)

diff --git a/tests/security/test_prd_review_sources.py b/tests/security/test_prd_review_sources.py
new file mode 100644
--- /dev/null
+++ b/tests/security/test_prd_review_sources.py
@@ -0,0 +1,92 @@
+"""来源匹配只认当前固定输入中的附件引用；不运行外部验证。"""
+from copy import deepcopy
+from pathlib import Path
+from uuid import uuid4
+
+import pytest
+
+from edw_api.documents.domain import initial_ast
+from edw_api.documents.editor_domain import InvalidAst, validate_ast
+from edw_api.review.rules import inspect
+
+ROOT = Path(__file__).resolve().parents[2]
+
+
+def test_foreign_or_expired_source_does_not_satisfy_requirement():
+    block = {'id': 'b1', 'type': 'requirement', 'content': {
+        'requirement_id': 'FR-1', 'statement': '查询', 'verification_method': '人工',
+        'source_refs': ['c1']}}
+    ast = {'document': {'metadata': {'document_type': 'prd'},
+                        'sections': [{'id': 's1', 'title': '需求', 'blocks': [block]}]}}
+    citation = {'id': 'c1', 'section_id': 's2', 'block_id': 'b2', 'chain': 'attachment',
+                'needs_review': False}
+    _, issues = inspect(ast, citations=[citation])
+    assert any(issue['rule_id'] == 'prd_source_unverified' for issue in issues)
+    citation.update(section_id='s1', needs_review=True)
+    _, issues = inspect(ast, citations=[citation])
+    assert any(issue['rule_id'] == 'prd_source_unverified' for issue in issues)
+
+
+def test_prd_source_refs_only_change_via_controlled_command():
+    template = uuid4()
+    previous = initial_ast('PRD', 'prd', 'project_only', template,
+                           {'sections': [{'title': '需求'}]})
+    block = {'id': str(uuid4()), 'type': 'requirement', 'content': {
+        'requirement_id': 'FR-1', 'statement': '查询', 'verification_method': '人工',
+        'source_refs': []}}
+    previous['document']['sections'][0]['blocks'].append(block)
+    forged = deepcopy(previous)
+    forged['document']['sections'][0]['blocks'][-1]['content']['source_refs'] = [str(uuid4())]
+    with pytest.raises(InvalidAst, match='controlled command'):
+        validate_ast(forged, expected_template_id=template, document_type='prd',
+                     knowledge_scope='project_only', old_ast=previous)
+    forged = deepcopy(previous)
+    forged['document']['sections'][0]['blocks'][-1]['content']['statement'] = '变更后的查询'
+    assert validate_ast(forged, expected_template_id=template, document_type='prd',
+                        knowledge_scope='project_only', old_ast=previous) == set()
+    sourced = deepcopy(previous)
+    sourced['document']['sections'][0]['blocks'][-1]['content']['source_refs'] = [str(uuid4())]
+    changed = deepcopy(sourced)
+    changed['document']['sections'][0]['blocks'][-1]['content']['statement'] = '替换后的需求'
+    assert validate_ast(changed, expected_template_id=template, document_type='prd',
+                        knowledge_scope='project_only', old_ast=sourced) == set()
+    changed = deepcopy(sourced)
+    changed['document']['sections'][0]['blocks'][-1]['content']['requirement_id'] = 'FR-2'
+    assert validate_ast(changed, expected_template_id=template, document_type='prd',
+                        knowledge_scope='project_only', old_ast=sourced) == set()
+
+
+def test_legacy_prd_id_and_long_statement_survive_unrelated_edit():
+    template = uuid4()
+    previous = initial_ast('PRD', 'prd', 'project_only', template,
+                           {'sections': [{'title': '需求'}]})
+    previous['document']['sections'][0]['blocks'].append({'id': str(uuid4()),
+        'type': 'requirement', 'content': {'requirement_id': 'REQ-1',
+            'statement': '既有需求' * 200, 'verification_method': '人工', 'source_refs': []}})
+    draft = deepcopy(previous)
+    draft['document']['metadata']['title'] = '更新标题'
+    assert validate_ast(draft, expected_template_id=template, document_type='prd',
+                        knowledge_scope='project_only', old_ast=previous) == set()
+
+
+def test_duplicate_prd_id_rejected_without_dropping_previous_block():
+    template = uuid4()
+    previous = initial_ast('PRD', 'prd', 'project_only', template,
+                           {'sections': [{'title': '需求'}]})
+    draft = deepcopy(previous)
+    for identifier in ('FR-1', 'fr-1'):
+        draft['document']['sections'][0]['blocks'].append({'id': str(uuid4()),
+            'type': 'requirement', 'content': {'requirement_id': identifier,
+                'statement': '查询', 'source_refs': []}})
+    with pytest.raises(InvalidAst, match='Duplicate PRD requirement ID'):
+        validate_ast(draft, expected_template_id=template, document_type='prd',
+                     knowledge_scope='project_only', old_ast=previous)
+    assert len(previous['document']['sections'][0]['blocks']) == 1
+
+
+def test_prd_citation_command_has_live_and_version_guards():
+    routes = (ROOT / 'edw-api/src/edw_api/documents/claim_routes.py').read_text(encoding='utf-8')
+    method = routes.split("@router.post('/requirements/citations')", 1)[1].split("@router.post('/citations')", 1)[0]
+    for guard in ('source_proof(', 'live(', 'head(', 'editable_document(', 'save_document(',
+                  "claim_type'] != 'prd_requirement'", "item['chain'] != 'attachment'"):
+        assert guard in method

Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.
