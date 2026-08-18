# 贡献指南

感谢你对随手学 Open 的关注！我们欢迎各种形式的贡献。

## 你可以做什么

**提交新 Profile**：如果你在学一个我们还没覆盖的学科（数学、音乐、历史……），欢迎创建新的 Profile YAML。请确保它符合 [Profile 接口规范](profiles/README.md)，并附上至少一张示例卡片。

**改进现有 Profile**：觉得某个 Profile 的字段设计可以更好？欢迎提 Issue 讨论，或直接提 PR。

**修复 Bug**：发现 kb-mcp 服务端有问题？欢迎提交修复。

**改进文档**：发现文档有错误、表述不清、或缺少内容？欢迎修改。

## 提交流程

1. Fork 本仓库
2. 创建你的分支：`git checkout -b feature/your-feature`
3. 提交你的修改：`git commit -m "feat: 添加 mathematics Profile"`
4. 推送分支：`git push origin feature/your-feature`
5. 创建 Pull Request

## Commit 规范

我们使用简化版的 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

- `feat:` 新功能或新 Profile
- `fix:` 修复 bug
- `docs:` 文档修改
- `refactor:` 代码重构（不影响功能）
- `test:` 添加或修改测试

## Profile 提交要求

提交新 Profile 时，请确保：

1. YAML 文件放在 `profiles/` 目录下
2. 四个槽位（KNOW / UNDERSTAND / CONNECT / VERIFY）各至少定义一个字段
3. 包含 `name`、`display_name`、`description`、`version`、`min_schema_version` 等必要元信息
4. 在 `examples/` 目录下附带至少一张使用该 Profile 生成的示例卡片
5. 示例卡片的 frontmatter 必须包含完整的 Metadata 字段

## 行为准则

请保持友善和建设性。我们是一个小型开源项目，每个贡献者的时间都很宝贵。

## 许可证

提交贡献即表示你同意你的贡献将遵循本项目的 [AGPL v3 许可证](LICENSE)。
