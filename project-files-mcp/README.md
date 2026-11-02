# GitHub 项目共享 + 本地文件 MCP 部署包

版本 0.1.0｜2026-11-02

这个包实现“在 ChatGPT 网页读取指定 Linux 项目的本地文件”。GitHub 则提供同一项目的已提交版本与写入通路。两条连接分别验收。

**交付状态：服务与安装器已实现，目标仓库已确定为 `grij499-sudo/something`；30 项测试通过；云端工作区的 Linux x86_64 官方 tunnel-client 已下载并验证帮助命令。目标 DGX、本机 Git 往返、真实 Tunnel 与 ChatGPT 网页调用仍需实际安装后验证。**

## 1. 服务能做什么

| 工具 | 用途 |
| --- | --- |
| `project_info` | 确认真正连接的项目路径、服务实例与限制 |
| `list_files` | 列出目录与文件，支持分页 |
| `read_file` | 读取 UTF-8 文本，返回内容、哈希和下一页位置 |
| `search_text` | 按字面文本搜索，返回文件、行号和片段 |

该版本只读一个显式指定的项目目录，不提供文件写入、任意命令执行或 Codex 派工。代码修改通过本地 Codex 或具有相应权限的 GitHub 工具完成。

读取边界：拒绝目录穿越、符号链接、多硬链接和非普通文件；排除隐藏路径、常见凭据名称和私钥文件。单文件最多 1 MiB，每页最多 32,768 字符；列表每页最多 200 项；单次目录扫描最多 5,000 个条目；搜索最多 100 条结果、8 MiB 总读取量。扫描达到上限会明确返回不完整状态。

文件名策略不是通用秘密扫描器，正常命名文件中仍可能包含敏感信息。配置项目范围时应选择确实准备供 ChatGPT 读取的目录。这个服务也不提供操作系统级隔离。

## 2. 目标机器需要什么

- Linux、Python 3.11 或更高版本，并可创建 Python 虚拟环境。
- 要连接的项目绝对路径。
- 可访问 Python 包索引、GitHub 发布下载，以及 OpenAI 隧道服务的网络。
- 一个真实的 Secure MCP Tunnel ID 和具备所需权限的运行凭据。

Python 依赖固定为官方 `mcp==2.3.0`。当前 SDK 的服务类名称是 `MCPServer`。[S4]

安装器支持 Linux `x86_64` 和 `aarch64` 的官方资产匹配；本次实际执行验证使用 x86_64，DGX 的 ARM64 安装与运行仍需现场验证。

## 3. 在项目所在电脑上安装

克隆 `grij499-sudo/something` 后，可以按仓库根 README 的命令直接将整个仓库作为首次验证项目。若要连接其他明确指定的项目，进入本包 `project-files-mcp` 目录后执行：

```bash
python3 setup_local.py --project "/替换为真实的项目绝对路径"
python3 install_tunnel.py
.venv/bin/python verify_local.py --file README.md
```

最后一条的 `README.md` 是目标项目中的相对路径。如果项目没有该文件，可以换成一个已知的小型 UTF-8 文件，或省略 `--file README.md`。

`setup_local.py` 在本包内创建 `.venv/` 并写入 `.local/project.json`，不改业务代码。`install_tunnel.py` 从 OpenAI 官方 GitHub 的 latest release 元数据选择匹配架构的客户端，校验大小与 SHA256，安装到本包 `.local/bin/`，不做全局安装。[S5]

本地验收报告应显示 `local_mcp: verified`，并列出正确的项目路径。这个结果只证明本机 MCP 通路可用。

## 4. 配置 Secure MCP Tunnel

