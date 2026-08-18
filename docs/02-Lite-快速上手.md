# Lite 快速上手

> 五分钟，让 AI 帮你存下第一张知识卡片。

## 你需要什么

- Python 3.10+
- 一个支持 MCP 的 AI 客户端（如 Claude Desktop、ChatGPT Desktop、Cursor 等）
- 就这些。不需要服务器，不需要数据库，不需要付费账号

## 第一步：获取代码

```bash
git clone https://github.com/jiuyu-shenshi/suishouxue-open.git
cd suishouxue-open/kb-mcp
```

## 第二步：安装依赖 + 配置

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

打开 `config.yaml`，确认 `cards_dir` 指向你想存放知识卡片的目录（默认是 `./cards`，会自动创建）。

## 第三步：连接 AI 客户端

以 Claude Desktop 为例，打开配置文件 `claude_desktop_config.json`，添加：

```json
{
  "mcpServers": {
    "suishouxue": {
      "command": "python",
      "args": ["/你的路径/suishouxue-open/kb-mcp/server.py"]
    }
  }
}
```

重启 Claude Desktop，你应该能在工具列表中看到五个新工具：`kb_save`、`kb_get`、`kb_update`、`kb_search`、`kb_guide`。

## 第四步：存你的第一张卡片

在对话中问 AI 一个概念，然后说"帮我存到知识库"。例如：

> "Embedding 是什么？帮我存到知识库。"

AI 会按当前 Profile 的规则生成一张结构化的知识卡片，通过 `kb_save` 保存为一个 Markdown 文件。

去你的 `cards/` 目录看看——你的第一张卡片就在那里。

## 第五步：搜索和追加

以后想找回某张卡片：

> "帮我搜一下知识库里关于向量的内容"

想给一张卡片追加理解：

> "我对 Embedding 有了新的理解：[你的新理解]，帮我更新到知识库"

## 健康检查

不确定配置对不对？运行健康检查：

```bash
python healthcheck.py
```

它会告诉你配置文件、卡片目录、Profile 文件的状态。

## 接下来

- 想了解卡片的完整结构？→ [卡片规范详解](03-卡片规范详解.md)
- 遇到问题？→ [常见问题与排错](04-常见问题与排错.md)
