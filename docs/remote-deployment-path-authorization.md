# EID 专用部署路径变更方案

状态：用户已明确授权。2026-09-17 经修复、独立审查及同包实时 check 后，五个基础服务已在 `/opt/eid/release-20260917-002` 完成纠正，private cgroup、原卷/网络、专有持久消息及普通隔离守卫通过。详细恢复链见当日接续记录；不等于迁移、九服务或 Story 验收完成。

## 请求的一项增量授权

允许在 `seadee-develop` 的 `/opt/eid` 新建 root:root、0700 的 EID 专用部署目录，并将 EID 发布文件、Compose、只读配置和归属收据的路径契约切换到该目录。

继续使用现有 Compose project `eid-remote-dev`、现有 owner nonce、专属网络及五个 named volume。保留 `/opt/docker/eid` 和所有既有数据；不修改共享 `/opt/docker` 的归属或权限，不操作其他项目，不增加主机挂载策略。现有七端口 SSH 转发规则不变。

## 为什么需要另行授权

原环境授权限定 `/opt/docker/eid`，不包括新路径；用户随后单独批准本方案，新增 `/opt/eid` 的限定权限。已批准的 sshd 最小转发方案已执行并独立复核通过。

远端 `/opt/docker` 是 UID197610、GID197121、0755；即使子目录为 root:root、0700，父目录所有者仍能重命名和替换 `eid`。目前文档将该所有者列入信任边界，不能声称部署路径为 root 独占控制。

纠正旧容器 cgroup 配置的执行草稿在验证后将绝对路径交给 Compose/Docker 重新解析。独立审查确认文件描述符检查、哈希及项目锁不能绑定实际消费的路径；因此该草稿未获执行批准。仅把 Compose 复制到 root 目录也不足以保护仍经旧路径解析的 bind source。

只读现场核验：`/` 为 root:root、0555，`/opt` 为 root:root、0755；`/opt/eid` 不存在（包括符号链接检查）。执行时必须再次核验；如果已存在则停止，不接管。

## 获批后的具体实施边界

1. 固定唯一新 root 为 `/opt/eid`，只接受 root 控制、无符号链接、无组/其他用户写权限的祖先；不引入任意路径开关。同步环境 YAML、渲染、staging、收据和守卫，并测试旧/新路径混淆与越界拒绝。
2. 保留原归属收据，明确记录同一 owner nonce 的路径变更来源。从本地冻结且校验过的候选包创建新 release，不从旧共享路径复制执行代码或配置，不移动任何持久数据。
3. 过渡检查只接受已记录的五个旧完整容器 ID 使用其既有路径；替换后的容器只接受新路径。外来资源与新旧 EID 目录、原卷真实路径的重叠检查全部保留。普通隔离守卫继续拒绝 host cgroup namespace。
4. 修复草稿的挂载顺序误报、上传目录字符规则及缺失执行入口，完成独立审查后才执行。禁止直接运行 `.local/remote/acceptance-20260916/correction_runner.py` 当前草稿。
5. 在部署锁下重新核对主机、目录、owner、完整容器/镜像 ID、网络、卷及绑定配置；逐个重建五个基础服务，使用 `--no-deps --no-build --pull never` 和有限等待。保留原卷、网络及旧 releases，不执行 down、清理或数据删除。
6. RabbitMQ 保持 hostname `5e8cac11b089`、节点 `rabbit@5e8cac11b089` 和现有 Mnesia 目录；以专有持久验证数据检查重建前后用户/队列/消息保留，不删除或消费原业务数据。保留验证对象并记录归属。
7. 检查五个新容器真实 cgroup namespace、相同卷身份、健康状态、原始守卫及隧道；确认无其他项目资源变化。失败保留现场和证据，不自动执行破坏性回退或用旧代码猜测恢复。
8. 五服务纠正通过后，才沿既有项目授权继续初始化、迁移、fixture、三工程运行、日志和浏览器验收。Story 仍须单独完成测试、独立审查、状态核验及提交。

本方案不要求修改 `/opt/docker` 权限，也不包含生产发布、Git Push、删除数据库或重建数据卷。

## 当前已完成与未完成

- 最小 SSH 转发、允许/拒绝路径和正式隧道监听守卫已通过；恢复材料已放在 root 控制的 `/etc/ssh/eid-forwarding-backup-20260916` 并通过独立复核。
- 九服务 Compose 的 private cgroup 配置修复完成；相关296项测试及补充111项测试通过，配置增量独立审查通过。
- `/opt/eid` 已独占创建，root:root 0700，dev/inode 为 64768/29497029；候选目录 `/opt/eid/release-20260917-002`。创建来源保存在 `.eid-root-transition.json`，具体证据为 `.local/remote/acceptance-20260916/trusted-execute-20260917-002.json`。
- 首次探针失败与五服务恢复日志均保留；最终 `.local/remote/complete-20260917/execute-003.json` 退出0，消息内容及持久属性验证后已放回，完整恢复时定义快照匹配。首次尝试前历史完整快照缺失仍如实记录。禁止重放这些一次性入口或删除现场；迁移、fixture、九服务和Story验收另行记录。
- 旧路径执行草稿的审查结论与禁止执行标识：`.local/remote/acceptance-20260916/REVIEW-STATUS.md`。
