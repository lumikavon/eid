# 数据模型与 API 接口规范

**文档编号**：EDW-TECH-SPEC-003  
**版本**：V1.1

---

## 1. 数据设计原则

1. 事务数据与知识索引解耦；
2. 文档正文采用 AST；
3. Version 不可覆盖；
4. Evidence 与 Claim 是一等实体；
5. GenerationRun/ReviewRun 必须可审计；
6. AI 输出与人工确认状态分离；
7. 事件采用幂等 ID。
### 1.1 数据访问技术基线

- PostgreSQL + JSONB 为业务事实源与 Document AST 持久化基线；
- FastAPI API 与 Celery Worker 均使用 SQLAlchemy 2 + psycopg 3，但必须配置独立连接池；
- Alembic 是关系模型、JSONB 约束、索引及 pgvector 扩展相关变更的唯一 Schema 迁移入口；
- Redis 仅用于 Cache、Rate Limit、短期锁和可丢失派生状态；
- pgvector 只承载工作台附件/资料的自建向量索引，现有企业知识库不因本系统强制迁移索引。

---

## 2. 核心实体

### 2.1 Workspace

```json
{
  "id": "ws-001",
  "name": "云桌面系统建设项目",
  "type": "project",
  "classification": "L2",
  "status": "active"
}
```

### 2.2 Document

```json
{
  "id": "doc-001",
  "workspace_id": "ws-001",
  "document_type": "technical_solution",
  "title": "云桌面系统总体技术方案",
  "template_id": "tpl-tech-03",
  "template_version": "3.2",
  "status": "USER_REVIEW",
  "current_version_id": "ver-014",
  "classification": "L2"
}
```

### 2.3 DocumentVersion

```json
{
  "id": "ver-014",
  "document_id": "doc-001",
  "version_no": 14,
  "label": "V0.6",
  "parent_version_id": "ver-013",
  "created_by": "user-001",
  "created_via": "ai_patch",
  "generation_run_id": "gen-223",
  "checksum": "sha256:..."
}
```

### 2.4 Section

```json
{
  "id": "sec-3.2",
  "document_version_id": "ver-014",
  "parent_section_id": "sec-3",
  "title": "高可用设计",
  "order": 320,
  "required": true,
  "review_status": "warning"
}
```

### 2.5 Block

Block 类型：

- paragraph
- heading
- table
- figure
- diagram
- requirement
- citation
- warning
- code
- form

示例：

```json
{
  "id": "blk-888",
  "section_id": "sec-3.2",
  "type": "paragraph",
  "content": {
    "text": "系统采用三节点高可用架构……"
  }
}
```

---

## 3. Document AST Schema

顶层建议：

```json
{
  "schema_version": "1.0",
  "document": {
    "metadata": {},
    "sections": [],
    "claims": [],
    "citations": [],
    "review_state": {}
  }
}
```

### 3.1 Requirement Block

```json
{
  "type": "requirement",
  "requirement_id": "TR-HA-001",
  "statement": "单节点故障不得导致核心桌面服务整体不可用",
  "verification_method": "failover_test",
  "source_refs": ["ev-001"]
}
```

### 3.2 Table Block

```json
{
  "type": "table",
  "columns": [
    {"key": "metric", "title": "指标"},
    {"key": "target", "title": "目标"}
  ],
  "rows": [
    {"metric": "登录时延", "target": "≤ 10 s"}
  ]
}
```

---

## 4. Evidence

```json
{
  "id": "ev-001",
  "source_document_id": "kb-doc-99",
  "source_version": "V3.2",
  "source_section": "5.4",
  "chunk_id": "chunk-551",
  "text": "……",
  "knowledge_domain": "quality",
  "knowledge_level": "L1",
  "retrieval_score": 0.81,
  "rerank_score": 0.94,
  "effective_at": "2026-09-08",
  "classification": "L2"
}
```

Evidence 不直接存储“用户是否有权限”的布尔值，而保存：

- `permission_policy_id`
- `permission_snapshot_hash`

读取时再次授权。

---

## 5. Claim

```json
{
  "id": "claim-091",
  "document_version_id": "ver-014",
  "section_id": "sec-3.2",
  "block_id": "blk-888",
  "type": "performance",
  "subject": "系统",
  "predicate": "最大并发用户",
  "value": 500,
  "unit": "user",
  "criticality": "high",
  "verification_status": "supported"
}
```

关联表：

```text
claim_evidence
- claim_id
- evidence_id
- relation: supports | conflicts | contextual
- confidence
```

---

## 6. ReviewIssue

