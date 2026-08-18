# 随手学 Open — Core Schema v0.1 final

> **文档性质**：架构定稿（评审通过）
> **版本**：v0.1 final
> **Schema 版本号**：`0.1`
> **日期**：2026-08-17
> **作者**：柯言（Cowork 侧）
> **评审人**：九聿、顾知行（GPT 侧）
> **评审结论**：原则通过，已按评审意见修订

---

## 一、Core Schema 是什么

Core Schema 是随手学 Open 所有知识卡片的**最底层骨架**。

不管用户在学 AI、学英语、学数学还是学烹饪，每一张卡片都必须能被这个骨架容纳。它不规定具体写什么内容——那是 Profile 的事——它只规定**学习过程的结构**。

**设计原则**：

- Core 只管"学习长什么样"，不管"知识长什么样"
- Core 越小越好，刚好能撑住所有学科，一个字段都不多加
- 具体学科的差异全部交给 Profile 处理

---

## 二、四槽位定义

每张知识卡片由两部分组成：**元信息（Metadata）** 和 **四个学习能力槽位（Learning Slots）**。

### 2.1 元信息（Metadata）

元信息是卡片的"信封"，用于标识、分类、检索和版本追踪，不涉及学习内容本身。

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | 卡片唯一标识符（建议格式：`profile-slug`，如 `ai-tech-embedding`、`lang-apple`，由系统自动生成，保证全库不重复） |
| `title` | ✅ | 知识点名称（人类可读标题） |
| `profile` | ✅ | 使用的学习模板（如 `ai-tech`、`language`、`general`） |
| `schema_version` | ✅ | 生成此卡片时的 Core Schema 版本号（如 `0.1`），用于未来 Schema 升级时的兼容判断 |
| `profile_version` | ✅ | 生成此卡片时的 Profile 版本号（如 `0.1`），用于 Profile 更新时识别旧卡片 |
| `category` | ⚙️ | 所属大类——**是否必填由 Profile 决定**（有些学科分类很重要，有些场景下用户只是随手记一个概念，不需要先想分类） |
| `tags` | ❌ | 自由标签，用于搜索 |
| `created` | ✅ | 创建时间（自动生成） |
| `updated` | ✅ | 最后更新时间（自动生成） |
| `source` | ❌ | 知识来源（对话、课程、书籍等） |

### 2.2 四个学习能力槽位

| 槽位 | 英文 | 核心问题 | Core 层定义 |
|---|---|---|---|
| **知** | KNOW | 这个知识是什么？ | 保存知识本体：定义、名称、核心事实 |
| **解** | UNDERSTAND | 我如何理解它？ | 保存个人化的理解方式：类比、自己的话、例子、直觉 |
| **联** | CONNECT | 它和什么有关？ | 保存知识间的关系：前置、关联、上下位、应用场景 |
| **验** | VERIFY | 我怎么证明自己会了？ | 保存学习验证手段：自测、例题、应用、复述 |

**Core 层只定义这四个槽位的"含义"——每个槽位里具体放哪些字段、每个字段怎么写，由 Profile 决定。**

**槽位允许存在但不硬凑**：四个槽位是卡片的结构骨架，每张卡片都应该保留这四个区域。但如果某个知识点在某个槽位下确实没有有意义的内容（比如一个极简概念暂时想不到关联知识），允许该槽位只写一句"暂无"或留空，不要为了填满而硬凑内容。**宁可诚实地留白，不要制造噪音。** 随着学习深入，用户或 AI 可以后续追加更新。

用比喻来说：Core Schema 是一个书架，固定了四层隔板（知、解、联、验）。Profile 决定每层隔板上放什么形状的书。某一层暂时没有书也没关系，隔板在那里，以后随时可以放。

---

## 三、Profile 最小接口规范

一个 Profile 是一个 YAML 文件，描述某个学科/学习场景下，四个槽位各包含哪些具体字段。

### 3.1 Profile 必须包含的信息