打开 [Platform 的 Tunnels 设置](https://platform.openai.com/settings/organization/tunnels)，创建或选择准备供此项目使用的 Tunnel。关联正确的 Platform 组织和 ChatGPT 工作区，取得它的 `tunnel_id`。

运行凭据使用获准的安全凭据设置入口或已有且获准的凭据。凭据留在本机；不要粘贴到聊天或提交 Git。Tunnel 的组织权限与 ChatGPT 自定义 MCP 权限分别生效，普通 API key 的存在本身不能证明隧道权限已配置。[S1]

在本包目录运行：

```bash
python3 connect_tunnel.py --tunnel-id "替换为真实的tunnel_id"
```

脚本会在本机终端以隐藏输入请求运行凭据，也支持已由安全方式设置的 `CONTROL_PLANE_API_KEY`。凭据只进入当前进程环境，不写入配置文件、不作为命令参数传递；启动 MCP 子进程时还会去掉相关 OpenAI 凭据环境变量。

脚本调用官方客户端的 `init → doctor → run`，配置写在本包 `.local/tunnels/<tunnel_id>/`。初次连接前台运行：**保持终端和电脑运行，Ctrl+C 会断开连接**。它不会自动创建新的 Tunnel、改变账号权限或开机自启。

网页首次成功调用后，若需要后台常驻，可由本机 Codex 按安装版本的 `tunnel-client runtimes connect --help` 配置官方管理的本地运行方式，并检查 `runtimes status`。不要把后台进程启动当作网页已经连通，也不要默认环境变量凭据能跨机器重启自动恢复。

## 5. 在 ChatGPT 网页加入插件

进入 `Plugins → ＋ → Add custom MCP server`，名称可用 `Project Files`，连接方式选择 `Tunnel`，选择同一个 Tunnel，完成网页要求的认证设置与创建步骤，然后安装插件。[S2]

此包的 MCP 子进程本身不提供额外 OAuth，访问依赖私有 Tunnel 的账号、组织与工作区权限。如果网页要求本服务没有提供的认证能力，停止并检查所选连接方式，不要把本服务直接改为无认证公网文件接口。

在新对话中通过 `@` 选择该插件，依次请求：

1. 调用 `project_info`，确认项目根目录。
2. 调用 `list_files`，查看某个明确目录。
3. 读取项目里一个已知文件，并核对其内容或哈希。
4. 搜索一个自己知道存在的短语。
5. 检查 `../` 路径被拒绝。

网页真实工具调用成功后，才可将“ChatGPT 到本机文件”标记为已连接。官方亦要求通过实际调用验证工具行为。[S2]

## 6. GitHub 这条连接怎样落地

本次使用已确定的仓库 [`grij499-sudo/something`](https://github.com/grij499-sudo/something)，ChatGPT 侧已有该仓库的 GitHub 连接。首次验证将本机克隆目录同时作为 Codex 工作区和 MCP 项目目录。

推荐步骤：

1. 克隆上述仓库，或进入已有本机副本；先核对当前 remote、分支、未提交修改。
2. 本地 Codex 使用这份工作副本；ChatGPT 使用连接器访问同一仓库。
3. 读取已有的 `coordination/connection-check.md`，核对其中的检查标记。
4. ChatGPT 按确切分支或提交读取同一文件；本机 Codex 拉取相同提交并核对内容。
5. 在独立任务分支中做必要的无敏感内容写入、推送及回读验证；不要用强制推送覆盖远端状态。

以后切换业务项目时，重新运行 `setup_local.py --project` 指向明确授权的绝对路径，再重启连接并重新核对 `project_info`。本 MCP 包本身不要求将该业务项目上传到本仓库。

GitHub 通路读取已经提交且可访问的版本；MCP 通路读取本机当前工作区。两边内容不同，先核对分支、提交和本地修改。

## 7. 文件与排障

| 文件 | 作用 |
| --- | --- |
| `project_files.py` | 受限文件访问核心 |
| `server.py` | 官方 MCP SDK 工具注册与 stdio 服务 |
| `setup_local.py` | 配置项目路径、安装依赖 |
| `run_mcp.py` | 启动器，隔离不必要的凭据环境变量 |
| `install_tunnel.py` | 下载并验证官方 Linux 客户端 |
| `connect_tunnel.py` | 使用已有 Tunnel，前台启动 |
| `verify_local.py` | 验证实际本地协议调用，不打印文件内容 |
| `tests/` | 文件边界、协议、安装器和启动器检查 |

常见问题：

- **网页看不到 Tunnel：**核对工作区关联与 Tunnel Use 权限。
- **本机验证成功但网页失败：**检查前台客户端是否仍运行、网络是否可达、网页选的是不是同一个 Tunnel。
- **读不到某些文件：**先核对相对路径、UTF-8、大小限制、隐藏路径和凭据排除策略。
- **看到旧内容：**GitHub 核对 ref；MCP 调用 `project_info` 核对本机路径和服务实例。
- **Python 缺 venv 模块：**在本机使用对应发行版的软件包管理器安装 Python venv 支持后重试，不要把依赖装进系统 Python。

测试命令：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

本次测试 30 项通过，包含实际 stdio 连接；所用测试项目均为临时夹具。当前执行环境对线程与子进程管道有限制，协议测试在批准的正常本地执行环境中完成，未绕过目标服务的文件访问限制。

## 官方依据

- [S1：Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [S2：Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [S3：Add custom MCP server](https://developers.openai.com/api/docs/guides/custom-mcp-server)
- [S4：官方 Python MCP SDK](https://py.sdk.modelcontextprotocol.io/)
- [S5：OpenAI tunnel-client 官方发布](https://github.com/openai/tunnel-client/releases/latest)
