# GitHub / 本机 MCP 连接检查

- 仓库：`grij499-sudo/something`
- 检查标记：`SOMETHING-GITHUB-MCP-20261102-V1`
- 内容版本：1

此文件只包含公开的连接检查内容，不包含账号凭据或业务数据。

检查步骤：先通过 GitHub 读取此文件，再在本机拉取相同提交，通过 MCP 的 `read_file` 读取 `coordination/connection-check.md`。核对标记、完整内容和 SHA256；记录双方使用的提交或本地状态。

搜索验收短语：`共享项目连接验证成功`。

路径越界检查使用 `../outside.txt`，应返回拒绝读取的错误。网页真实调用成功后，在执行报告中记录证据，不要把本文件的存在当作已经连通的证明。

