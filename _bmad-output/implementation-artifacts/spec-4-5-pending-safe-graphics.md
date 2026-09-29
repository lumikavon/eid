---
title: 'Story 4.5 待确认事实及安全表格/图形提案'
type: 'feature'
created: '2026-09-29'
status: 'review'
baseline_commit: '039cf97e17cc70d2638c0483bf7be7b5d40e357a'
context:
  - '_bmad-output/implementation-artifacts/epic-4-context.md'
---

## Intent

将待确认项以定位、来源、原因、状态与决议历史持久化；已授权作者仅能依据当前有效证据确认事实，不授予未知豁免权限。结构化表格及严格受限 Mermaid 图形进入逐项候审 Patch；不支持的 PlantUML 或非法/远程/资源超限的内容明确阻断。

## Bounds

- API 独占决议与文档 head；模型与 Worker 仅生成候审数据，不更新正文。
- 事实确认是人工确认行为，不能把模型生成视为已证实；未知豁免权限与严重安全门禁失败关闭。
- 图形生成只允许定界 grammar 和纯静态 SVG，渲染器不可有网络/进程/数据库凭据；实际服务与沙箱验收 `not-run`。
- 不执行测试套件、迁移、服务、浏览器和真实环境验收；仅离线编译/静态审查到 `review`。

## Work

- [x] 待确认项持久化、定位及版本化人工处理记录，允许当前 ACL 的事实确认，拒绝豁免。
- [x] Copilot 结构化输出严格解析 table/Mermaid；安全受限图形转义/限额，PlantUML 显式不支持。
- [x] 将结构化候审内容接入 4.4 的服务端选择/版本 CAS、来源复核；Web 显示预览及真实待确认计数/处理。
- [x] 编写针对越权、重复、过期、恶意图语法及表格边界的契约与安全测试源码。

## Implementation Notes

- 待确认项由当前 Copilot `create_pending` 结果登记，固定当前文档版本/节/块/目标哈希和来源；确认仅记录作者输入、原因、动作及审计，不自动将模型值写入正文，也不提供豁免操作。
- 表格节点限制行列与单元格长度；图形仅纯 Python 解析 `flowchart TD` 的简单节点/箭头并转义生成静态 SVG，禁止链接/指令/任意 HTML，不调用 Mermaid/PlantUML 运行时。`plantuml` 返回 `GRAPH_UNSUPPORTED`。AST 保存对静态 SVG 做确定性重算。
- 企业链无法在短事务内重新证明时失败关闭；真实来源、沙箱、工具资源限制及 UI 截图均待运行验收。

## Verification

- `python -m compileall -q edw-api/src migrations/versions tests/contract tests/security`
- `npm --prefix edw-web run typecheck`
- `git diff --check`

测试、迁移、服务、浏览器、外部来源及沙箱运行均 `not-run`。

2026-09-29：Python `compileall`、Web `typecheck`、`git diff --check` 退出 0。测试套件与运行验收 `not-run`。

## 静态审查记录

候审路径已检查目标稳定 ID、文档版本 CAS、当前 ACL/证据及只读 Preview 的安全边界；对 Mermaid 的限定语法与输出重算作源码审核。尚无独立审查或运行时矩阵测试结果，本记录不作验收结论。

Epic 4 跨 Story 返修：待确认项重复登记与确认前重新核验当前来源和提案；历史查询覆盖旧文档版本；Mermaid 拒绝控制字符与不规范语法，表格拒绝非法控制字符/代理项；PlantUML 明确返回不支持。新增源码级反例，测试未运行。返修后 Python `compileall`、Web `typecheck`、`git diff --check` 退出码均为 0（换行符警告不影响退出码）。
