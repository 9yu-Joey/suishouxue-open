# Private：自托管部署

> 把随手学部署到你自己的服务器和域名上。手机、平板、公司电脑都能连同一个知识库，只有持有访问令牌的设备才能读写。

Private 是给**一个人、多台设备**用的：一台服务器对应一个人的一套卡片。每台设备各发一个令牌，某台设备丢了，就单独吊销它的令牌。

**不支持**多人共用同一台服务器：所有令牌看到的是同一套卡片。

---

## 它和 Lite / Pro 的关系

| | Lite / Pro | Private |
|---|---|---|
| 运行位置 | 你自己的电脑 | 你自己的服务器 |
| 连接方式 | stdio（AI 客户端直接启动 `server.py`） | HTTPS（`https://你的域名/mcp`） |
| 谁能访问 | 只有这台电脑 | 持有有效令牌的设备 |

三者用的是同一个 `server.py` 和同一套卡片格式。Private 只是多了 `--transport http` 这种启动方式。Pro 的 Git 同步在 Private 里照样可以用。

---

## 安全边界（先读这一段）

- **认证不能关闭。** 没有有效令牌时，服务直接拒绝启动。
- **程序本身不处理 HTTPS。** 默认只监听 `127.0.0.1`。要监听其他地址，必须显式开启 `allow_remote_bind`，并且前面一定要有 HTTPS 反向代理。下面的部署模板用 Caddy 自动申请证书。
- **令牌只存哈希。** 服务器上的 `tokens.json` 里没有令牌原文，令牌只在创建时显示一次。
- **吊销立即生效。** 吊销后下一次请求就会被拒绝，不需要重启服务。
- **防 DNS 重绑定。** 只接受发往你自己域名的请求。

---

## 你需要什么

- 一台有公网 IP 的 Linux 服务器，装好 Docker 和 Docker Compose
- 一个域名，把 DNS 的 A（或 AAAA）记录指向这台服务器
- 服务器的 80 和 443 端口可以从外网访问（Caddy 申请证书要用）

下文用 `notes.example.com` 代表你的域名，请换成你自己的。

---

## 第一步：获取代码并填写域名

```bash
git clone https://github.com/9yu-Joey/suishouxue-open.git
cd suishouxue-open/deploy
cp .env.example .env
```

编辑 `deploy/.env`：

```bash
SUISHOUXUE_DOMAIN=notes.example.com
```

## 第二步：构建镜像并签发第一个令牌

服务没有令牌时拒绝启动，所以要**先签发令牌，再启动**：

```bash
docker compose build
docker compose run --rm suishouxue python kb-mcp/auth_tokens.py create laptop
```

终端会显示一串以 `ssx_` 开头的令牌。**它只显示这一次**，请立刻存进密码管理器，或者直接填到客户端配置里。

## 第三步：启动

```bash
docker compose up -d
```

检查是否正常：

```bash
curl https://notes.example.com/healthz
# {"status": "ok"}
```

第一次启动时，Caddy 需要几十秒申请证书。如果一直失败，请检查 DNS 解析，以及 80 / 443 端口是否放行。

## 第四步：连接 AI 客户端

MCP 地址是 `https://notes.example.com/mcp`。每次请求都要带上请求头：

```text
Authorization: Bearer ssx_你的令牌
```

**Claude Code：**

```bash
claude mcp add --transport http suishouxue https://notes.example.com/mcp \
  --header "Authorization: Bearer ssx_你的令牌"
```

**支持自定义请求头的客户端**（如 Cursor）一般这样写：

```json
{
  "mcpServers": {
    "suishouxue": {
      "url": "https://notes.example.com/mcp",
      "headers": { "Authorization": "Bearer ssx_你的令牌" }
    }
  }
}
```

各客户端的具体字段名以它们自己的文档为准。

> 只支持 OAuth 登录的连接器（例如 claude.ai 网页版的自定义连接器）目前连不上 Private，因为 Private 用的是静态令牌，不是 OAuth。

---

## 日常管理

所有命令都在 `deploy/` 目录下执行。

### 新增设备 / 吊销设备

```bash
docker compose exec suishouxue python kb-mcp/auth_tokens.py create phone
docker compose exec suishouxue python kb-mcp/auth_tokens.py list
docker compose exec suishouxue python kb-mcp/auth_tokens.py revoke phone
```

每台设备用自己的令牌。某台设备丢了，只吊销它的令牌，其他设备不受影响。

### 备份

```bash
docker compose exec suishouxue python kb-mcp/backup.py backup --out /data/backups/cards-$(date +%Y%m%d).tar.gz
docker compose cp suishouxue:/data/backups/cards-$(date +%Y%m%d).tar.gz ./
```

第一条命令在服务器的数据卷里打包，第二条把备份文件拷到当前目录。**请把备份文件再拷到服务器以外的地方保存**：只放在同一台服务器上不算备份。

备份范围只包含卡片（卡片目录顶层的 `.md` 文件），**不包含令牌**。换服务器后请重新签发令牌。

### 恢复

```bash
docker compose cp ./cards-20260929.tar.gz suishouxue:/tmp/restore.tar.gz
docker compose exec suishouxue python kb-mcp/backup.py restore --from /tmp/restore.tar.gz
```

恢复**永远不会覆盖**现有卡片：
- 同名且内容相同的卡片，直接跳过；
- 同名但内容不同的卡片，保留服务器上的现有版本，并在输出里列出来，由你决定怎么处理；
- 备份包里如果有子目录、符号链接、`../` 这样的路径，或非 `.md` 文件，整个恢复会被拒绝；
- 为防止恶意备份包撑爆磁盘，单张卡片不超过 10 MiB、最多 50,000 张、**卡片内容**总量不超过 256 MiB；另外每张卡附带的元数据（tar 头、扩展头等）最多 64 KiB，超出就立即停止读取。备份时用的是同一套上限，所以本工具生成的备份一定能恢复。

### 数据在哪里

卡片和令牌文件都在 Docker 数据卷 `suishouxue_suishouxue-data` 里。`docker compose down` 不会删除它，重启和升级后数据都在。

> ⚠️ `docker compose down -v` 会**删除数据卷**，也就删掉了所有卡片。执行前先备份。

### 升级

```bash
git pull
docker compose build
docker compose up -d
```

---

## 不用 Docker 的部署

也可以直接运行：

```bash
cd kb-mcp
pip install -r requirements.txt
python auth_tokens.py create laptop
python server.py --transport http          # 默认只监听 127.0.0.1:8765
```

然后用你熟悉的反向代理（Caddy、Nginx 等）把 HTTPS 流量转发到 `127.0.0.1:8765`，并在配置里把 `http.allowed_hosts` 设为你的域名。

只要反向代理和服务在同一台机器上，就不需要开启 `allow_remote_bind`。

---

## 已知限制

- 单用户：所有令牌共享同一套卡片，不支持多人数据隔离。
- 认证只支持静态令牌，不支持 OAuth。
- 程序本身不处理 HTTPS，必须依赖反向代理。
- 没有内置限流。令牌是 256 位随机数，暴力猜测不可行；如果需要限流，请在反向代理上配置。
- 不提供可用性保证：服务宕机期间无法访问，请自行监控 `/healthz`。