```yaml
# Profile 元信息
name: "ai-tech"                    # Profile 唯一标识（英文，用于系统引用）
display_name: "AI 与技术学习"        # 人类可读名称
description: "适用于学习 AI、编程、互联网技术等概念"
version: "0.1"                     # Profile 自身版本号，更新时递增
min_schema_version: "0.1"          # 依赖的最低 Core Schema 版本

# 分类体系（该 Profile 下可用的 category 值）
category_required: true              # 该 Profile 下 category 是否必填（Core 不强制，由 Profile 决定）
categories:
  - "计算机与互联网"
  - "AI与数据科学"
  - "工具与平台"

# 四槽位字段定义
slots:
  know:
    label: "知识本体"
    fields:
      - name: "definition"
        label: "定义"
        required: true
        hint: "用一两句话说清楚这个概念是什么"
      - name: "english_full"
        label: "英文全称"
        required: true
        hint: "缩写展开，如 API = Application Programming Interface"
      # ... 更多字段

  understand:
    label: "理解方式"
    fields:
      - name: "analogy"
        label: "类比"
        required: true
        hint: "用生活中的东西打个比方"
      # ... 更多字段

  connect:
    label: "知识关联"
    fields:
      - name: "related_concepts"
        label: "关联概念"
        required: true
      # ... 更多字段

  verify:
    label: "学习验证"
    fields:
      - name: "self_test"
        label: "自测问题"
        required: true
      # ... 更多字段

# AI 生成指令（可选）：当 AI 为这个 Profile 生成卡片时的额外规则
ai_instructions: |
  - 英文术语首次出现时必须补全：全称、发音、中文谐音、字面直译
  - 类比优先使用生活场景，避免用另一个技术概念解释技术概念
  - 自测问题应包含至少一个判断场景题
```

### 3.2 Profile 接口规则

1. **每个 Profile 必须为四个槽位都定义至少一个字段**——保证卡片结构完整。但槽位允许留白（见 §2.2 说明），Profile 定义的是"这个槽位可以装什么"，不是"每个槽位必须装满"
2. **`name` 字段是 Profile 的唯一标识**，对应卡片 Metadata 中的 `profile` 值
3. **`version` 是 Profile 自身的版本号**，每次更新字段定义时递增；生成卡片时自动写入 Metadata 的 `profile_version`，用于后续识别"这张卡片是用哪个版本的 Profile 生成的"
4. **`min_schema_version` 声明依赖的最低 Core Schema 版本**——未来 Schema 升级时，旧 Profile 如果低于新 Schema 版本，系统可以提示需要更新
5. **`category_required` 由 Profile 自行决定**——Core 不强制 category 必填。有的学科分类很重要（如 AI 技术），有的场景用户只想随手存一个概念不想先想分类
6. **`ai_instructions` 是给 AI 的生成指令**——这是 Profile 层的"教学法"，告诉 AI 在这个学科下应该怎么写卡片
7. **Profile 就是 Single Source of Truth**——不再另设 templates/ 目录，避免两份结构定义打架

### 3.3 卡片由 Profile 生成

AI 在生成卡片时的工作流程：

```
用户问了一个概念
       ↓
AI 读取当前活跃的 Profile
       ↓
按 Profile 中四个槽位的字段定义生成内容
       ↓
填入 Metadata（title, profile, category, created...）
       ↓
输出为 Markdown 文件（frontmatter + 正文）
```

**生成出来的卡片是 Markdown，不是 YAML。** Profile 是给 AI 和系统读的"图纸"，卡片是给人类读的"成品"。

---

## 四、压力测试

用三个完全不同类型的知识，验证同一个 Core Schema 是否能容纳。

### 测试 1：Embedding（AI 技术概念）

**使用 Profile**：`ai-tech`

```markdown
---
id: ai-tech-embedding
title: Embedding
profile: ai-tech
schema_version: "0.1"
profile_version: "0.1"
category: AI与数据科学
tags: [向量, 表示学习, NLP, 搜索]
created: 2026-08-17
updated: 2026-08-17
---

## KNOW · 知识本体

**英文全称**：Embedding（无缩写）
**中文**：嵌入 / 向量表示
**发音**：/ɪmˈbɛdɪŋ/（音近"因-掰-丁"）
**字面直译**：嵌进去——把一个东西嵌进另一个空间里
**为什么叫这个名字**：把离散的符号（文字、图片）"嵌入"到一个连续的数学空间中，让它们有了位置和距离
**定义**：一种将离散数据（文字、图片等）转换为连续向量的技术，使得语义相近的内容在向量空间中距离也近

## UNDERSTAND · 理解方式

**类比**：像给每个词发一张地图坐标卡——"猫"和"狗"会被分到附近的坐标，"猫"和"经济学"就离得很远。电脑不认识字，但认识坐标，有了坐标就能算"谁跟谁更像"
**为什么会出现**：传统搜索只能精确匹配关键词（搜"苹果"找不到"水果"），Embedding 让计算机理解"苹果和水果意思接近"，搜索和推荐才变得智能
**项目实例**：随手学的知识库未来可以用 Embedding 增强搜索——目前 Lite 版用的是关键词匹配，升级后你搜"向量"，它就能找到标题里没有"向量"但内容相关的卡片

## CONNECT · 知识关联

**前置知识**：向量（Vector）、相似度（Similarity）
**关联概念**：RAG（检索增强生成）、语义搜索、Word2Vec、BERT
**应用场景**：搜索引擎、推荐系统、聊天机器人的知识检索、图像相似度比较

## VERIFY · 学习验证

**自测**：用自己的话向一个不懂技术的朋友解释"为什么搜索引擎能理解你的意思而不只是匹配关键词"
**判断场景**：如果你要给一个菜谱 App 加"找类似菜品"功能，你会用关键词匹配还是 Embedding？为什么？
**经典例子**：为什么 king - man + woman ≈ queen？这个等式说明了 Embedding 的什么特性？
```

