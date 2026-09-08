# LLM、RAG 与文档生成编排规范

**文档编号**：EDW-TECH-SPEC-004  
**版本**：V1.1

---

## 1. 目标

本规范约束企业智能文档工作台如何使用 LLM 和 RAG，重点避免：

- 一次性生成整篇长文；
- 关键参数无依据；
- 历史错误内容被直接复用；
- 用户权限被 RAG 绕过；
- 不同章节事实互相冲突；
- AI 草稿反向污染知识库。

---

## 2. 总体 Pipeline

```text
Document Intent
  ↓
Context Preparation
  ↓
Document Planning
  ↓
Outline
  ↓
Section Tasks
  ↓
Query Planning
  ↓
Domain Routing
  ↓
Hybrid Retrieval
  ↓
Permission + Validity Filter
  ↓
Rerank
  ↓
Evidence Pack
  ↓
Section Generation
  ↓
Claim Extraction
  ↓
Fact Verification
  ↓
Cross Section Check
  ↓
Reviewer
  ↓
Human Review
```

---

## 3. Context Preparation

必须建立以下结构化上下文：

```json
{
  "workspace": {},
  "document_intent": {},
  "template": {},
  "project_fact_table": {},
  "glossary": {},
  "reference_documents": [],
  "constraints": [],
  "missing_information": []
}
```

### 3.1 Project Fact Table

示例：

| Key | Value | Source | Status |
|---|---|---|---|
| project_name | XX云桌面建设项目 | 项目立项书 | confirmed |
| user_scale | 200 | 需求规格书 V1.3 | confirmed |
| server_nodes | 3 | 当前技术方案 | draft |
| availability | 99.9% | 合同技术附件 | confirmed |

正文生成优先使用 Fact Table 中已确认事实。

### 3.2 工作台附件解析与索引

工作台附件与现有企业知识库采用分离链路。附件按文件类型分派到独立 `parse_ocr` Worker：

- PDF：pypdf；扫描页或低文本质量页面按策略进入 PaddleOCR；
- DOCX：python-docx；
- XLSX：openpyxl；
- 图片：PaddleOCR（按业务需要）；
- 原始文件与解析产物写 S3 API 对象存储，默认 SeaweedFS。

授权附件的本地检索采用 `pgvector + PostgreSQL FTS + jieba 企业词典预分词`。Embedding 基线为 BGE-M3；Reranker 基线为 bge-reranker-v2-m3，统一通过 FlagEmbedding Adapter。现有企业知识库继续由 Knowledge Gateway Adapter 调用，不强制重建现有向量或变更其内部索引。

---

## 4. Document Planner

Planner 输出必须结构化：

```json
{
  "objective": "编制项目总体技术方案",
  "audience": ["客户技术评审", "内部项目组"],
  "must_cover": [
    "项目概述",
    "需求分析",
    "总体架构",
    "高可用",
    "安全",
    "部署",
    "测试验收"
  ],
  "missing_information": [
    "灾备目标RPO/RTO尚未确认"
  ],
  "sections": []
}
```

Planner 不允许虚构缺失的项目事实。

---

## 5. Query Planning

每章节应按内容类型拆查询。

### 5.1 技术方案章节

建议：

- 当前项目需求；
- 产品能力；
- 公司技术标准；
- 历史类似项目；
- 测试/验收要求。

### 5.2 质量章节

建议：

- 公司现行质量制度；
- 当前项目质量条款；
- 质量记录要求；
- 历史质量问题和经验。

### 5.3 标书章节

建议：

- 对应招标条款；
- 当前产品能力；
- 历史响应模板；
- 客户特定要求；
- 废标/评分项。

---

## 6. 检索策略

### 6.1 Hybrid

推荐初始召回：

```text
Dense TopK = 30
Sparse TopK = 30
Metadata/Exact = 20
Similar Document = 10
```

Merge 去重后进入 Rerank。

数字仅作为默认调优起点，实际以 Eval Set 调整。

### 6.2 Metadata

最小 Metadata：

