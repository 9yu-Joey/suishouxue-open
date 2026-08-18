# 随手学 Open (SuiShouXue Open)

> **AI 原生的学习记忆框架** — 让 AI 帮你把学到的东西，变成真正属于你的知识。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Schema Version](https://img.shields.io/badge/Core_Schema-v0.1-green.svg)](core/SCHEMA.md)

---

## 这是什么？

随手学是一个 **帮助你把 AI 对话转化为个人知识资产的 AI 学习记忆框架**。

你或许会遇到类似场景：

每天向 AI 提问，学会了很多新概念。

今天理解了 Embedding，明天弄懂了 RAG，后天研究 Fine-tuning……

但聊天结束后，这些理解散落在不同对话中，难以整理、回看，也很难形成自己的知识体系。

随手学解决的就是这个问题：

它帮助 AI 将你的学习过程结构化，把一次次对话中的理解沉淀为可以保存、检索、复习和持续更新的知识卡片。

它不是笔记软件，不是 Wiki，也不是传统闪卡工具。

它是一套让 AI 理解“知识应该如何被学习和沉淀”的框架：

Core Schema：定义通用的学习结构；

Profile：根据不同学科决定具体学习方式；

MCP 服务端：让 AI 能够按照规则自动创建和维护知识卡片。

每张知识卡片都围绕四个核心问题：

知 KNOW：它是什么？

解 UNDERSTAND：如何理解它？

联 CONNECT：它和什么有关？

验 VERIFY：如何证明自己掌握？

学习不再是一次性消费。

每一次与 AI 的交流，都可以沉淀为属于你的知识资产。

当然，随手学不局限于 AI 或技术领域。

无论是语言、数学、历史，还是任何你想长期学习的领域，都可以通过不同 Profile 建立适合自己的学习方式。

---

## 核心架构

```
┌─────────────────────────────────────────────────┐
│                Core Schema v0.1                  │
│  ┌──────┐ ┌──────────┐ ┌────────┐ ┌──────┐     │
│  │ KNOW │ │UNDERSTAND│ │CONNECT │ │VERIFY│     │
│  │  知  │ │    解    │ │   联   │ │  验  │     │
│  └──────┘ └──────────┘ └────────┘ └──────┘     │
│  是什么？  怎么理解？   和什么有关？ 怎么证明会了？ │
└─────────────────────────────────────────────────┘
                      ▲
                      │ 四个槽位，任何学科通用
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
┌─────────┐    ┌───────────┐    ┌──────────┐
│ general │    │  ai-tech  │    │ language │
│ 通用学习 │    │ AI与技术   │    │ 语言学习  │
└─────────┘    └───────────┘    └──────────┘
  Profile：定义每个槽位里具体放什么字段
```

**Core Schema** 是骨架——它定义了学习过程的四个维度，适用于任何学科。

**Profile** 是肌肉——每个学科用自己的 Profile 决定四个维度里具体怎么写。学 AI 技术，遇到专业名词需要记"英文全称、发音、谐音"，学语言需要记"音标、例句、词族"——这些差异全由 Profile 吸收，Core 保持稳定。

详见 [Core Schema 完整定义](core/SCHEMA.md) · [Profile 接口规范](profiles/README.md)

---

## 当前版本：Lite

Lite 使用 MCP 服务端和本地 Markdown 文件，不依赖在线服务，五分钟即可开始。

---

## 快速开始（Lite）

### 1. 克隆仓库

```bash
git clone https://github.com/9yu-Joey/suishouxue-open.git
cd suishouxue-open
```

### 2. 安装依赖

```bash
cd kb-mcp
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

### 3. 配置 AI 客户端

以 Claude Desktop 为例，在 `claude_desktop_config.json` 中添加：

**macOS / Linux：**

```json
{
  "mcpServers": {
    "suishouxue": {
      "command": "python3",
      "args": ["/Users/你的用户名/suishouxue-open/kb-mcp/server.py"]
    }
  }
}
```

**Windows：**

```json
{
  "mcpServers": {
    "suishouxue": {
      "command": "python",
      "args": ["C:\\Users\\你的用户名\\suishouxue-open\\kb-mcp\\server.py"]
    }
  }
}
```

> 把路径替换为你实际克隆仓库的位置。环境变量 `SUISHOUXUE_CARDS_DIR` 可选设置卡片存储目录。

### 4. 开始学习

在和 AI 的对话中提到一个新概念，AI 会自动按当前 Profile 的规则生成一张知识卡片，通过 `kb_save` 保存到你的本地文件夹。

试试问 AI：*"Embedding 是什么？帮我存到知识库。"*

---

## 仓库结构

```
suishouxue-open/
├── README.md                ← 你在这里
├── LICENSE                  ← AGPL v3
├── CONTRIBUTING.md          ← 贡献指南
├── CHANGELOG.md             ← 版本记录
│
├── core/
│   └── SCHEMA.md            ← Core Schema v0.1 定义
│
├── profiles/
│   ├── README.md            ← Profile 接口规范
│   ├── general.yaml         ← 通用学习
│   ├── ai-tech.yaml         ← AI/技术学习
│   └── language.yaml        ← 语言学习
│
├── examples/
│   ├── embedding.md         ← ai-tech 示例卡片
│   └── apple.md             ← language 示例卡片
│
├── docs/
│   ├── 01-随手学是什么.md
│   ├── 02-Lite-快速上手.md
│   ├── 03-卡片规范详解.md
│   └── 04-常见问题与排错.md
│
├── kb-mcp/
│   ├── server.py            ← MCP 服务端
│   ├── healthcheck.py       ← 健康检查
│   ├── config.example.yaml  ← 配置示例
│   ├── .env.example         ← 环境变量示例
│   ├── requirements.txt     ← Python 依赖
│   └── README.md            ← MCP 文档
│
└── tests/
    └── test_basic_save.py   ← 基础测试
```

---

## 教程文档

| 文档 | 内容 |
|------|------|
| [随手学是什么](docs/01-随手学是什么.md) | 项目理念、设计哲学 |
| [Lite 快速上手](docs/02-Lite-快速上手.md) | 五分钟从零开始 |
| [卡片规范详解](docs/03-卡片规范详解.md) | Core Schema + Profile 完整解读 |
| [常见问题与排错](docs/04-常见问题与排错.md) | FAQ 和 troubleshooting |

---

## 创建你自己的 Profile

随手学的 Profile 系统是可扩展的。如果你在学音乐、学历史、学烹饪——你可以创建自己的 Profile，定义你的学科需要在四个槽位里记录什么内容。

详见 [Profile 接口规范](profiles/README.md) 和 [贡献指南](CONTRIBUTING.md)。

---

## 贡献

欢迎提交新的 Profile、修复 bug、改进文档。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 许可证

本项目基于 [GNU Affero General Public License v3.0](LICENSE) 开源。

简单来说：你可以自由使用、修改、分发这个项目，但如果你修改了代码并以网络服务的形式提供给他人使用，你必须公开你的修改版本的源代码。这确保了社区的改进能回馈给所有人。

---

## 作者

**九聿** — 从 AI 训练师到 AI 建造者的路上，用随手学记录每一步。

---

*学习不是一次性消费，是可以积累的资产。*
