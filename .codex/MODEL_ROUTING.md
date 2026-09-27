# EID Codex 分级模型路由

核验时间：2026-09-14（America/New_York；UTC 2026-09-15）。

## 本机结论

- 实际 CLI：`codex-cli 0.154.0`，npm 安装于 `D:/npm-global/node_modules/@openai/codex`。PATH 的 `codex` 经过 OpenCodex 包装；验证使用同一安装的原生二进制。
- 本会话配置目录：`C:/Users/virtualink/AppData/Roaming/orca/codex-runtime-home/home`；另有 `C:/Users/virtualink/.codex`。本次未直接编辑任何全局 config.toml。活动 Orca 配置修改前后 SHA-256 相同；另一份用户配置在工作期间哈希变化，已观察到主推理强度 high → medium，保留当前内容，未回滚该变化。
- 项目在当前配置中已受信任，App Server `config/read` 确认 `.codex/config.toml` 是有效 project layer。未修改信任或权限配置。
- `codex debug models` 返回 50 个条目，其中包括 OpenCodex 的其他路由条目。目录可见不代表每个条目都能成功推理；仅下面三个模型完成本次真实调用。完整的精简目录快照见 `routing-evidence.json`。

| 用途 | 角色 | 模型 / effort |
| --- | --- | --- |
| 搜索、定位、资料整理 | default | gpt-6-luna / low |
| 常规编码 | eid_coder | gpt-6-sol / medium |
| 常规测试 | eid_tester | gpt-6-sol / medium |
| 代码审查 | eid_reviewer | gpt-6-sol / xhigh |
| 复杂排障 | eid_debugger | gpt-6-sol / xhigh |
| 架构分析 | eid_architect | gpt-6-sol / xhigh |
| 高风险修改 | eid_high_risk | gpt-6-sol / xhigh |

Luna、Terra、Astra 的相对定位同时符合本机目录与 [OpenAI Docs 模型说明](https://learn.chatgpt.com/docs/models)。此处不承诺固定费用或节省比例；实际计费和供应商路由由当前账户及 OpenCodex 设置决定。

## 改动与生效方式

- 新建七个 `.codex/agents/*.toml`，使用已验证的 `name`、`description`、`developer_instructions`、`model`、`model_reasoning_effort` 和部分只读角色的 `sandbox_mode`。
- `.codex/config.toml` 将默认子代理设为 Luna/low，保留最多 10 个子代理；项目级 `hide_spawn_agent_metadata=false` 使 `agent_type` 可选，模型临时覆盖参数仍隐藏。
- 根 `AGENTS.md` 原有 BMAD 约束保留，追加角色选择、授权范围、一次性委派、失败升级及不可用回退规则。路由由主代理遵循规则执行，不存在 TOML 自动分类或自动重试引擎。
- 项目 `default.toml` 覆盖本项目的通用探子；全局 default 文件保留。自定义角色通过目录自动发现，无需旧版 `[agents.<role>] config_file` 注册形式。参见 [OpenAI Docs 子代理说明](https://learn.chatgpt.com/docs/agent-configuration/subagents)。
- 主会话模型、供应商、认证、MCP 和权限继承现有值。本次新会话核验主模型仍为 Astra/medium。

在本项目目录启动新的 Codex 会话后，直接要求“按 AGENTS.md 选择角色”。已有会话的工具参数可能保持旧状态：本次原对话的 spawn 工具没有 `agent_type`，另起的 0.154.0 CLI 已实际暴露并成功使用该参数。不能把写文件视为旧会话已经热更新。

主代理亲自执行任务时，用实际支持的参数选模型，例如 PowerShell：

```powershell
codex -m gpt-6-sol -c 'model_reasoning_effort="medium"'
codex -m gpt-6-sol -c 'model_reasoning_effort="xhigh"'
```

当前 CLI 的 `-p` 使用独立的用户 profile 文件，不以旧版项目内 `[profiles]` 示例作为路由依据。

## 已完成验证

1. 七个 TOML 可解析，角色必填字段、模型名和 effort 均匹配当前目录。
2. 在临时空 CODEX_HOME 中，使用实际 0.154.0 App Server `--strict-config` 检查项目配置及每个角色的配置键；全部通过。真实用户目录和凭证没有复制到临时目录。
3. 在实际 CODEX_HOME 中，通过 `initialize` 和 `config/read` 确认项目层、默认模型及角色选择开关；通过。
4. 最小真实调用：主会话 `01a0a315-8dfb-7a32-8a6a-5e44e497a16b` 分别调用 default、eid_coder、eid_reviewer，不读写项目文件。子代理日志中的 `session_meta.agent_role`、`turn_context.model/effort` 和 `task_complete` 一致，三者均返回 `ROUTING_OK`，CLI 退出码 0。七个角色均做配置检查，真实派生选取三个档位的代表角色。
5. 活动 Orca 配置哈希与原有 AGENTS.md 字节前缀保持一致；另一份用户配置的工作期间变化单独记录，未覆盖。既有业务改动保留；未提交、推送或启动 Story 开发。

只验证配置、不会调用推理模型的复查命令：

```powershell
python .codex/verify-routing.py
```

脚本检查配置、有效目录和严格解析，打印 `status: PASS`。模型目录查询可能刷新客户端缓存。安装路径变化后传 `--codex-bin <实际 codex.exe 路径>`。实时模型可用性仍需重新执行最小调用，不能用静态检查替代。

重新做真实验证时，在新 CLI 会话中要求：

> 仅验证路由。派生 default、eid_coder、eid_reviewer 三个一次性子代理，fork_turns=none；每个只返回 ROUTING_OK，不调用工具、不读写文件。等待全部结束。随后核对子代理运行日志中的 agent_role、model、effort 和 task_complete，不采用代理自报的模型名作为证据。

## 已知限制

- 现有全局 `disable_response_storage` 是本版本严格解析不识别的旧字段。本次未修改；因此不能声称整个全局配置严格通过。实际正常配置加载通过，新增项目及角色配置的隔离严格检查通过。
- 真实调用期间现有技能目录产生遍历/描述长度提示，OpenCodex WebSocket 产生 HTTP 426 后调用仍完成。这些外围提示不属于本次路由配置修复范围。
- 父会话运行时权限会覆盖角色 sandbox 默认值。本次日志中只读角色继承了 workspace-write；只读行为同时依靠角色指令，本验证不证明操作系统级只读隔离。需要强制隔离时，应在父会话选择相应权限。
- 低档不可用按规则升级；Astra 不可用时，高风险判断、架构结论、最终审查不会降到 Terra。无自动换供应商、虚构模型名或绕过门禁。

## 备份与恢复

修改前备份位于 `.codex/backups/20260915T031357Z-model-routing/`，包含原始 `AGENTS.md` 和 `manifest.json`（原文件哈希、原 Git 状态、全局配置哈希）。项目此前没有 `.codex/config.toml` 或项目角色文件。

`installed-files.json` 记录本次新增/修改文件及安装后的 SHA-256。恢复前结束使用这些角色的会话，先比对该清单；文件若已有后续改动，先另备份并人工合并，不能直接覆盖。

恢复时仅把清单中的项目 config.toml 和七个角色 TOML 移到备份目录下的停用目录（离开 `.codex/agents`），再从备份恢复 AGENTS.md；或只删除 AGENTS.md 的 `eid-model-routing` 标记块以保留后来新增内容。验证脚本和说明可一并归档。不要删除整个 `.codex`、修改全局配置或清理任何业务文件。备份目录不是代理加载目录，保留它不会启用路由。
