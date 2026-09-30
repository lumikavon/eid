# Epic 5 openEuler 打包与隔离验证

目标为 openEuler 24.03 LTS-SP2（linux/amd64）。该入口打包显式候选源码，包含部署输入、测试、逐文件 SHA-256、候选源码摘要和基线提交；不是预构建镜像或运行验收证明。

```powershell
uv run --no-sync python -m scripts.epic5_candidate --output .local/epic5/candidate
$env:EID_CANDIDATE_DIR = (Resolve-Path .local/epic5/candidate).Path
$env:EID_PACKAGE_DIR = (Resolve-Path .local/epic5/package).Path
docker compose -f deployment/pack.compose.yaml run --rm pack
```

输出目录须预先创建且为空。镜像或候选输入缺失、校验错误、输出已存在都会失败。Compose 不挂载工作树、Docker socket 或凭据目录；打包无网络。`SOURCE.json` 记录实际候选内容，`ARTIFACT.sha256` 记录 tar.gz。记录实际镜像 ID/RepoDigest，标签本身不是不可变镜像身份。

远端只使用 SSH `seadee-test` 和新建 `/opt/eid-test/<候选标识>`；不要调用绑定 seadee-develop 的 `remote_environment.py` 部署操作。检查主机、sudo、Docker/Compose，校验上传候选的 SOURCE.sha256 后运行相同打包 Compose。运行栈必须将 Compose 项目、命名卷和监听端口改为该候选独有值；不得接管已有目录或卷。运行时 wake/model 密钥在主机私有环境文件中创建，不能加入源码或打包目录。迁移使用隔离数据库 eid_local_dev / eid-local-dev-v1；记录命令、退出码、镜像身份、服务状态与真实测试结果。失败写入证据，不能沿用历史通过结果。
