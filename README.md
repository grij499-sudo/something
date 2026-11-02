# something：ChatGPT 与 Codex 的共享项目

**当前使用方式：ChatGPT 写任务，Codex 在本机执行，通过 GitHub 交换计划、代码和结果，再由 ChatGPT 审核指定版本。**

目标仓库是 [`grij499-sudo/something`](https://github.com/grij499-sudo/something)。用户已确定只使用现有订阅，当前不引入额外模型 API 计费。Secure MCP Tunnel 配置暂停，已安装的本地 MCP 服务保留。

## 现在开始：先完成一次任务交接

第一项任务已经写好：[T001：GitHub 协作往返验证](coordination/tasks/T001/TASK.md)。

在本机 Codex 打开这个仓库，交给它以下内容：

> 请保留现有改动，从 origin 获取并进入 `task/T001-github-handoff` 分支；如有不适合切换的改动，使用独立工作副本处理。读取 `AGENTS.md` 和 `coordination/tasks/T001/TASK.md`，执行 T001，把结果写入该任务目录的 `RESULT.md`，提交并推送到任务分支。继续使用现有订阅登录方式，不配置 Platform API key 或 Tunnel。完成后返回任务分支、最终提交 SHA、结果文件链接；遇到 GitHub 登录或权限阻塞时说明具体缺项。

完成后，在 ChatGPT 中提供分支和提交 SHA，要求按这个确切版本读取任务、检查文件、结果报告及改动差异。审核报告写入同一任务目录的 `REVIEW.md`，其中记录被审核的提交。当前通过用户消息触发各阶段，未部署自动会话互聊或自动调度。

## 当前进度

| 项目 | 状态 |
| --- | --- |
| GitHub 共享项目 | ChatGPT 端写入与回读已通过；本机 Codex 的推送回传由 T001 验收 |
| MCP 服务 | 已实现四个只读工具；云端 Linux x86_64 环境的 30 项测试通过 |
| 目标电脑 / DGX 安装 | 用户回传的本地验证已通过，连接检查文件哈希与发布版一致 |
| Secure MCP Tunnel | 已暂停；费用与账号条件未确认，不继续创建凭据或启动连接 |
| ChatGPT 网页调用本机文件 | 尚未接通；目前通过 GitHub 读取已推送版本 |

具体证据与待验证项见 [验证记录](project-files-mcp/VERIFICATION.md) 和 [连接检查文件](coordination/connection-check.md)。

## 本地 MCP：保留，暂不继续网页接入

本地安装和 `verify_local.py` 验证已经由用户完成，当前无需重装。服务与安装说明保留在 [project-files-mcp](project-files-mcp/README.md)。

官方 Tunnel 需要 Platform 运行密钥与使用权限；需要密钥本身不等于调用模型 API，但独立费用与账号门槛尚未确认。[S1] 在用户改变当前决定前，不创建或使用 Platform 凭据，不启动 Tunnel，不将 Codex 改为模型 API key 登录。

## ChatGPT 与 Codex 怎样协作

| 内容 | 放在哪里 | 使用方式 |
| --- | --- | --- |
| 任务目标与验收条件 | 从 `coordination/templates/TASK.template.md` 复制到任务文件 | ChatGPT 完成计划后写入；Codex 开工前读取 |
| 代码与文档 | 对应任务分支 | Codex 本地修改、验证并提交；ChatGPT 按明确分支或提交读取 |
| 执行结果 | 从 `RESULT.template.md` 复制 | 记录每项要求的实现位置和实际验证证据 |
| 独立审核 | 从 `REVIEW.template.md` 复制 | 读取原任务与实际代码，对必需项逐条核查 |
| 未提交的本机文件 | 本机工作副本 | 由本机 Codex 读取；当前网页协作以已推送版本为准 |

GitHub 和本机工作副本通过提交、推送和拉取同步。对不上时先检查分支、提交号和本地改动。每轮交接都提供任务编号、分支和实际提交，避免仅依赖聊天中的概述。

每个任务使用独立分支，保留既有改动，不强制推送覆盖远端。网页端写入后，本机 Codex 更新同一任务分支并检查差异；本机修改后提交并推送，网页再按该提交读取。当前 MCP 只提供读取工具，修改由 Codex 或具有相应权限的 GitHub 工具完成。

## 目录

- `project-files-mcp/`：服务、安装器、验证脚本与测试。
- `coordination/tasks/T001/`：首次协作验证的任务，后续保存执行报告和审核报告。
- `coordination/templates/`：任务、执行结果、独立审核和协作规则模板。
- `coordination/connection-check.md`：GitHub 与本机 MCP 共用的无敏感内容检查文件。
- `AGENTS.md`：在本仓库工作的约定。

本仓库为公开仓库。安装产生的 `.local/`、`.venv/` 及 `.env` 已列入忽略规则；真实凭据和其他项目数据应保留在相应的授权范围内。MCP 的文件排除规则不能识别所有正常命名文件中的秘密，完整范围与限制见服务说明。

## 官方资料

- [S1：Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [S2：Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server)

