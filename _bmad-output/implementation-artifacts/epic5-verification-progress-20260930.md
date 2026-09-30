# Epic 5 验证进展（未关闭）

## 已执行结果

- 本地精选合同/安全回归：35 passed（本轮最近一次 1.04s）；随后新增撤权追踪用例及上游链检查，尚未重跑。
- 前端领域适配器与文档 API：27 passed；发现 UUID 正则遗漏第四段并已修复。
- 前端 typecheck 通过；build 通过，有大 chunk 警告；lint 0 errors、21 warnings。
- 前端 TemplateWorkspace 测试套件在 Node 环境因 `window is not defined` 收集失败，不能标记通过。
- 全量 `uv run --no-sync pytest -q tests/contract tests/security tests/ops --maxfail=20`：12 failed、769 passed、1 skipped、8 errors（30.84s）。尚未逐项完成基线归因。日志：`C:\Users\virtualink\.local\share\opencode\tool-output\tool_0f17d1063001yvrQO6AtS7OwbW`。

## 同候选打包与远端验证

- 验证主机：seadee-test，openEuler 24.03 LTS-SP2、x86_64；Docker 18.09（API 1.39），Compose v2.39.4 通过 `/usr/local/lib/docker/cli-plugins/docker-compose` 直接运行。
- 打包镜像：`openeuler/openeuler:24.03-lts-sp2`；已核对容器 `/etc/os-release`。远端从 Docker Hub 拉取超时，使用本地 save/scp/load。
- 候选 03 源码摘要：`27316df60fb9bc713d744009bf72c7e5b76f4fbc93f24502e970699d25c1998a`。
- 本地候选：`C:\Users\VIRTUA~1\AppData\Local\Temp\opencode\eid-epic5-candidate-03`。
- 远端目录：`/opt/eid-test/epic5-20260930-03`。
- 本地和远端 Compose `run --rm pack` 均退出 0；逐文件 SOURCE.sha256 校验成功；`cmp eid-candidate.tar.gz output/eid-candidate.tar.gz` 退出 0。
- 产物 SHA256：`769ce2cc697221fa38f0938cc4147c51878c6f1c3a7fd150c5078427370466cd`。
- 避免旧 daemon 的 platform API 错误，打包容器内显式验证 `uname -m = x86_64`。
- 候选 03 在本地与远端相同验证镜像中执行只读、无网络精选回归：均 33 passed（5.54s / 2.28s）。验证镜像是 Python 应用基础镜像加 pytest/Pillow，**不是 openEuler 应用运行镜像**；候选源码通过只读挂载/PYTHONPATH 加载，未使用镜像内旧源码作为结果。
- 未启动十服务应用栈、未执行真实数据库迁移或授权 API/worker/web 端到端验证。以上证据只证明容器打包与离线回归。
- 候选 03 后又修复 UUID、增加撤权回归和上游链检查，**当前工作树已不同于远端候选 03**，需生成下一候选并重新验证。

## 独立审查与剩余事项

- Codex 文件读取审查因本机沙箱启动失败而超时；Claude CLI 也超时，未得到审查结论。
- 将关键后端 diff 直接交给独立 Codex 会话后获得静态发现（无工具执行）。这不是完整 BMAD 三层审查，也不是批准。
- 已按发现修复：需求引用先核验编辑权再读取链接；核验所有保留 source_refs；跨文档覆盖问题不再伪装成本测试方案区块；不可访问链接返回 unavailable；same_defect 容忍空 details。
- 初步排除：投影调用遗漏（editor_repository.save_document 已调用 project）；modify 缺少当前复查（accessible_result 已重新校验）；旧链接静默通过（coverage 已标 stale）；引用偏移需与目标正文对齐，非来源全文偏移。
- 待继续核实：显式基线范围（目前仅引用到的需求文档）、完整链覆盖分子、同文档链接保存后的过期策略、多 Claim 稳定缺陷身份、技术要求 UI 的来源绑定入口、数据库事务与独立并发授权回归。
- BMAD step-04 要求同级模型三层独立子代理；当前没有子代理工具。按其降级协议生成三个自包含交接 Prompt，并暂停等待独立审查结果。

## 七故事验收状态

| 故事 | 本轮状态 |
|---|---|
| 5.1 固定版本八类审校 | 已检查相关版本/来源逻辑及精选回归，完整运行链未验证 |
| 5.2 筛选、溯源与历史 | 引用关键字匹配与真实覆盖初版，UI 交互/筛选一致性未完整验证 |
| 5.3 人工处置 | Modify 后独立复查关闭路径初版，事务与端到端未验证 |
| 5.4 技术方案 | 相关规则回归通过，完整创建→生成→接受→审校未验证 |
| 5.5 PRD | 保留用户工作并修复引用续接/字段检查，完整来源事务未验证 |
| 5.6 测试链 | 双向投影/版本导航/覆盖初版；链分子与显式分母仍待完善 |
| 5.7 可测量技术要求 | 结构字段/阈值保护/规则初版；来源 UI 与完整改写接受链未验证 |

未提交或推送 Git；未修改 seadee-develop；未删除既有远端数据。规格保持 in-review，所有未完成执行项保持未勾选。