```json
{
  "id": "issue-001",
  "review_run_id": "review-22",
  "severity": "high",
  "type": "fact",
  "section_id": "sec-3.2",
  "block_id": "blk-888",
  "claim_id": "claim-091",
  "status": "open",
  "message": "500 并发用户缺少有效依据",
  "suggestion": "补充性能测试报告"
}
```

Issue 状态：

```text
open
accepted
rejected
fixed
waived
closed
```

`waived` 必须记录批准人和原因。

---

## 7. GenerationRun

```json
{
  "id": "gen-223",
  "document_id": "doc-001",
  "section_id": "sec-3.2",
  "task_type": "section_write",
  "prompt_template_id": "prompt-tech-section",
  "prompt_version": "8",
  "model_profile": "internal-strong-writing-v2",
  "evidence_pack_id": "pack-22",
  "input_hash": "sha256:...",
  "output_hash": "sha256:...",
  "token_in": 8200,
  "token_out": 2100,
  "status": "success"
}
```

敏感 Prompt 原文是否保存应由公司安全策略决定；推荐默认保存模板版本、变量摘要和哈希，必要环境采用加密审计库。

---

## 8. API 规范

统一前缀：

```text
/api/v1
```

### 8.1 创建文档

```http
POST /api/v1/documents
```

Request：

```json
{
  "workspace_id": "ws-001",
  "document_type": "technical_solution",
  "template_id": "tpl-tech-03",
  "title": "云桌面系统总体技术方案"
}
```

Response：

```json
{
  "id": "doc-001",
  "status": "DRAFT",
  "current_version_id": "ver-001"
}
```

### 8.2 生成文档计划

```http
POST /api/v1/documents/{document_id}/plan
```

Request：

```json
{
  "mode": "generate",
  "reference_document_ids": ["kb-doc-1", "kb-doc-2"]
}
```

Response：`202 Accepted`

```json
{
  "task_id": "task-plan-01"
}
```

### 8.3 生成章节

```http
POST /api/v1/documents/{document_id}/sections/{section_id}/generations
```

```json
{
  "instruction": "结合当前项目资料生成高可用设计",
  "mode": "patch",
  "evidence_policy": "required"
}
```

### 8.4 AI 修改

```http
POST /api/v1/documents/{document_id}/patches
```

```json
{
  "version_id": "ver-014",
  "selection": {
    "block_ids": ["blk-888"]
  },
  "operation": "rewrite_as_technical_requirement",
  "instruction": "转换为可测试、可验收的技术要求"
}
```

返回 Patch：

```json
{
  "patch_id": "patch-22",
  "base_version_id": "ver-014",
  "diff": [
    {
      "block_id": "blk-888",
      "before": "系统性能良好。",
      "after": "在100个并发用户条件下，95百分位操作响应时间应不高于2秒。"
    }
  ]
}
```

### 8.5 接受 Patch

```http
POST /api/v1/documents/{document_id}/patches/{patch_id}:accept
```

### 8.6 拒绝 Patch

```http
POST /api/v1/documents/{document_id}/patches/{patch_id}:reject
```

---

## 9. Knowledge API

### 9.1 Search

```http
POST /api/v1/knowledge/search
```

```json
{
  "query": "云桌面系统高可用设计要求",
  "domains": ["technical", "project", "quality"],
  "workspace_id": "ws-001",
  "top_k": 30,
  "rerank_top_k": 8
}
```

Response：

```json
{
  "results": [
    {
      "document_id": "kb-doc-99",
      "chunk_id": "chunk-551",
      "title": "云桌面高可用技术规范",
      "section": "5.4",
      "knowledge_level": "L1",
      "score": 0.94
    }
  ]
}
```

### 9.2 Evidence Pack

```http
POST /api/v1/knowledge/evidence-packs
```

```json
{
  "document_id": "doc-001",
  "section_id": "sec-3.2",
  "queries": ["公司高可用规范", "当前项目可用性要求"]
}
```

---

## 10. Review API

### 10.1 全文审校

```http
POST /api/v1/documents/{document_id}/reviews
```

```json
{
  "reviewers": [
    "structure",
    "fact",
    "requirement",
    "technical",
    "consistency",
    "style",
    "security"
  ]
}
```

### 10.2 查询问题

```http
GET /api/v1/documents/{document_id}/review-issues
```

Query：

```text
severity=high
status=open
section_id=sec-3.2
```

### 10.3 处理 Issue

```http
POST /api/v1/review-issues/{issue_id}:resolve
```

```json
{
  "action": "fixed",
  "comment": "已补充性能测试报告并修正并发指标"
}
```