**测试结论**：✅ 四个槽位自然填满，没有硬掰。ai-tech Profile 的特色字段（英文全称、发音、谐音、项目实例）自然落入 KNOW 和 UNDERSTAND。

---

### 测试 2：apple（英语单词）

**使用 Profile**：`language`

```markdown
---
id: lang-apple
title: apple
profile: language
schema_version: "0.1"
profile_version: "0.1"
category: 基础词汇
tags: [名词, 食物, 日常用语, A1]
created: 2026-08-17
updated: 2026-08-17
---

## KNOW · 知识本体

**单词**：apple
**音标**：/ˈæp.əl/
**词性**：noun（可数名词）
**词义**：苹果；一种圆形水果，果肉白色、脆甜，果皮有绿、红、黄色

## UNDERSTAND · 理解方式

**例句**：
- An apple a day keeps the doctor away.（一天一苹果，医生远离我——谚语）
- She reached for the apple on the top shelf.
**语境与用法**：日常食物词汇；也有大量引申用法——Apple Inc.（苹果公司）、apple of my eye（掌上明珠）、bad apple（害群之马）
**常见搭配**：apple pie, apple juice, apple tree, apple cider, apple sauce

## CONNECT · 知识关联

**同类词**：fruit, pear, orange, banana, grape（水果类）
**易混词**：无明显易混词
**词族**：applesauce（苹果酱）、apple-cheeked（红润的）

## VERIFY · 学习验证

**造句**：用 apple 的一个引申义（如 bad apple 或 apple of my eye）造一个句子
**听辨**：在一段自然语速的对话中能否听出 apple
**拼写**：双 p，直接拼读，无陷阱
```

**测试结论**：✅ 四个槽位自然适配语言学习。KNOW 装词义词性，UNDERSTAND 装例句语境，CONNECT 装同类词和词族，VERIFY 装造句听写。没有任何字段是硬塞的。注意 language Profile 里完全没有"发音谐音""项目实例"这些 ai-tech 的字段——这正是 Profile 分离的价值。

---

### 测试 3：导数（数学概念）

**使用 Profile**：`mathematics`

```markdown
---
id: math-derivative
title: 导数
profile: mathematics
schema_version: "0.1"
profile_version: "0.1"
category: 微积分
tags: [极限, 变化率, 切线, 高等数学]
created: 2026-08-17
updated: 2026-08-17
---

## KNOW · 知识本体

**术语**：导数（Derivative）
**定义**：函数在某一点处的瞬时变化率；几何上是函数曲线在该点处切线的斜率
**核心公式**：f'(x) = lim(h→0) [f(x+h) - f(x)] / h
**符号说明**：f'(x)、dy/dx、df/dx 均表示导数，写法不同含义相同

## UNDERSTAND · 理解方式

**图像直觉**：想象你站在一座山坡上——导数就是你脚下这一点的"陡峭程度"。正数=上坡，负数=下坡，零=山顶或谷底的平地
**推导思路**：从"平均变化率"（两点连线的斜率）出发，让两个点无限靠近，极限值就是"瞬时变化率"（切线斜率）
**为什么重要**：导数是描述"变化"的数学语言——速度是位移的导数，加速度是速度的导数，经济学里边际成本是总成本的导数

## CONNECT · 知识关联

**前置知识**：极限（Limit）、函数（Function）、直线斜率
**关联概念**：积分（导数的逆运算）、链式法则（Chain Rule）、偏导数（多变量版本）
**向上延伸**：微分方程、泰勒展开、梯度下降（机器学习核心）

## VERIFY · 学习验证

**例题**：用定义求 f(x) = x³ + 2x 的导数（答案：3x² + 2）
**易错点**：复合函数忘记用链式法则；把导数和原函数搞混
**应用题**：一个球的位置是 s(t) = 4.9t²，求 t = 3 秒时的速度（答案：s'(3) = 29.4 m/s）
```

