# something：ChatGPT 与 Codex 的共享项目

这个仓库把两条连接放在一起：**GitHub 保存可追踪的项目版本；MCP 让 ChatGPT 读取指定电脑上的项目当前文件。**

目标仓库已确定为 [`grij499-sudo/something`](https://github.com/grij499-sudo/something)。首次安装直接使用这个仓库的本地副本作为 MCP 项目目录，先验证完整通路，再按需要切换到其他项目。

## 当前进度

| 项目 | 状态 |
| --- | --- |
| GitHub 共享项目 | 使用本仓库；服务、安装脚本与协作模板均在版本管理中 |
| MCP 服务 | 已实现四个只读工具；云端 Linux x86_64 环境的 30 项测试通过 |
| 目标电脑 / DGX 安装 | 需要在项目所在电脑执行下面的安装步骤 |
| Secure MCP Tunnel | 需要真实 Tunnel ID、运行凭据及正确的工作区关联 |
| ChatGPT 网页调用本机文件 | 等待实际连接和工具调用验收 |

具体证据与待验证项见 [验证记录](project-files-mcp/VERIFICATION.md) 和 [连接检查文件](coordination/connection-check.md)。

## 先在 DGX / Linux 上安装

要求 Linux、Python 3.11+，以及 Git、Python 虚拟环境和所需网络访问。安装器支持匹配 Linux x86_64 与 ARM64 官方客户端；当前已有的实际运行验证来自 x86_64，ARM64 仍需在目标机器验收。

在准备保存项目的目录打开终端，逐条执行；任意一步报错时先解决错误，再继续：

```bash
git clone https://github.com/grij499-sudo/something.git
cd something
python3 project-files-mcp/setup_local.py --project "$PWD"
python3 project-files-mcp/install_tunnel.py
project-files-mcp/.venv/bin/python project-files-mcp/verify_local.py --file coordination/connection-check.md
```

已有仓库副本时，直接进入现有副本，核对分支和未提交改动后更新，不要覆盖原目录。`$PWD` 使用当前仓库的实际绝对路径，不需要猜测 DGX 的目录结构。

本地检查应返回 `local_mcp: verified`，`project_root` 应指向这个仓库。它同时读取连接检查文件并返回 SHA256。该结果证明本地 MCP 可用，网页连接仍需下面的步骤。

也可以在此仓库中打开本机 Codex，交给它这句话：

> 请读取 AGENTS.md 和 project-files-mcp/INSTALL_WITH_CODEX.md，完成这套系统在本机的部署。仓库已确定为 grij499-sudo/something，先用当前仓库根目录作为 MCP 项目目录。继续执行已授权的安装和验证；只有缺少真实 Tunnel ID、账号权限或本机凭据时，才说明具体需要我完成的操作。

## 连接 ChatGPT 网页

1. 在 [OpenAI Platform 的 Tunnels 设置](https://platform.openai.com/settings/organization/tunnels) 创建或选择 Tunnel，并核对组织、ChatGPT 工作区关联和使用权限。[S1]
2. 在仓库根目录运行以下命令，把占位符替换为真实 Tunnel ID。运行凭据在本机终端隐藏输入，不要放进聊天或 Git。

```bash
python3 project-files-mcp/connect_tunnel.py --tunnel-id "替换为真实的tunnel_id"
```

3. 初次连接保持终端运行。在 ChatGPT 网页的 `Plugins → ＋ → Add custom MCP server` 中选择 `Tunnel`，选择同一个 Tunnel，按界面完成配置并安装。[S2]
4. 在对话中选择这个插件，依次调用 `project_info`、`list_files`、`read_file`、`search_text`。读取 `coordination/connection-check.md`，确认标记为 `SOMETHING-GITHUB-MCP-20261102-V1`，再验证 `../` 路径被拒绝。

只有网页中的真实工具调用成功，才将网页连接标记为通过。前台连接按 Ctrl+C 会断开；长期运行的配置见 [完整部署说明](project-files-mcp/README.md)。

## ChatGPT 与 Codex 怎样协作

| 内容 | 放在哪里 | 使用方式 |
| --- | --- | --- |
| 任务目标与验收条件 | 从 `coordination/templates/TASK.template.md` 复制到任务文件 | ChatGPT 完成计划后写入；Codex 开工前读取 |
| 代码与文档 | 对应任务分支 | Codex 本地修改、验证并提交；ChatGPT 按明确分支或提交读取 |
| 执行结果 | 从 `RESULT.template.md` 复制 | 记录每项要求的实现位置和实际验证证据 |
| 独立审核 | 从 `REVIEW.template.md` 复制 | 读取原任务与实际代码，对必需项逐条核查 |
| 未提交的本机文件 | MCP 指定的项目目录 | 网页读取当前状态，核对 `project_info` 返回的实际路径 |

GitHub 和本机工作副本通过提交、推送和拉取同步。GitHub 中的内容与 MCP 读取的本机文件可能处在不同版本；对不上时先检查分支、提交号和本地改动。模板约定协作方法，自动创建会话或自动派工需要另行实现。

每个任务使用独立分支，保留既有改动，不强制推送覆盖远端。网页端写入后，本机 Codex 更新同一任务分支并检查差异；本机修改后提交并推送，网页再按该提交读取。当前 MCP 只提供读取工具，修改由 Codex 或具有相应权限的 GitHub 工具完成。

## 目录

- `project-files-mcp/`：服务、安装器、验证脚本与测试。
- `coordination/templates/`：任务、执行结果、独立审核和协作规则模板。
- `coordination/connection-check.md`：GitHub 与本机 MCP 共用的无敏感内容检查文件。
- `AGENTS.md`：在本仓库工作的约定。

本仓库为公开仓库。安装产生的 `.local/`、`.venv/` 及 `.env` 已列入忽略规则；真实凭据和其他项目数据应保留在相应的授权范围内。MCP 的文件排除规则不能识别所有正常命名文件中的秘密，完整范围与限制见服务说明。

## 官方资料

- [S1：Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [S2：Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server)