---

## 11. Template API

```http
GET    /api/v1/templates
POST   /api/v1/templates
GET    /api/v1/templates/{id}
POST   /api/v1/templates/{id}/versions
POST   /api/v1/templates/{id}:publish
POST   /api/v1/templates/{id}:deprecate
```

---

## 12. Export API

```http
POST /api/v1/documents/{document_id}/exports
```

```json
{
  "version_id": "ver-014",
  "format": "docx",
  "render_theme": "corporate-standard-v3"
}
```

返回异步任务。

---

## 13. Event、Outbox 与 Inbox 规范

所有需要跨进程/跨系统投递的领域事件，先与业务事务一起写入 PostgreSQL `outbox_event`，再由 Dispatcher 投递 RabbitMQ。消费者使用 `inbox_event` 或等价幂等记录避免重复副作用。

建议事件：

- `document.created`
- `document.version.created`
- `document.published`
- `generation.started`
- `generation.completed`
- `generation.failed`
- `review.completed`
- `review.issue.created`
- `approval.completed`
- `export.completed`

事件 envelope：

```json
{
  "event_id": "evt-...",
  "event_type": "document.published",
  "occurred_at": "2026-09-08T06:00:00Z",
  "tenant_id": "tenant-001",
  "actor_id": "user-001",
  "data": {}
}
```

消费者必须基于 `event_id` 幂等。生产 RabbitMQ 任务/事件队列采用 quorum queue。

`outbox_event` 最小字段：

```text
id / event_id / aggregate_type / aggregate_id / event_type
payload_jsonb / occurred_at / published_at / retry_count / next_retry_at
```

`inbox_event` 最小字段：

```text
consumer / event_id / received_at / processed_at / status / result_hash
```

---

## 14. SSE 事件流契约

异步计划、章节生成、解析、审校和导出均通过 REST 创建任务，通过 SSE 获取进度：

```http
GET /api/v1/tasks/{task_id}/events
Accept: text/event-stream
Last-Event-ID: 184
```

事件示例：

```text
id: 185
event: generation.progress
data: {"task_id":"task-1","state":"GENERATING","progress":62,"message":"正在生成第 3.2 节"}
```

约束：

- `id`/cursor 单调递增且可恢复；
- 服务端至少保留任务生命周期内的可重放进度事件或可从持久化状态重建快照；
- NGINX 必须关闭不适合 SSE 的响应缓冲并设置合理 idle timeout；
- SSE 只传状态与小型结果摘要，大对象通过 REST/S3 获取；
- 一期不把 WebSocket 作为必选协议。

---

## 15. 数据库与索引实现约束

### 15.1 AST 分层存储

建议 `document_version` 保存版本元数据，正文 AST 采用 JSONB 快照 + 必要关系型投影（Section/Claim/Evidence/ReviewIssue）。高频筛选字段不得仅隐藏在深层 JSONB 中。

### 15.2 工作台附件检索表

本地附件索引至少包含：

```text
attachment_document
attachment_chunk
attachment_chunk_embedding (pgvector)
attachment_chunk_fts      (预分词文本 + PostgreSQL tsvector)
attachment_acl_snapshot
```

中文全文检索在入库前通过 jieba + 企业词典预分词；词典版本需记录以支持重建与 Eval。

### 15.3 迁移与兼容

- Alembic migration 必须提供 upgrade/downgrade 或明确不可逆说明；
- 生产迁移避免长时间锁表；
- JSON Schema/AST Schema 版本与数据库 Schema 版本分开管理；
- API/Worker 升级需兼容滚动发布窗口内的前后一个消息版本。

---

## 16. 错误码

建议：

| Code | 含义 |
|---|---|
| DOC_VERSION_CONFLICT | 当前版本已变化 |
| TEMPLATE_DEPRECATED | 模板已停用 |
| KNOWLEDGE_PERMISSION_DENIED | 无权读取知识 |
| EVIDENCE_REQUIRED | 当前任务要求 Evidence |
| EVIDENCE_STALE | Evidence 已过期 |
| MODEL_NOT_ALLOWED | 当前密级不允许该模型 |
| REVIEW_GATE_FAILED | 审校门禁未通过 |
| MISSING_CONFIRMATION | 存在待确认项 |
| EXPORT_FAILED | 导出失败 |

---

## 17. 并发与一致性

文档修改采用乐观锁：

```text
base_version_id + document_revision
```

如果版本冲突：

- 不自动覆盖；
- 返回 `DOC_VERSION_CONFLICT`；
- 客户端展示差异并要求合并。

长任务不得持有数据库长事务。
