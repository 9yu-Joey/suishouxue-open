# Profile 接口规范

## Profile 是什么

Profile 是随手学的"学科模板"。它告诉 AI 和系统：**在这个学科下，四个学习槽位里各应该记录什么内容。**

Core Schema 定义了四个槽位（KNOW / UNDERSTAND / CONNECT / VERIFY）的含义，Profile 定义了每个槽位里的**具体字段**。

打个比方：Core Schema 是一个书架，固定了四层隔板。Profile 决定每层隔板上放什么形状的书。

## Profile 就是 Single Source of Truth

卡片结构的定义**只存在于 Profile YAML 中**。没有单独的 templates/ 目录，没有第二份结构定义。AI 在生成卡片时直接读取 Profile，按字段定义生成内容。

## 内置 Profile

| Profile | 文件 | 适用场景 |
|---------|------|----------|
| `general` | [general.yaml](general.yaml) | 任何学科的通用学习，最小公约数 |
| `ai-tech` | [ai-tech.yaml](ai-tech.yaml) | AI、编程、互联网技术 |
| `language` | [language.yaml](language.yaml) | 英语、日语等语言学习 |

## YAML 结构规范

每个 Profile YAML 必须包含以下信息：

```yaml
# ─── 元信息 ───
name: "profile-id"              # 唯一标识（英文，对应卡片 Metadata 中的 profile 值）
display_name: "显示名称"          # 人类可读名称
description: "一句话描述"         # 说明这个 Profile 适用于什么
version: "0.1"                   # Profile 自身版本号
min_schema_version: "0.1"        # 依赖的最低 Core Schema 版本

# ─── 分类体系 ───
category_required: true/false    # 该 Profile 下 category 是否必填
categories:                      # 可选的分类值列表
  - "分类A"
  - "分类B"

# ─── 四槽位字段定义 ───
slots:
  know:
    label: "槽位显示名"
    fields:
      - name: "field_id"         # 字段标识（英文）
        label: "字段显示名"       # 人类可读名称
        required: true/false     # 是否必填
        hint: "填写提示"          # 告诉 AI 怎么写这个字段

  understand:
    label: "..."
    fields: [...]

  connect:
    label: "..."
    fields: [...]

  verify:
    label: "..."
    fields: [...]

# ─── AI 生成指令（可选）───
ai_instructions: |
  在这个学科下生成卡片时的额外规则
```

## 接口规则

1. **每个槽位至少定义一个字段** — 保证卡片结构完整
2. **槽位允许留白** — Profile 定义的是"这个槽位可以装什么"，不是"每个槽位必须装满"
3. **`name` 是唯一标识** — 对应卡片 Metadata 中的 `profile` 值
4. **`version` 每次更新时递增** — 生成卡片时写入 `profile_version`，用于识别旧卡片
5. **`min_schema_version` 声明兼容性** — 未来 Schema 升级时，系统据此判断 Profile 是否需要更新
6. **`category_required` 由 Profile 决定** — Core 不强制 category 必填
7. **`ai_instructions` 是教学法** — 告诉 AI 在这个学科下怎么写卡片

## 创建你自己的 Profile

1. 复制 `general.yaml` 作为起点
2. 修改 `name`、`display_name`、`description`
3. 为四个槽位定义适合你学科的字段
4. 编写 `ai_instructions`
5. 创建一张示例卡片验证效果
6. 提交 PR（详见 [贡献指南](../CONTRIBUTING.md)）
