# kb-mcp/http_app.py — 随手学 Private：带令牌认证的 Streamable HTTP 服务
#
# Copyright (C) 2026  随手学 Open / SuiShouXue Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
把 MCP 服务以 Streamable HTTP 方式提供，并强制令牌认证。

安全边界：
  - 认证不可关闭：没有有效令牌时拒绝启动。
  - 默认只监听 127.0.0.1；监听其他地址必须显式开启 allow_remote_bind。
  - 本程序只说 HTTP，不处理 TLS。公网访问必须放在 HTTPS 反向代理后面
    （部署模板 deploy/ 使用 Caddy）。
  - 开启 Host/Origin 校验，防 DNS 重绑定。
  - 除 /healthz 外，所有请求先校验 Authorization: Bearer <token>。
"""

from __future__ import annotations

import ipaddress
import json
import logging

from mcp.server.transport_security import TransportSecuritySettings

from auth_tokens import TokenStore

HEALTH_PATH = "/healthz"
MCP_PATH = "/mcp"

logger = logging.getLogger("suishouxue.http")

_LOOPBACK_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*", "127.0.0.1", "localhost", "[::1]"]
_LOOPBACK_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


class StartupError(RuntimeError):
    """配置不安全或不完整，拒绝启动。"""


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def check_startup(http_config: dict, store: TokenStore) -> None:
    """启动前的安全检查。"""
    if store.active_count() == 0:
        raise StartupError(
            f"没有可用的访问令牌（{store.path}）。"
            f"请先运行: python auth_tokens.py create <设备名>"
        )
    if not is_loopback(http_config["host"]) and not http_config["allow_remote_bind"]:
        raise StartupError(
            f"拒绝监听非本机地址 {http_config['host']}：本程序不处理 HTTPS，"
            f"公网访问必须放在 HTTPS 反向代理后面。确认已经这样部署后，"
            f"设置 http.allow_remote_bind: true（或 SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND=true）。"
        )


def transport_security(http_config: dict) -> TransportSecuritySettings:
    hosts = list(_LOOPBACK_HOSTS)
    origins = list(_LOOPBACK_ORIGINS)
    for host in http_config["allowed_hosts"]:
        hosts.append(host)
        origins.append(f"https://{host}")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


async def _send_json(send, status: int, body: dict, headers: list | None = None) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(payload)).encode()),
            (b"cache-control", b"no-store"),
            *(headers or []),
        ],
    })
    await send({"type": "http.response.body", "body": payload})


class BearerAuth:
    """ASGI 中间件：除健康检查外，所有 HTTP 请求都必须携带有效令牌。"""

    def __init__(self, app, store: TokenStore):
        self.app = app
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            # 不提供 websocket 等其他协议
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return

        if scope.get("path") == HEALTH_PATH:
            return await _send_json(send, 200, {"status": "ok"})

        token = None
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                scheme, _, credential = value.decode("latin-1").partition(" ")
                if scheme.lower() == "bearer":
                    token = credential.strip()
                break

        device = self.store.verify(token) if token else None
        if device is None:
            # 不记录令牌内容
            logger.warning("拒绝未授权请求: %s %s", scope.get("method"), scope.get("path"))
            return await _send_json(
                send, 401, {"error": "unauthorized"},
                [(b"www-authenticate", b'Bearer realm="suishouxue"')],
            )

        scope.setdefault("state", {})["device"] = device
        return await self.app(scope, receive, send)


def build_app(mcp, http_config: dict, store: TokenStore):
    """组装带认证的 ASGI 应用。"""
    inner = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH,
        # 无状态 + JSON 响应：服务重启不会让客户端会话失效
        stateless_http=True,
        json_response=True,
        transport_security=transport_security(http_config),
        host=http_config["host"],
    )
    return BearerAuth(inner, store)


def run(mcp, http_config: dict, store: TokenStore) -> None:
    import uvicorn

    check_startup(http_config, store)
    app = build_app(mcp, http_config, store)
    print(
        f"随手学 Private 已启动: http://{http_config['host']}:{http_config['port']}{MCP_PATH}"
        f"（{store.active_count()} 个有效令牌）",
        flush=True,
    )
    uvicorn.run(app, host=http_config["host"], port=http_config["port"],
                proxy_headers=True, server_header=False, log_level="warning")