**测试结论**：✅ 四个槽位完美适配数学学习。KNOW 装定义和公式，UNDERSTAND 装直觉和推导，CONNECT 装前置和延伸，VERIFY 装例题和易错点。数学 Profile 里有"核心公式""符号说明""推导思路""例题"这些 ai-tech 和 language Profile 里根本不会出现的字段——Profile 分离让每个学科按自己的方式活着。

---

## 五、压力测试总结

| 维度 | Embedding (AI技术) | apple (英语) | 导数 (数学) | Core 能否统一容纳 |
|---|---|---|---|---|
| KNOW | 全称、发音、定义 | 音标、词性、词义 | 定义、公式、符号 | ✅ 都在回答"是什么" |
| UNDERSTAND | 类比、项目实例 | 例句、语境、搭配 | 图像直觉、推导 | ✅ 都在回答"怎么理解" |
| CONNECT | 关联概念、应用场景 | 同类词、词族 | 前置知识、向上延伸 | ✅ 都在回答"和什么有关" |
| VERIFY | 自测、判断场景 | 造句、听辨 | 例题、易错点 | ✅ 都在回答"怎么证明会了" |

**结论：Core Schema v0.1 通过压力测试。**

同一个四槽位骨架，不需要任何修改就能容纳三种完全不同类型的知识。差异全部由 Profile 层吸收，Core 层保持稳定。

---

## 六、对仓库结构的影响

基于 Core Schema + Profile 架构，仓库结构调整为：

```
suishouxue-open/
├── README.md
├── LICENSE                        ← AGPL v3
├── CONTRIBUTING.md
├── CHANGELOG.md
│
├── core/
│   └── SCHEMA.md                  ← 本文档（Core Schema 定义）
│
├── profiles/
│   ├── README.md                  ← Profile 接口规范 + 如何创建自己的 Profile
│   ├── general.yaml               ← 通用学习（最小公约数）
│   ├── ai-tech.yaml               ← AI/技术学习（九聿原版方法论）
│   └── language.yaml              ← 语言学习
│
├── examples/
│   ├── embedding.md               ← ai-tech Profile 生成的示例
│   ├── apple.md                   ← language Profile 生成的示例
│   └── (更多示例随 Profile 增加)
│
├── docs/
│   ├── 01-随手学是什么.md
│   ├── 02-Lite-快速上手.md
│   ├── 03-卡片规范详解.md
│   └── 04-常见问题与排错.md
│
├── kb-mcp/
│   ├── server.py
│   ├── requirements.txt
│   ├── config.example.yaml
│   ├── .env.example
│   ├── healthcheck.py
│   └── README.md
│
└── tests/
    └── test_basic_save.py
```

**注意**：已移除独立的 `templates/` 目录。Profile 就是 Single Source of Truth——卡片结构的定义只在 Profile YAML 里存在一份。`examples/` 目录用真实的示例卡片展示效果，不作为结构定义。

---

## 七、评审结论与修订记录

### 评审结论（2026-08-17）

Core Schema v0.1 **原则通过**。以下为评审意见及修订情况：

| 评审意见 | 修订状态 |
|---|---|
| 补 `id` 字段作为卡片唯一标识 | ✅ 已补入 Metadata |
| 补 `schema_version` 和 `profile_version` | ✅ 已补入 Metadata 和 Profile 接口 |
| `category` 是否必填下放给 Profile 决定 | ✅ 已改为 ⚙️ 由 Profile 的 `category_required` 控制 |
| 允许槽位存在但内容不硬凑 | ✅ 已在 §2.2 增加"留白"说明 |
| 压力测试到此停止，不再扩展新学科 | ✅ 三个测试已足够验证 |
| v1 暂定 general + ai-tech + language 三个 Profile | ✅ 已确认 |

### 遗留决议项

1. ~~**License 选择**~~：已确定 AGPL v3
2. **`id` 的生成规则细节**：建议 `profile前缀-slug`（如 `ai-tech-embedding`），是否需要更严格的唯一性保障（如加时间戳或哈希），待施工时确定

### 下一步

Core Schema v0.1 final 定稿 → 进入仓库骨架施工阶段。

---

*文档定稿 · 柯言 · 2026-08-17*
