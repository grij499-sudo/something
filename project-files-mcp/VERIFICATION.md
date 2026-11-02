# 验证记录

日期：2026-11-02。环境：当前云端工作区，Linux x86_64，Python 3.12.14。

## 已验证

- 目标 GitHub 仓库已由用户指定为 `grij499-sudo/something`。通过 ChatGPT 的 GitHub 连接器创建初始 README 提交 [`6b6090346aa42266f24272b9ee45c5f8a52fc486`](https://github.com/grij499-sudo/something/commit/6b6090346aa42266f24272b9ee45c5f8a52fc486)，再按该确切提交读取 README，内容逐字一致。这证明当前连接器具有本仓库的写入与读取能力；用户机器上的拉取与推送仍单独验收。
- 官方 Python MCP SDK：安装并使用 `mcp==2.3.0`。
- 完整测试命令：`.venv/bin/python -m unittest discover -s tests -v`。
- 结果：30 项通过，约 2.3 秒。包括 13 项文件访问核心检查、2 项 SDK/stdio 协议检查、12 项客户端下载与安装检查、3 项部署启动器检查。
- 真实 stdio 子进程：auto 与 legacy 两种客户端连接均通过；发现四个工具，读取临时项目文件、搜索文本、拒绝排除路径及非法参数。
- 安装与启动器额外演练：在带空格路径的临时项目上运行 `setup_local.py`，再经 `run_mcp.py` 启动服务，`verify_local.py --file README.md` 返回 `local_mcp: verified`，核对目录与文件哈希成功。
- 官方 tunnel-client：实际下载 `v0.0.19` 的 Linux amd64 ZIP，API SHA256 核对成功；`--help`、`help quickstart`、`init --help`、`runtimes connect --help` 和 `runtimes status --help` 均成功执行。
- 下载包 SHA256：`9ee9448592345a9dd1517fb79791ab54d24f051142eb92bcbe8cd355effc9142`。

测试使用临时文件，没有读取用户 DGX 上的项目或任何账户密钥。协议测试依赖正常线程与子进程管道，在批准的本地执行环境中运行。

## 尚未验证

- DGX 上 tunnel-client 的实际联网运行；安装输出不等于已连接。
- 真实 Tunnel 的权限、工作区关联和网络连接。
- ChatGPT 网页发现并调用这个 MCP 服务。
- 用户机器上的 GitHub 任务分支推送、拉取与文件内容往返核对。

需要目标机器和对应账号配置才能完成这些检查，不能用上述工作区测试替代。

## 用户回传的目标机器证据

2026-11-02，用户回传了本机安装器与验证器输出：

- `local_mcp: verified`，项目根目录指向 `something` 的本机工作副本。
- 工具列表包含 `project_info`、`list_files`、`read_file`、`search_text`；`path_restrictions: verified`。
- 读取 `coordination/connection-check.md` 得到 SHA256：`5c2b40efbd932f8eb5dee1301817d757b7df4c05a071c776837d2c425e5b9393`。与发布文件重新计算的值一致。
- 输出中 Tunnel 状态仍为 `must still be verified from ChatGPT`。

以上为用户回传的终端证据，未由本会话直接登录目标机器复跑。用户随后选择只使用现有订阅，暂停 Tunnel，先完成 GitHub 协作往返；这项决定不影响已经通过的本地验证。
