# 更新日志

所有值得注意的变更都会记录在这里。

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [未发布]

### 新增（Private，可选，默认关闭）

- `server.py --transport http`：Streamable HTTP 自托管模式（路径 `/mcp`，无状态 JSON 响应，服务重启不影响客户端）
- 静态访问令牌认证（单用户多设备）：`auth_tokens.py create / list / revoke`
  - 认证不可关闭，没有有效令牌时拒绝启动
  - 令牌文件只存 SHA-256 哈希，以 0600 权限原子写入；令牌只在创建时显示一次
  - 常数时间比对；吊销立即生效，无需重启
- 默认只监听 127.0.0.1；监听其他地址需显式开启 `allow_remote_bind`（程序不处理 HTTPS，必须放在反向代理后）
- Host / Origin 校验，防 DNS 重绑定；`/healthz` 健康检查不需要令牌、不泄露信息
- `backup.py`：备份卡片，恢复时永不覆盖已有卡片；拒绝含子目录、符号链接、路径穿越、非 `.md` 或超大条目的备份包
- `deploy/`：Dockerfile（非 root 用户）、Docker Compose + Caddy 自动 HTTPS 模板；服务端口不映射到宿主机
- 健康检查增加访问令牌状态
- 教程《Private：自托管部署》及对应排错条目
- Private 测试 `tests/test_private.py`

### 新增（Pro，全部可选，默认关闭）

- Git 同步：`sync.enabled` 开启后，`kb_save` / `kb_update` 成功时自动在卡片仓库做本地提交（只提交本次卡片，不联网）
- 新工具 `kb_sync`：fetch → merge → push；`action="status"` 查看本地状态
  - 冲突时取消合并并列出冲突文件，本地卡片不被覆盖
  - 推送失败时保留本地提交，可再次同步重试；永不 force push
  - 卡片目录必须是拥有自己 `.git` 目录的独立仓库根目录；上级仓库的子目录、linked worktree、子模块都会被拒绝，不会把卡片提交进其他仓库
  - 联网时强制 SSH 非交互（即使用户设置了 `BatchMode=no`，仍保留其密钥与代理参数），并脱离控制终端，不会卡住等待密码
  - 返回内容、错误信息与健康检查输出中，remote 地址的用户信息、查询参数和片段都会被隐藏；配置校验错误不回显原值
- 静态站点生成器 `build_site.py`：只发布 tags 带 `public`（可配置）的卡片；卡片中的原始 HTML 会被转义；拒绝覆盖非站点目录
- GitHub Pages 发布模板 `kb-mcp/templates/github-pages.yml`（默认仅手动触发）
- `requirements-pro.txt`（站点生成所需的 markdown-it-py）
- 健康检查增加 Git 同步检查
- 教程《Pro：同步与展示》及对应排错条目
- Pro 测试 `tests/test_pro.py`

### 变更

- 配置加载与卡片解析抽到 `kbcore.py`，由 server 与站点生成器共用（站点生成器不依赖 mcp）

### 修复

- Lite 快速上手中的仓库克隆地址

## [0.1.0] - 2026-08-17

### 新增

- Core Schema v0.1 定稿（四槽位：KNOW / UNDERSTAND / CONNECT / VERIFY）
- 三个内置 Profile：`general`（通用）、`ai-tech`（AI/技术）、`language`（语言学习）
- kb-mcp 服务端，五个工具：kb_save / kb_get / kb_update / kb_search / kb_guide
- 两张示例卡片：Embedding（ai-tech）、apple（language）
- Lite 快速上手、卡片规范与常见问题文档
- AGPL v3 许可证

### 说明

这是随手学 Open 的首个公开版本。Core Schema 经过三轮评审和压力测试（AI 技术 / 英语 / 数学），验证了四槽位架构能够容纳不同学科的知识。
