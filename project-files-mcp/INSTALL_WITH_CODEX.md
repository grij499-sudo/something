# 交给项目所在电脑上的 Codex

请帮我完成 GitHub 项目共享与本包的本地文件 MCP 接入。

1. 读取根目录与本包 README。仓库已确定为 `https://github.com/grij499-sudo/something`；首次部署默认以这个仓库的实际本地根目录作为 MCP 项目目录，无需重新询问仓库或猜测固定路径。若用户明确指定另一个项目目录，使用该目录。
2. 保留现有 Git 工作区与未提交改动。核对仓库 remote，报告时不要输出 URL 中可能存在的凭据。
3. 在本包目录执行 setup_local.py、install_tunnel.py 和 verify_local.py，并检查真实结果。默认使用仓库中的 `coordination/connection-check.md` 验证读取；配置后必须核对 project_info 的实际项目根目录。
4. 使用我在 Platform 中选择或创建的真实 Tunnel，核对目标组织与 ChatGPT 工作区关联。没有真实 Tunnel ID 时，先完成本地安装验证，再说明需要的 ID 和账号操作。我会通过本机隐藏输入提供运行凭据，不要把密钥写进聊天、命令参数、日志或代码库。
5. 执行 connect_tunnel.py。首次通过后，如需长期运行，使用官方 `tunnel-client runtimes connect` 管理方式并核对状态，不使用 nohup/disown 冒充可管理的部署。
6. 网页加入 Project Files 自定义 MCP 插件后，实际调用 project_info、list_files、read_file、search_text，确认目录与内容，并验证越界路径被拒绝。
7. 先核对 `coordination/connection-check.md` 的检查标记 `SOMETHING-GITHUB-MCP-20261102-V1`，再在 `grij499-sudo/something` 的独立任务分支里做必要的无敏感内容写入/读取往返检查，核对确切提交；不强制推送、不覆盖其他工作。
8. 最终分别报告：GitHub 往返、MCP 本机、Tunnel 运行、ChatGPT 网页调用，各自是通过、失败还是尚未验证。不能把“已生成配置文件”写成全部部署成功。

现有用户授权涵盖这次部署所需的可逆配置和验证。有缺失信息或账号权限时，说明具体缺项；不要改变全局审批策略，也不要上传未指定的业务数据。
