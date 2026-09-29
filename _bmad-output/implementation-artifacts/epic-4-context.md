# Epic 4 Context: Obtain controlled AI proposals without silent edits

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让作者在受控模型路径下获得有依据的章节、Copilot 和结构化图表提案，并由当前授权的用户逐项接受；模型、检索或后台任务不得静默修改正文。软件开发与运行验收分开：当前仅做源码、静态与编译检查，运行测试及真实环境验收记 `not-run`。

## Stories

- Story 4.1: Use a policy-approved model and versioned Prompt
- Story 4.2: Propose an outline and generate bounded sections
- Story 4.3: Target the complete Copilot operation catalog
- Story 4.4: Accept only selected, current AI changes
- Story 4.5: Resolve pending facts and safely propose tables or diagrams

## Requirements & Constraints

- 模型调用必须依次分类、DLP、策略、脱敏、路由；L3 禁止外发，L2 默认内部且外部例外未配置时拒绝，L1 外发必须按批准策略脱敏。拒绝不能降级到宽松提供商；不可信知识、附件或标书内容不能提升工具和权限。
- 模型和 Prompt 配置版本化；请求有 capability、上下文、token、成本、配额及超时限制；结构化响应按 schema 校验，最多一次修复，错误与持久重试状态可追踪。普通日志、浏览器存储与配置界面不得暴露敏感原文或密钥；保留哈希、用量和路由决定审计。
- 确认的上下文与大纲、章节 Evidence Pack 和当前来源权限是生成输入；持久化阶段/错误/取消/缺证状态；生成结果只作为包含 Claim、引用、假设、缺失信息和溯源的提案。整稿组装需跨章节检查，不能绕过人工接受。
- Copilot 操作须解析真实目标、声明只读或写入家族；只读不得修改 AST，写入仅返回 Patch、定位问题或待确认项。目标缺失、输入无效、无权或不安全输出要有明确失败状态。
- Patch 以稳定块 ID、基础版本/修订和目标散列定位；由 API 在当前 ACL、来源、策略及并发检查后仅应用用户选定且兼容的变更，创建一个不可变版本；拒绝不改正文。过期/越权/重复请求不能改变正文或双重应用。
- 待确认事实须带位置、依据、状态和历史；未声明的豁免权限拒绝，严重安全门禁不可豁免。表格采用验证后的 AST；Mermaid/PlantUML 不得执行任意代码或远程资源，非法或不支持的语法须显式失败。

## Technical Decisions

- 产品工程只有 Web、API、Worker；模型与知识 Gateway 是内部共享模块，不另建监听服务。API 独占文档 head/权限/人工接受，Worker 只能保存任务状态与受限提案。
- PostgreSQL 的不可变文档版本和 AST 是正文真相；后台任务、事件、输出由持久层承载，SSE 是观察通道而非任务真相。后台阶段及最终提交重新鉴权、校验版本/租约/策略/撤权。
- HTTP 模型适配使用 httpx/Pydantic；确定性本地模型替身只能证明契约，Qwen3-32B 只是评估候选，不表示已生产批准或真实效果。危险渲染工具应独立隔离、禁网与业务凭据、限制资源并净化输出。
- 当前不得启动测试套件、服务、迁移、浏览器或实际环境验证；可编写测试代码并做静态/类型检查和离线编译。每个来源 Story 的 L 与 Epic 13 的 R/P 验收保持 `not-run`，不得将静态结果冒充运行通过。

## UX & Interaction Patterns

- 保留原型六个 Copilot 按钮、三标签、输入与响应区域的视觉和入口；扩展操作走“更多”，提交前显示操作、章节/选区及上下文，未配置/禁止模型明确禁用。响应只作安全文本或验证后的节点，不用不可信 HTML。
- 状态显示真实排队、检索、证据、生成、校验、Diff、失败、取消和缺证；短暂 toast 不代替持久任务。AI Diff 展示前后、逐项选择和溯源；冲突保留提案并进入版本对比，不覆盖手工正文。
- 待确认项显示真实计数、定位、原因、决议和授权历史；图表预览及错误明确区分，不能呈现虚构的生产指标或通过状态。

## Cross-Story Dependencies

- 4.1 基于已完成的 Evidence Pack 和任务观察接口；4.2 基于 4.1、Claim/引用及已确认大纲；4.3 基于 4.2；4.4 基于 4.3 和版本冲突；4.5 基于 4.4 与安全附件管道。来源撤权和文档 revision 变化贯穿全部调用与接受流程。
