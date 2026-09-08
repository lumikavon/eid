# 安全、权限、审计与 NFR 规范

**文档编号**：EDW-TECH-SPEC-005  
**版本**：V1.1

---

## 1. 安全目标

系统处理项目、客户、技术、生产、质量和制度文档，必须按企业内部受控系统设计。

安全目标：

- 用户只能看到其原本有权访问的知识；
- AI 不扩大权限；
- 外部 LLM 不接触禁止出域的数据；
- AI 生成和修改全程可追溯；
- 正式发布有质量和审批门禁；
- 密钥、Token 和内部敏感字段不得进入日志。

---

## 2. 身份认证

身份基线采用 **Keycloak + OIDC**：

- 浏览器 SPA 使用 OIDC Authorization Code + PKCE；
- NGINX 负责 TLS、静态资源与反向代理，不自行实现业务授权；
- FastAPI 验证短期 Access Token，并将用户/组织/角色映射为业务 Auth Context；
- 企业已有 IdP（AD/LDAP/其他标准身份源）优先通过 Keycloak Federation/Broker 或标准协议适配接入；
- 后台服务采用 Service Identity/Client Credentials，不使用共享用户账号；
- 业务授权仍由工作台的 RBAC + ABAC 执行，Keycloak Role 不直接代替对象级 ABAC。

## 3. 授权模型

### 3.1 RBAC

Role 定义操作能力，例如：

- document:create；
- document:edit；
- document:review；
- document:approve；
- template:publish；
- prompt:manage；
- model:manage。

### 3.2 ABAC

对象访问进一步根据属性：

- department；
- workspace/project；
- customer_scope；
- product_scope；
- classification；
- document_owner；
- approval_status；
- effective_time。

授权决策：

```text
RBAC operation permission
AND
ABAC object scope
AND
classification <= user clearance
```

---

## 4. 知识权限继承

RAG 检索必须携带用户 Auth Context：

```json
{
  "user_id": "user-001",
  "roles": ["project_member"],
  "departments": ["研发部"],
  "workspace_ids": ["ws-001"],
  "customer_scope": ["cust-01"],
  "classification_ceiling": "L2"
}
```

检索前过滤，检索后复核。

严禁：

> 先检索全部知识，再让 LLM“不要说出来”。

---

## 5. 数据分级

建议：

| 级别 | 示例 | 模型策略 |
|---|---|---|
| L0 | 公开资料 | 可按策略使用外部模型 |
| L1 | 公司内部普通资料 | 可脱敏/策略控制 |
| L2 | 客户、项目、内部技术资料 | 内部模型优先 |
| L3 | 核心机密、密钥、核心设计 | 仅受控内部环境 |

文档、Evidence、附件、导出文件均继承/计算密级。

---

## 6. 外部 LLM 出域控制

### 6.1 DLP

检测：

- Access Key；
- Secret；
- JWT；
- 密码；
- 私钥；
- IP/MAC；
- 内部域名；
- 客户名称；
- 人员信息；
- 项目编号；
- 序列号；
- 核心技术参数。

### 6.2 路由门禁

流程：

```text
Request
→ Classify
→ DLP
→ Policy
→ Redact
→ Model Router
```

策略不允许时直接拒绝，不降级到更开放的模型。

---

## 7. Prompt Injection

知识库内容、上传附件、招标文件均视为不可信 Data。

防护：

- 内容清洗；
- Injection 识别；
- System/Data 分层；
- Tool 白名单；
- 模型无权修改权限上下文；
- 检索内容不得产生新的系统指令。

---

## 8. 审计

### 8.1 必审计操作

- 登录；
- 知识搜索；
- 查看 Evidence；
- AI 生成；
- AI 修改；
- Patch 接受/拒绝；
- Reviewer；
- Issue Waive；
- 模板发布；
- Prompt 修改；
- 模型策略修改；
- 审批；
- 导出；
- 正式发布；
- Golden Knowledge 回灌。

### 8.2 Audit 字段

```json
{
  "audit_id": "aud-001",
  "occurred_at": "...",
  "actor_id": "user-001",
  "action": "document.patch.accept",
  "object_type": "document",
  "object_id": "doc-001",
  "workspace_id": "ws-001",
  "result": "success",
  "trace_id": "...",
  "metadata": {}
}
```

日志禁止保存明文 Secret。

---

## 9. 数据保护

- 传输 TLS；
- 数据库和对象存储按企业要求加密；
- 密钥进入 KMS/Secret Manager；
- 导出文件支持水印/密级标记；
- 临时生成文件设置 TTL；
- 数据库备份加密；
- 审计日志防篡改。

---

## 10. NFR

### 10.1 性能

| 指标 | 目标 |
|---|---:|
| 首页/列表 API P95 | < 1 s |
| 文档 AST 获取 P95 | < 1 s |
| 知识搜索 P95 | < 3 s |
| Evidence Pack 典型 P95 | < 8 s |
| AI 首 Token P95 | < 5 s（不含不可控公网异常） |
| 单章节生成典型 P95 | < 60 s |
| 自动保存 P95 | < 1 s |
| 导出 50 页 DOCX | < 60 s |

