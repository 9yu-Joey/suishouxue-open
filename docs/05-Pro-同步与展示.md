# Pro：同步与展示

> 在 Lite 的基础上，多加两件事：卡片存进你自己的私有 Git 仓库，可以多台电脑同步、随时回滚；再挑一部分卡片生成一个网页，分享给别人看。

两项能力都是**可选的**，默认关闭。不开启时，随手学的行为和 Lite 完全一样。

| 能力 | 做什么 | 需要什么 |
|---|---|---|
| Git 同步 | 每次保存/更新卡片自动在本地提交；说一句"同步一下"就推到你的私有仓库 | Git、一个 GitHub（或任意 Git 托管）私有仓库 |
| 静态站点 | 把带 `public` 标签的卡片生成只读网页，可部署到 GitHub Pages | `pip install -r requirements-pro.txt` |

---

## 第一部分：Git 同步

### 你需要什么

- 已经跑通 [Lite 快速上手](02-Lite-快速上手.md)
- 电脑上装了 Git（终端里 `git --version` 能看到版本号）
- 一个 GitHub 账号

### 第一步：建一个私有仓库专门放卡片

在 GitHub 新建仓库，例如叫 `my-cards`，**可见性选 Private**。

> 卡片仓库和 `suishouxue-open` 是两个仓库：前者放你的学习内容，后者是程序。不要把卡片放进 `suishouxue-open` 目录里。

### 第二步：克隆到本地，并确认你能推送

```bash
cd ~
git clone git@github.com:你的用户名/my-cards.git
cd my-cards
```

**先手动推送一次，确认认证没问题**。随手学在后台运行，没有办法弹窗问你密码，所以认证必须提前配好：

- 推荐用 SSH key：参考 GitHub 文档「Connecting to GitHub with SSH」
- 或者用 HTTPS + Git credential helper（例如 GitHub CLI 的 `gh auth login`）

```bash
git commit --allow-empty -m "init"
git push origin main
```

能推上去就说明准备好了。

> ⚠️ **不要把 token 写进 remote 地址或随手学配置里。** 随手学不读取、不保存任何凭据，认证完全交给你的 Git 自己处理。

### 第三步：让随手学使用这个仓库

编辑 `kb-mcp/config.yaml`：

```yaml
cards_dir: "/Users/你的用户名/my-cards"   # 用绝对路径

sync:
  enabled: true
  remote: "origin"   # remote 名称，不是 URL
  branch: "main"
```

也可以在 `kb-mcp/.env` 里去掉 `SUISHOUXUE_CARDS_DIR`、`SUISHOUXUE_SYNC_ENABLED` 两行开头的 `# ` 并填写；或者直接写在 AI 客户端的 MCP 配置里：

```json
{
  "mcpServers": {
    "suishouxue": {
      "command": "python3",
      "args": ["/你的路径/suishouxue-open/kb-mcp/server.py"],
      "env": {
        "SUISHOUXUE_CARDS_DIR": "/Users/你的用户名/my-cards",
        "SUISHOUXUE_SYNC_ENABLED": "true"
      }
    }
  }
}
```

然后运行健康检查：

```bash
cd kb-mcp
python healthcheck.py
```

看到 `[OK] Git 同步已启用` 就可以了。重启 AI 客户端，工具列表里会多出 `kb_sync`。

### 第四步：日常使用

- **保存和更新卡片**：和以前一样。区别是每次成功后，随手学会在卡片仓库里自动做一次本地提交（只提交这张卡片，不联网）。
- **同步**：对 AI 说"同步一下知识库"，AI 会调用 `kb_sync`。它会依次：
  1. 把你在编辑器里手动改过的卡片先提交；
  2. 拉取远端的新卡片；
  3. 合并；
  4. 推送本地的新卡片。
- **看状态**：说"看看知识库同步状态"，AI 会调用 `kb_sync(action="status")`，只看本地，不联网。

**已经有 Lite 卡片？** 把原来 `cards/` 里的 `.md` 文件复制到 `my-cards/`，下次同步时会自动提交并推送。

**多台电脑？** 在另一台电脑上同样克隆 `my-cards`、同样配置。开始学习前先同步一次，拿到另一台电脑上的卡片。

### 同步结果怎么看

`kb_sync` 返回的 `status`：

