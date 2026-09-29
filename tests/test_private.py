#!/usr/bin/env python3
"""
随手学 Open — Private 测试：访问令牌、HTTP 认证、持久化、备份恢复

HTTP 测试在本机回环地址上启动真实的 uvicorn 服务，并用 MCP 官方客户端连接。

Copyright (C) 2026 九聿 (Joey)
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import asyncio
import contextlib
import io
import json
import os
import shutil
import socket
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "kb-mcp"))

_FULL_SLOTS = "## KNOW\n\ntest\n\n## UNDERSTAND\n\ntest\n\n## CONNECT\n\ntest\n\n## VERIFY\n\ntest"


def _http_config(**overrides):
    config = {"host": "127.0.0.1", "port": 0, "tokens_file": "unused",
              "allow_remote_bind": False, "allowed_hosts": []}
    config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# 令牌
# ---------------------------------------------------------------------------

class TestTokenStore(unittest.TestCase):

    def setUp(self):
        from auth_tokens import TokenStore
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "tokens.json"
        self.store = TokenStore(self.path)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_verify(self):
        token = self.store.create("laptop")
        self.assertTrue(token.startswith("ssx_"))
        self.assertEqual(self.store.verify(token), "laptop")

    def test_file_has_no_plaintext_and_is_private(self):
        token = self.store.create("laptop")
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn(token, text)
        self.assertNotIn(token[4:], text)
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_and_malformed_tokens_rejected(self):
        token = self.store.create("laptop")
        for bad in ["", "ssx_", "ssx_wrong", token + "x", token[4:], token.upper()]:
            self.assertIsNone(self.store.verify(bad), bad)

    def test_revoke_takes_effect_for_running_server(self):
        """另一个进程吊销后，已加载的 store 下次校验立即拒绝（不需要重启）"""
        from auth_tokens import TokenStore
        token = self.store.create("phone")
        self.assertEqual(self.store.verify(token), "phone")
        self.assertEqual(TokenStore(self.path).revoke("phone"), 1)
        self.assertIsNone(self.store.verify(token))
        self.assertEqual(self.store.active_count(), 0)

    def test_devices_revoked_independently(self):
        a = self.store.create("laptop")
        b = self.store.create("phone")
        self.store.revoke("phone")
        self.assertEqual(self.store.verify(a), "laptop")
        self.assertIsNone(self.store.verify(b))

    def test_name_rules(self):
        self.store.create("laptop")
        with self.assertRaises(ValueError):
            self.store.create("laptop")
        for bad in ["", "-x", "a b", "../x", "x" * 65]:
            with self.assertRaises(ValueError):
                self.store.create(bad)
        self.store.revoke("laptop")
        self.store.create("laptop")  # 吊销后可以重新签发

    def test_cli_shows_token_once_and_list_hides_it(self):
        import auth_tokens
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(auth_tokens.main(["--file", str(self.path), "create", "cli"]), 0)
        token = next(w for w in out.getvalue().split() if w.startswith("ssx_"))
        listing = io.StringIO()
        with contextlib.redirect_stdout(listing):
            auth_tokens.main(["--file", str(self.path), "list"])
        self.assertIn("cli", listing.getvalue())
        self.assertNotIn(token, listing.getvalue())
        self.assertNotIn(json.loads(self.path.read_text())["tokens"][0]["hash"], listing.getvalue())


# ---------------------------------------------------------------------------
# 启动检查
# ---------------------------------------------------------------------------

class TestStartupChecks(unittest.TestCase):

    def setUp(self):
        from auth_tokens import TokenStore
        self.tmp = Path(tempfile.mkdtemp())
        self.store = TokenStore(self.tmp / "tokens.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refuses_without_active_token(self):
        import http_app
        with self.assertRaises(http_app.StartupError):
            http_app.check_startup(_http_config(), self.store)
        self.store.create("x")
        self.store.revoke("x")
        with self.assertRaises(http_app.StartupError):
            http_app.check_startup(_http_config(), self.store)

    def test_refuses_remote_bind_unless_explicit(self):
        import http_app
        self.store.create("x")
        for host in ["0.0.0.0", "::", "192.168.1.5", "notes.example.com"]:
            with self.assertRaises(http_app.StartupError):
                http_app.check_startup(_http_config(host=host), self.store)
        http_app.check_startup(_http_config(host="0.0.0.0", allow_remote_bind=True), self.store)
        for host in ["127.0.0.1", "localhost", "::1", "[::1]"]:
            http_app.check_startup(_http_config(host=host), self.store)

    def test_http_config_from_env(self):
        import kbcore
        env = {"SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND": "true",
               "SUISHOUXUE_ALLOWED_HOSTS": "notes.example.com, b.example.com"}
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            http = kbcore._load_http_config(None)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertTrue(http["allow_remote_bind"])
        self.assertEqual(http["allowed_hosts"], ["notes.example.com", "b.example.com"])
        self.assertEqual(kbcore._load_http_config(None)["host"], "127.0.0.1")


# ---------------------------------------------------------------------------
# 真实 HTTP 服务
# ---------------------------------------------------------------------------

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LiveServer:
    """在后台线程里运行 uvicorn。"""

    def __init__(self, app, port):
        import uvicorn
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                                    log_level="error", lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline:
                raise RuntimeError("uvicorn 启动超时")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=10)


class TestHttpServer(unittest.TestCase):

    def setUp(self):
        import server
        from auth_tokens import TokenStore
        self.server_mod = server
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (server.CARDS_DIR, server.SYNC)
        server.CARDS_DIR = self.tmp / "cards"
        server.SYNC = {"enabled": False, "remote": "origin", "branch": "main"}
        self.store = TokenStore(self.tmp / "tokens.json")
        self.token = self.store.create("laptop")
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server_mod.CARDS_DIR, self.server_mod.SYNC = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def live(self):
        import http_app
        app = http_app.build_app(self.server_mod.mcp, _http_config(port=self.port), self.store)
        return _LiveServer(app, self.port)

    def post(self, headers):
        import httpx2
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        return httpx2.post(f"{self.base}/mcp", json=body, timeout=10, headers={
            "accept": "application/json, text/event-stream", **headers})

    async def _mcp(self, calls, token=None):
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        headers = {"Authorization": f"Bearer {token or self.token}"}
        async with httpx2.AsyncClient(headers=headers) as client:
            async with streamable_http_client(f"{self.base}/mcp", http_client=client) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    results = []
                    for name, args in calls:
                        if name == "list_tools":
                            tools = await session.list_tools()
                            results.append(sorted(t.name for t in tools.tools))
                        else:
                            res = await session.call_tool(name, args)
                            results.append(json.loads(res.content[0].text))
                    return results

    def test_health_needs_no_token_and_leaks_nothing(self):
        import httpx2
        with self.live():
            resp = httpx2.get(f"{self.base}/healthz", timeout=10)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_unauthorized_requests_rejected(self):
        """未授权访问：无令牌、错误令牌、错误认证方案、已吊销令牌都返回 401"""
        revoked = self.store.create("old-phone")
        self.store.revoke("old-phone")
        cases = [
            {},
            {"authorization": "Bearer ssx_wrong"},
            {"authorization": f"Basic {self.token}"},
            {"authorization": self.token},
            {"authorization": f"Bearer {revoked}"},
        ]
        with self.live():
            for headers in cases:
                resp = self.post(headers)
                self.assertEqual(resp.status_code, 401, headers)
                self.assertIn("Bearer", resp.headers.get("www-authenticate", ""))
                self.assertNotIn("tools", resp.text)

    def test_revocation_applies_to_live_server(self):
        with self.live():
            self.assertNotEqual(self.post({"authorization": f"Bearer {self.token}"}).status_code, 401)
            self.store.revoke("laptop")
            self.assertEqual(self.post({"authorization": f"Bearer {self.token}"}).status_code, 401)

    def test_dns_rebinding_host_rejected(self):
        with self.live():
            resp = self.post({"authorization": f"Bearer {self.token}", "host": "evil.example"})
        self.assertEqual(resp.status_code, 421)

    def test_authorized_client_full_loop(self):
        with self.live():
            tools, saved, found = asyncio.run(self._mcp([
                ("list_tools", {}),
                ("kb_save", {"title": "Remote Card", "content": _FULL_SLOTS}),
                ("kb_search", {"query": "Remote Card"}),
            ]))
        self.assertIn("kb_save", tools)
        self.assertEqual(saved["status"], "saved")
        self.assertEqual(found["total"], 1)

    def test_data_persists_across_restart(self):
        """服务重启（新的应用实例）后，卡片仍能读取"""
        with self.live():
            asyncio.run(self._mcp([("kb_save", {"title": "Persist", "content": _FULL_SLOTS})]))
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        with self.live():
            (card,) = asyncio.run(self._mcp([("kb_get", {"id": "general-persist"})]))
        self.assertEqual(card["title"], "Persist")


# ---------------------------------------------------------------------------
# 备份与恢复
# ---------------------------------------------------------------------------

class TestBackup(unittest.TestCase):

    def setUp(self):
        import backup
        self.backup = backup
        self.tmp = Path(tempfile.mkdtemp())
        self.cards = self.tmp / "cards"
        self.cards.mkdir()
        (self.cards / "a.md").write_text("card a", encoding="utf-8")
        (self.cards / "我的 卡片.md").write_text("card b", encoding="utf-8")
        (self.cards / "notes.txt").write_text("not a card", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_roundtrip(self):
        archive = self.tmp / "b.tar.gz"
        self.assertEqual(self.backup.backup(self.cards, archive), 2)
        target = self.tmp / "restored"
        result = self.backup.restore(archive, target)
        self.assertEqual(sorted(result["restored"]), ["a.md", "我的 卡片.md"])
        self.assertEqual((target / "a.md").read_text(encoding="utf-8"), "card a")
        self.assertFalse((target / "notes.txt").exists())

    def test_restore_never_overwrites(self):
        archive = self.tmp / "b.tar.gz"
        self.backup.backup(self.cards, archive)
        (self.cards / "a.md").write_text("edited after backup", encoding="utf-8")
        result = self.backup.restore(archive, self.cards)
        self.assertEqual(result["conflicts"], ["a.md"])
        self.assertEqual(result["identical"], ["我的 卡片.md"])
        self.assertEqual((self.cards / "a.md").read_text(encoding="utf-8"), "edited after backup")

    def test_backup_refuses_to_overwrite_archive(self):
        archive = self.tmp / "b.tar.gz"
        archive.write_bytes(b"precious")
        with self.assertRaises(self.backup.BackupError):
            self.backup.backup(self.cards, archive)
        self.assertEqual(archive.read_bytes(), b"precious")

    def _evil_archive(self, name, data=b"x", kind=tarfile.REGTYPE, size=None):
        archive = self.tmp / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind == tarfile.SYMTYPE:
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            else:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return archive

    def test_rejects_unsafe_members(self):
        target = self.tmp / "target"
        for name, kind in [("../escape.md", tarfile.REGTYPE), ("sub/x.md", tarfile.REGTYPE),
                           ("/abs.md", tarfile.REGTYPE), ("link.md", tarfile.SYMTYPE),
                           ("script.sh", tarfile.REGTYPE), (".hidden.md", tarfile.REGTYPE)]:
            with self.assertRaises(self.backup.BackupError, msg=name):
                self.backup.restore(self._evil_archive(name, kind=kind), target)
        self.assertFalse((self.tmp / "escape.md").exists())
        self.assertEqual(list(target.iterdir()) if target.exists() else [], [])

    def test_rejects_oversized_card(self):
        original = self.backup.MAX_CARD_BYTES
        self.backup.MAX_CARD_BYTES = 10
        try:
            with self.assertRaises(self.backup.BackupError):
                self.backup.restore(self._evil_archive("big.md", b"x" * 11), self.tmp / "t")
        finally:
            self.backup.MAX_CARD_BYTES = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