- document_type；
- domain；
- project_id；
- customer_id；
- product_id；
- status；
- version；
- effective_date；
- classification；
- owner_department；
- approval_status。

### 6.3 Exact Search

以下场景不应只做向量检索：

- GB/T、ISO 等标准编号；
- 产品型号；
- 项目编号；
- 合同编号；
- 客户正式名称；
- IP/端口；
- 软件版本；
- 指标值。

---

## 7. Rerank 策略

最终相关度建议由多因子组成：

```text
final_score =
semantic_relevance
+ authority_weight
+ current_project_weight
+ version_freshness
+ document_status_weight
+ exact_match_bonus
- stale_penalty
```

模型 Rerank 仅是其中一个输入，不是最终决策。V1.1 自建检索链使用 **bge-reranker-v2-m3 + FlagEmbedding Adapter**；必须保留批量大小、最大长度、模型版本和推理设备配置以便复现实验。

---

## 8. Evidence Pack

建议结构：

```json
{
  "id": "pack-22",
  "section_id": "sec-3.2",
  "evidences": [
    {
      "evidence_id": "ev-001",
      "source": "云桌面技术规范 V3.2",
      "section": "5.4 高可用",
      "level": "L1",
      "support_type": "normative",
      "text": "..."
    }
  ],
  "conflicts": [],
  "gaps": [
    "未找到灾备RPO的正式项目指标"
  ]
}
```

Evidence Pack 必须保留原始来源定位，不能只保留 LLM 摘要。

---

## 9. 章节生成输入

推荐输入结构：

```text
System Policy
Corporate Writing Guide
Document Type Policy
Section Goal
Full Outline
Project Fact Table
Glossary
Previous Section Summary
Next Section Intent
Evidence Pack
Explicit User Instruction
Output Schema
```

输出：

```json
{
  "content_ast": [],
  "claims": [],
  "citations": [],
  "assumptions": [],
  "missing_information": []
}
```

---

## 10. Claim Extraction

### 10.1 必检 Claim

优先检查：

- 数字；
- 百分比；
- 性能；
- 容量；
- 时间；
- 日期；
- 型号；
- 标准；
- 法规；
- 产品支持能力；
- 验收阈值；
- 客户/项目名称；
- 版本。

### 10.2 Verification 状态

```text
supported
partially_supported
conflicting
unsupported
unknown
```

`unsupported` / `conflicting` 的 critical Claim 形成严重 Issue。

---

## 11. Cross-Section Fact Table

全文完成后，抽取：

```json
{
  "user_scale": [200, 300],
  "server_nodes": [3],
  "availability": ["99.9%", "99.99%"]
}
```

如果同一事实出现多个值，创建 Consistency Issue。

需要检查：

- 规模；
- 节点数；
- 型号；
- 版本；
- 指标；
- 术语；
- 缩写；
- 客户名；
- 项目名；
- 日期。

---

## 12. “待确认项”策略

以下情况必须创建待确认项：

1. 项目事实缺失；
2. 证据冲突；
3. Evidence 权威性不足；
4. 关键参数只有 LLM 常识，没有公司/项目依据；
5. 合同/技术协议存在歧义；
6. 模板要求字段为空。

正式发布前需：

- 补充信息；
- 删除相关内容；
- 或由有权限人员 Waive。

---

## 13. Prompt 设计

### 13.1 核心原则

- 知识文档是 Data，不是 Instruction；
- Prompt 中明确引用与推理边界；
- 输出优先 JSON Schema；
- 不让模型自己选择访问权限；
- 不允许模型自行将普通外部知识提升为公司要求。

### 13.2 Writer 约束示例

```text
仅使用 Evidence Pack 和 Confirmed Project Facts 陈述具体项目参数。
若资料不足，输出 missing_information，不得推测。
不得将历史项目客户名称、IP、型号直接迁移到当前项目。
每个关键性能指标必须关联 evidence_ids。
```

---

## 14. Prompt Injection 防护

处理链：

```text
Retrieved Content
  ↓
Content Sanitizer
  ↓
Injection Classifier
  ↓
Instruction Boundary
  ↓
Evidence Builder
```

