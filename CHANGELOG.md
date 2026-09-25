# 更新日志

所有值得注意的变更都会记录在这里。

格式基于 [Keep a Changelog](https://keepachangelog.com/)。

---

## [未发布]

### 新增（Pro，全部可选，默认关闭）

- Git 同步：`sync.enabled` 开启后，`kb_save` / `kb_update` 成功时自动在卡片仓库做本地提交（只提交本次卡片，不联网）
- 新工具 `kb_sync`：fetch → merge → push；`action="status"` 查看本地状态
  - 冲突时取消合并并列出冲突文件，本地卡片不被覆盖
  - 推送失败时保留本地提交，可再次同步重试；永不 force push
  - 卡片目录必须是独立的 Git 仓库根目录，不会把卡片提交进上级仓库
  - Git 在非交互模式运行，不会卡住等待密码；返回内容中的 remote 凭据会被隐藏
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