| status | 含义 | 你的卡片 |
|---|---|---|
| `ok` | 同步完成。`pulled` 是拉下来的提交数，`pushed` 是推上去的提交数 | 已同步 |
| `conflict` | 两台电脑改了同一张卡片，无法自动合并。`files` 列出了冲突的卡片 | **本地原样保留**，见下方「处理冲突」 |
| `push_failed` | 推送失败（网络问题，或者别处刚推了新内容） | 本地提交保留，再同步一次即可 |
| `fetch_failed` | 连不上远端（网络或认证问题） | 本地提交保留 |
| `no_remote` | 卡片仓库还没配置 remote | 不受影响 |
| `not_repo` | `cards_dir` 不是一个独立的 Git 仓库 | 不受影响 |
| `dirty` | 卡片目录里有非卡片文件改了但没提交 | 不受影响，先自己处理这些文件 |
| `disabled` | 没有开启 sync | 不受影响 |

随手学**永远不会** force push，也不会为了同步成功去覆盖任何一方的卡片。

### 处理冲突

冲突时，随手学已经取消了这次合并，你的本地卡片和合并前一模一样。手动解决的步骤：

```bash
cd ~/my-cards
git pull --no-rebase origin main   # 这一步会把冲突标记写进卡片文件
```

用编辑器打开冲突的卡片，会看到：

```text
<<<<<<< HEAD
这台电脑上的版本
=======
另一台电脑上的版本
>>>>>>> ...
```

保留你想要的内容，删掉 `<<<<<<<`、`=======`、`>>>>>>>` 这几行，然后：

```bash
git add 冲突的卡片文件名.md
git commit -m "解决卡片冲突"
```

最后回到 AI 对话里再同步一次。

### 备份边界

- Git 会记下每张卡片的每一次修改，改错了可以用 `git log` / `git checkout` 找回。
- 推送到 GitHub 之后，卡片在你的电脑之外多了一份副本。**还没推送的提交只存在本机。**
- 同步不是实时的，只在你调用 `kb_sync` 时发生。
- 删除 GitHub 仓库或账号，远端副本也会一起消失。重要内容请另外备份。

---

## 第二部分：生成知识卡片网站

### ⚠️ 先读这一段：私有仓库 ≠ 私有网站

GitHub Pages 生成的网站**通常任何人都能访问**，即使卡片仓库是 private。

所以随手学的规则是：**默认一张卡片都不公开**。只有 `tags` 里带 `public` 标签的卡片才会被生成网页，其他卡片不会进入网站，标题也不会出现在构建日志里。

另外，GitHub 免费账号只能在 **public 仓库** 使用 Pages。如果你是免费账号，**不要为了用 Pages 把卡片仓库改成 public**，那样会把所有卡片都公开。你可以在本地生成网站，再部署到别的静态托管服务。

### 第一步：选出要公开的卡片

对 AI 说"把 Embedding 这张卡设为公开"。AI 会用 `kb_update` 给它加上 `public` 标签（注意要保留原来的标签）。

想改用别的标签名，可以设置 `site.publish_tag`，或者生成时加 `--tag`。

### 第二步：本地预览

```bash
cd kb-mcp
pip install -r requirements-pro.txt
python build_site.py --cards ~/my-cards --out ./site
```

用浏览器打开 `kb-mcp/site/index.html` 看效果。

生成器只会覆盖它自己生成过的目录。如果 `--out` 指向一个已有内容的普通目录，它会拒绝执行，不会删你的文件。

### 第三步：部署到 GitHub Pages

1. 把 [`kb-mcp/templates/github-pages.yml`](../kb-mcp/templates/github-pages.yml) 复制到**卡片仓库**的 `.github/workflows/pages.yml`。
2. 提交并推送：

   ```bash
   cd ~/my-cards
   git add .github/workflows/pages.yml
   git commit -m "添加知识卡站点发布"
   git push origin main
   ```

3. 在 GitHub 打开卡片仓库 → Settings → Pages → Source 选 **GitHub Actions**。
4. 在 Actions 页面找到「发布随手学知识卡站点」，点 **Run workflow**。

模板默认只能手动触发。想每次同步后自动发布，就取消模板里 `push` 触发器的注释。

**想从网站上撤下某张卡片？** 去掉它的 `public` 标签，同步后重新运行 workflow。

---

## 已知限制

- 冲突需要手动解决，随手学不会自动合并同一张卡片的两份修改。
- 同步只在调用 `kb_sync` 时发生，不是实时的。
- 网站是纯静态只读页面，没有搜索和评论。
- 网站没有访问控制。需要登录才能看的站点属于 Private 阶段。