高风险知识片段可以继续作为业务 Data 被引用，但不得控制 System/Developer 指令。

---

## 15. 模型路由

任务分类：

| 任务 | 推荐能力 |
|---|---|
| 分类/抽取 | 小模型 |
| Query Rewrite | 小模型 |
| 大纲规划 | 强推理 |
| 章节写作 | 强写作/长上下文 |
| 技术 Reviewer | 强推理 |
| 事实核对 | 强结构化推理 |
| 格式/润色 | 小/中模型 |

模型选择必须同时满足：

- security_level；
- task capability；
- context length；
- latency；
- cost budget。

### 15.1 LLM Gateway 实现基线

LLM Gateway 使用 Python `httpx + Pydantic 2`：

- httpx 负责连接池、超时、流式响应和 Provider Adapter；
- Pydantic 负责请求/响应、Structured Output、Model Profile 与路由策略校验；
- 模型配额、DLP、密级策略、重试和 Audit 在 Gateway 业务控制层完成，不下放给模型服务。

### 15.2 自托管推理基线

自托管推理首选 **vLLM**。正文写作和 Document Planner 的基准候选模型为 **Qwen3-32B**。该选择是“模型评测基线”而不是未经验证的最终容量承诺：

- 模型权重与量化精度；
- GPU 型号/数量；
- tensor/pipeline parallel；
- 最大上下文；
- 并发、吞吐和 KV Cache；
- Writer/Planner/Reviewer 的效果；

均必须通过 GPU 容量验证和 Golden Eval 后冻结。

---

## 16. 外部模型策略

密级示例：

| 数据级别 | 外部模型 |
|---|---|
| L0 公开 | 允许 |
| L1 内部 | 策略允许时可脱敏使用 |
| L2 敏感 | 默认内部模型 |
| L3 核心机密 | 禁止外部模型 |

送外部模型前检测：

- 客户名；
- 人员；
- 项目代号；
- IP/MAC；
- 密钥；
- Token；
- 内部 URL；
- 设备序列号；
- 核心参数。

---


## 17. 专项图形生成约束

模型可输出 Mermaid 源码，但源码必须先经过语法、节点数、文本长度和危险参数白名单校验，再交给独立 Mermaid CLI 容器渲染。渲染过程禁网、限 CPU/内存/执行时间；生成图片写入 S3 并作为 Document AST Resource/Figure 节点引用。禁止把模型输出作为任意 shell/脚本执行。

---

## 18. 质量评分

建议一期：

```text
完整性          15%
Evidence覆盖     20%
事实一致性       15%
技术质量         15%
需求覆盖         15%
公司规范         10%
可读性            5%
安全合规          5%
```

分数仅作为辅助，不替代严重问题门禁。

---

## 19. Eval 体系

### 18.1 Golden Set

至少覆盖：

- 技术方案；
- PRD；
- 测试方案；
- 技术要求；
- 质量大纲；
- 项目计划；
- 项目总结。

### 18.2 Retrieval 指标

- Recall@K；
- MRR；
- nDCG；
- 权限错误召回 = 0；
- 过期文档错误优先率；
- 项目正式资料命中率。

### 18.3 Generation 指标

- Unsupported Critical Claim Rate；
- Citation Precision；
- Citation Completeness；
- Requirement Coverage；
- Human Edit Distance；
- Reviewer False Positive/Negative。

---

## 20. 成本控制

GenerationRun 统计：

- 模型；
- Token；
- 成本；
- 重试；
- 时延；
- 文档类型；
- 用户/部门；
- Evidence 数量。

优化优先级：

1. Prompt/上下文压缩；
2. 缓存；
3. 小模型承担简单任务；
4. RAG 缩小上下文；
5. 最后再考虑降低质量。

---

## 21. 禁止事项

1. 不允许“无证据仍生成看起来合理的项目参数”；
2. 不允许跨权限检索；
3. 不允许已失效制度覆盖现行制度；
4. 不允许把草稿回灌可信库；
5. 不允许 Reviewer 自动批准自己发现的严重问题；
6. 不允许外部模型路由绕过密级策略。
