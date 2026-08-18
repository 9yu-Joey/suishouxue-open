# kb-mcp — 随手学知识卡片 MCP Server

kb-mcp 是「随手学」项目的核心组件：一个基于 [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) 的知识卡片服务器。它让 AI 客户端（如 Claude Desktop、ChatGPT Desktop、Cursor）能够保存、搜索和管理结构化的知识卡片，将日常学习碎片转化为可检索的个人知识库。

基于官方 MCP Python SDK (FastMCP) 实现，要求 Python 3.10+。

## 快速开始

### 1. 安装依赖

```bash
cd kb-mcp
pip install -r requirements.txt
```

### 2. 创建配置文件

```bash
cp config.example.yaml config.yaml
```

根据需要编辑 `config.yaml`，默认配置即可直接使用。也可通过环境变量 `SUISHOUXUE_CARDS_DIR`、`SUISHOUXUE_PROFILES_DIR`、`SUISHOUXUE_DEFAULT_PROFILE` 覆盖配置。

### 3. 健康检查

```bash
python healthcheck.py
```

确认所有检查项通过后即可启动服务。

### 4. 启动 MCP Server

```bash
python server.py
```

服务器以 stdio 模式运行，通过标准输入/输出与 AI 客户端通信。

## 核心工具

| 工具 | 说明 |
|------|------|
| **kb_save** | 创建新知识卡片（含完整 Metadata），验证 Profile 和 category |
| **kb_get** | 按 id 读取完整卡片内容和元信息 |
| **kb_update** | 按 id 更新卡片内容或元信息，保留 created、刷新 updated |
| **kb_search** | 按关键词搜索卡片，返回 id/title/profile 和命中附近的摘要 |
| **kb_guide** | 加载 Profile YAML，返回字段定义，引导 AI 按模板生成卡片 |

## 连接 AI 客户端

### Claude Desktop

在 Claude Desktop 的 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "suishouxue-kb": {
      "command": "python3",
      "args": ["/你的路径/suishouxue-open/kb-mcp/server.py"]
    }
  }
}
```

### ChatGPT Desktop / Codex CLI

ChatGPT 桌面端和 Codex CLI 均支持 MCP stdio 传输，配置方式类似。

### 其他支持 MCP 的客户端

任何支持 MCP stdio 传输的客户端均可连接，将 `command` 指向 `python3`，`args` 指向 `server.py` 的绝对路径即可。

## 版本说明

v0.1 提供本地 Markdown 存储与 MCP stdio 服务。

## 许可证

AGPL-3.0-or-later — 详见 [LICENSE](../LICENSE)。
