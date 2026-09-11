# Story 1.1 执行检查点与视觉验收方法待决项

日期：2026-09-10。目标 Epic 1，基线提交 `3440d2f89647aaeacf49213285c055dbe365df7d`。

## 当前状态

Epic 1 与 Story 1.1 均为 `in-progress`。Story 1.2—1.6 保持 backlog。完成并提交的 Story 为 0；尚未启动正式独立代码审查、Epic 集成验收或复盘。没有提交或推送。

## 已落地内容与证据边界

- 三工程 React/Vite、FastAPI、Celery 骨架，根级 Python/pnpm 锁文件与 Docker Compose。
- 本机专用 `eid-local` 环境实际运行 PostgreSQL、Keycloak、RabbitMQ、Redis、SeaweedFS、NGINX 和三个工程。入口为 `http://localhost:18080`；保留原有占用 8080 的服务。
- 实际 Keycloak Code + PKCE S256 登录与数据库身份映射通过；浏览器令牌仅驻留内存。缺少 PKCE 的授权请求被拒绝。
- 数据库停止时 readiness 拒绝、进程 live 保持可用，数据库恢复后 readiness 恢复；Worker 修改成员关系被数据库权限拒绝。三项真实环境测试通过（最近运行 51.06 秒），环境已恢复。
- 新增迁移前实际 bucket、RabbitMQ vhost/权限、Keycloak realm/client/PKCE 配置核验；当前本地 `--check-only` 通过。初始化存储先于完整迁移前核验，Alembic 在线迁移入口也调用完整核验。
- `uv run --frozen pytest tests/security tests/contract tests/ops -q`：20 passed、3 skipped。3 skipped 为默认关闭的真实环境测试，已另行显式运行通过，不以跳过作为通过。
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations`：通过。
- 前序 Web 构建、类型检查、4 项 OIDC 单元测试与依赖安全扫描通过；后续实际修改后仍须按范围复核。

这些证据仅覆盖本地环境，不代表企业身份联邦、生产部署、真实 AI 效果或容量验收。

## 视觉失败与恢复尝试

`tests/ux/shell.spec.ts` 以原始原型为参考，仅将演示账户文本替换为对应未登录文本，固定浏览器、viewport 和字体条件，比较顶栏截图 PNG 完全一致。原型源文件未修改。

完整浏览器测试：3 项功能测试通过、6 个 viewport 的严格截图比较失败（1920、1440、1181、1180、1024、768，高度 900）。`.topbar/.brand/.logo/.topnav/#globalSearch/.sidebar` 布局矩形比较通过；截图断言之后的响应提示断言未执行，不能宣称该部分通过。

一次完整运行的解码像素差异：

| 宽度 | 差异像素数 | RGB 最大差值 | 差异包围框 |
|---|---:|---|---|
| 1920 | 1806 | 10,6,1 | 24,0,441,59 |
| 1440 | 2366 | 149,65,64 | 24,0,1411,63 |
| 1181 / 1180 / 1024 / 768 | 各 7247 | 149,54,66 | 70,0,1276,64 |

数据是一次运行的测量值，不作为容差阈值；后续运行可能不同。截图输出在 `test-results/actual-header-*.png` 与 `reference-header-*.png`，会被下一次 Playwright 运行覆盖；保留副本放在本检查点同目录 `story-1-1-visual-evidence/`。

已尝试：原始 CSS 直接复用、关闭 CSS 压缩、移除重复壳层 CSS、同一 context 重复截图、原型增加同样 root 包装的内存副本、HTTP 导航代替 setContent、匹配浏览器激活状态、固定 sRGB/关闭 GPU、试验关闭 Skia 优化或 LCD 文本，以及限定的应用侧合成层探测。未找到可靠的零差异修复；实验性浏览器参数已撤回。没有修改原型、增加容差、掩盖区域或删除失败断言。

独立探针发现 Logo 的差异与模糊 box-shadow 路径有关，移除两边的该阴影可消除 Logo 差异，但这只是诊断证据，不是可接受修复。不能据此断言所有文字与窄屏差异均已归因。主线程另行核验 1181px 顶栏文本 Range 矩形和字体值一致。

原型 SHA-256：`C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`；`git diff --exit-code -- docs/prototype/index.html` 通过。

## 待确认的具体方法

规划要求严格 1:1 并禁止自行处理视觉冲突（`planning-artifacts/epic-1-secure-workspace.md:33`）。当前 PNG 完全一致是实施时选择的自动门禁；项目未指定可接受的渲染误差阈值。不得自行设定数值容差。

建议供用户审阅的方法：原型保持只读；对布局、文字位置、字体、颜色、圆角、阴影、边框和响应条件执行精确属性比较；保存匹配条件下的截图及解码差异；由新的独立审查代理逐项审查差异，任何实际视觉/交互偏离仍须修复。PNG 差异作为必须审查的证据，而不是自动忽略或套用统一阈值。该方法尚未替换当前失败门禁，批准方法也不等于批准当前 UI。

## 用户确认（2026-09-10）

用户回复“允许”，明确批准将 PNG 完全一致改为精确布局/CSS 核验与独立截图差异审查。原型仍保持只读，实际视觉偏离仍须修复；不得把方法批准当作当前 UI 或 Story 验收通过。继续自主串行完成 Epic 1，无需再次请求此项许可。

## 恢复后的必要工作

1. 确定并完成视觉验收方法及全量壳层/窄屏/状态核验，不能把顶栏检查等同整壳通过。
2. 补齐镜像 manifest/显式构建镜像版本、工具链验证覆盖、README 与最终文件清单；复核初始化存储写入前的实际端口归属检查和所有失败路径。
3. 完整独立代码审查（bmad-code-review）及修复；当前没有审查通过结论。
4. 主线程必要验证通过后同步 done，按基线归属暂存并提交 Story 1.1，之后才继续 Story 1.2。

未提交修改包括三工程、deployment、scripts、migrations、contracts、tests、根级依赖/构建配置及本次实施记录。预存 `.agents/`、`.claude/`、`AGENTS.md`、`PROMPT.md`、`_bmad/` 和规划产物保持，不能整体暂存。