对 LLM 时延单独建立 SLA，不与 Core Backend 混合。

### 10.2 容量

一期建议容量设计参数：

- 500 日活用户；
- 100 并发在线编辑；
- 20 并发 AI 长任务；
- 100 万文档版本级记录；
- 1000 万 Evidence/Claim 关联级记录。

实际部署按公司规模重新压测。

### 10.3 可用性

- 核心平台 ≥ 99.9%；
- PostgreSQL 生产基线采用 CloudNativePG；若已有企业 PostgreSQL HA 服务满足同等要求可替代；
- Barman Cloud 备份插件将备份写入独立故障域；
- RabbitMQ 生产任务队列使用 quorum queue；
- Celery Worker 无状态或可恢复，业务任务状态持久化于 PostgreSQL；
- Redis 故障不得导致文档、审批或任务事实丢失；
- 单 Worker 故障不得丢失任务状态，恢复依赖 PostgreSQL 状态机 + Outbox/补偿扫描。

### 10.4 RPO/RTO

- RPO ≤ 15 min；
- RTO ≤ 1 h。

### 10.5 可维护性

- API OpenAPI；
- 数据库迁移版本化；
- Feature Flag；
- Prompt 版本化；
- Model Profile 配置化；
- 配置与 Secret 分离；
- 所有关键流程有 Trace ID。

---

## 11. 可观测性

统一采用：

```text
Application / NGINX / Celery / Gateway / Worker
             ↓ OTLP
OpenTelemetry Collector
  ├─ Metrics → Prometheus → Grafana / Alertmanager
  ├─ Logs    → Loki       → Grafana
  └─ Traces  → Tempo      → Grafana
```

### 11.1 Metrics

- HTTP QPS/Error/P50/P95/P99；
- NGINX upstream/SSE connection；
- SQLAlchemy pool wait/usage、PostgreSQL locks/slow query；
- RabbitMQ quorum queue depth/consumer lag/redelivery；
- Celery task queued/running/retry/fail/timeout；
- LLM request/error/TTFT/latency/token/cost；
- Retrieval recall proxy、Evidence empty rate；
- Generation retry rate；
- Review issue rate；
- Export fail rate；
- Approval cycle time；
- S3 request latency/error；
- OCR/LibreOffice/Mermaid Worker resource saturation。

### 11.2 Trace

一次“生成章节”必须可以串联：

```text
NGINX / HTTP Request
→ FastAPI
→ Orchestrator State / Outbox
→ Celery SectionTask
→ QueryPlanner
→ KnowledgeSearch
→ Rerank
→ EvidencePack
→ LLM Gateway / vLLM or Provider
→ ClaimVerification
→ Review
→ Patch
→ SSE progress event
```

日志、指标、Trace 使用同一 `trace_id`/`task_id` 关联，但敏感 Prompt、Secret 与未脱敏正文不得写普通日志。

## 12. 备份与恢复

至少备份：

- PostgreSQL（CloudNativePG + Barman Cloud 或经认可的企业 HA/备份服务）；
- 模板；
- Prompt Registry；
- 审计；
- 对象存储元数据与关键正式输出；
- Golden Knowledge Metadata；
- 工作台附件解析元数据。

备份必须位于独立故障域并定期进行恢复演练。工作台附件的 pgvector/FTS 索引可按原始授权附件重建；现有企业知识库的恢复仍遵循其自身灾备体系，本系统不得假设能够直接重建其内部向量索引。

---

## 13. 灾难与降级

### LLM 故障

编辑器保持可用。

### RAG 故障

禁止以“知识已验证”状态生成关键项目内容。

### Export 故障

不影响正文版本；导出任务可重试。

### Audit 故障

对于正式发布、权限和审批类关键写操作采用 Fail Closed。

---

## 14. 部署与供应链安全

- 开发联调使用 Docker Compose；生产使用 Kubernetes + Helm；
- NGINX、FastAPI、Celery、OCR、LibreOffice、Mermaid、vLLM 采用职责分离的镜像/Pod；
- PaddleOCR、LibreOffice、Mermaid CLI 等解析/渲染组件设置 seccomp/非 root/只读文件系统（可行时）、临时目录限额、网络策略与资源限制；
- Python 依赖使用 `uv` 锁定，前端依赖使用 `pnpm` 锁定；镜像构建需产生可追溯版本与依赖清单；
- Kubernetes Secret 或企业 Secret Manager 存储敏感配置，禁止将密钥写入 Helm values 明文仓库；
- 生产数据库由 CloudNativePG 或等价企业 HA 服务管理，应用 Pod 不拥有集群级数据库管理权限。

---

## 15. 合规和数据保留

保留周期应接入公司制度。建议配置：

```text
Audit
GenerationRun
ReviewRun
Export
Published Document
```

分别设置保留策略，而不是统一永久保存。

---

## 16. 安全验收

必须覆盖：

- 越权检索；
- 越权 Evidence；
- 外部模型 DLP；
- Prompt Injection；
- Secret 泄漏；
- 导出权限；
- Audit 完整性；
- 旧版本权限；
- 已撤销项目成员；
- 高密级文档跨模型路由。
