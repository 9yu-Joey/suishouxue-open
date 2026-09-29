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

    def test_concurrent_create_cannot_resurrect_revoked_token(self):
        """签发写回前另一个进程吊销了旧设备：吊销不能被旧列表覆盖掉"""
        import threading
        from auth_tokens import TokenStore
        lost = self.store.create("lost-phone")
        original_save = self.store._save
        paused, resume = threading.Event(), threading.Event()

        def slow_save(tokens):
            paused.set()
            resume.wait(5)
            original_save(tokens)

        self.store._save = slow_save
        creator = threading.Thread(target=lambda: self.store.create("laptop"))
        creator.start()
        self.assertTrue(paused.wait(5))
        revoker = threading.Thread(target=lambda: TokenStore(self.path).revoke("lost-phone"))
        revoker.start()
        revoker.join(0.3)
        self.assertTrue(revoker.is_alive(), "吊销应当等待签发事务结束")
        resume.set()
        creator.join(5)
        revoker.join(5)

        fresh = TokenStore(self.path)
        self.assertIsNone(fresh.verify(lost))
        self.assertEqual([e["name"] for e in fresh.entries() if not e["revoked"]], ["laptop"])

    def test_parallel_processes_keep_every_change(self):
        """多个进程同时签发和吊销，最终结果不丢任何一次修改"""
        import subprocess
        from auth_tokens import TokenStore
        for i in range(8):
            self.store.create(f"old{i}")
        script = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from auth_tokens import TokenStore; s = TokenStore(sys.argv[2]);"
            "s.create(sys.argv[3]) if sys.argv[4] == 'c' else s.revoke(sys.argv[3])"
        )
        kb = str(Path(__file__).parent.parent / "kb-mcp")
        procs = [subprocess.Popen([sys.executable, "-c", script, kb, str(self.path), f"new{i}", "c"])
                 for i in range(8)]
        procs += [subprocess.Popen([sys.executable, "-c", script, kb, str(self.path), f"old{i}", "r"])
                  for i in range(8)]
        for proc in procs:
            self.assertEqual(proc.wait(30), 0)
        state = {e["name"]: e["revoked"] for e in TokenStore(self.path).entries()}
        self.assertEqual(sorted(n for n, r in state.items() if r is None),
                         sorted(f"new{i}" for i in range(8)))
        self.assertTrue(all(state[f"old{i}"] for i in range(8)))

    def test_corrupt_token_file_is_rejected(self):
        """结构不对的令牌条目不能算作有效令牌"""
        import auth_tokens
        for content in ['{"tokens": [{}]}', '{"tokens": [{"name": "x", "hash": "abc"}]}',
                        '{"tokens": {}}', '[]', 'not json']:
            self.path.write_text(content, encoding="utf-8")
            store = auth_tokens.TokenStore(self.path)
            with self.assertRaises(ValueError, msg=content):
                store.active_count()
            with self.assertRaises(ValueError, msg=content):
                store.verify("ssx_anything")

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

    def test_quoted_false_does_not_enable_remote_bind(self):
        """YAML 里带引号的 "false" 不能被当成 True 而绕过启动检查"""
        import http_app
        import kbcore
        self.store.create("x")
        config = kbcore._load_http_config({"host": "0.0.0.0", "allow_remote_bind": "false"})
        self.assertIs(config["allow_remote_bind"], False)
        with self.assertRaises(http_app.StartupError):
            http_app.check_startup(config, self.store)
        self.assertIs(kbcore._load_http_config({"allow_remote_bind": "true"})["allow_remote_bind"], True)
        self.assertIs(kbcore._load_http_config({"allow_remote_bind": None})["allow_remote_bind"], False)
        for bad in ["maybe", "fasle", 2, [], "enabled"]:
            with self.assertRaises(ValueError, msg=bad):
                kbcore._load_http_config({"allow_remote_bind": bad})
        self.assertIs(kbcore._load_sync_config({"enabled": "false"})["enabled"], False)
        with self.assertRaises(ValueError):
            kbcore._load_sync_config({"enabled": "nope"})

    def test_invalid_env_bool_is_rejected(self):
        import kbcore
        os.environ["SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND"] = "sure"
        try:
            with self.assertRaises(ValueError):
                kbcore._load_http_config(None)
        finally:
            del os.environ["SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND"]

    def test_corrupt_token_file_refuses_startup(self):
        import http_app
        self.store.path.write_text('{"tokens": [{}]}', encoding="utf-8")
        with self.assertRaises(http_app.StartupError):
            http_app.check_startup(_http_config(), self.store)

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
        # trust_env=False：回环测试必须直连，不能被宿主机的代理设置劫持
        return httpx2.post(f"{self.base}/mcp", json=body, timeout=10, trust_env=False, headers={
            "accept": "application/json, text/event-stream", **headers})

    async def _mcp(self, calls, token=None):
        import httpx2
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        headers = {"Authorization": f"Bearer {token or self.token}"}
        async with httpx2.AsyncClient(headers=headers, trust_env=False) as client:
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
            resp = httpx2.get(f"{self.base}/healthz", timeout=10, trust_env=False)
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

    def test_corrupt_token_file_fails_closed_at_runtime(self):
        """运行中令牌文件被写坏：请求一律 401，而不是 500 或放行"""
        with self.live():
            self.store.path.write_text('{"tokens": [{}]}', encoding="utf-8")
            resp = self.post({"authorization": f"Bearer {self.token}"})
        self.assertEqual(resp.status_code, 401)

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

    def test_backup_refuses_cards_restore_would_reject(self):
        """本工具生成的备份一定能恢复：超限卡片在备份阶段就拒绝"""
        original = self.backup.MAX_CARD_BYTES
        self.backup.MAX_CARD_BYTES = 10
        try:
            (self.cards / "large.md").write_bytes(b"x" * 11)
            archive = self.tmp / "big.tar.gz"
            with self.assertRaises(self.backup.BackupError):
                self.backup.backup(self.cards, archive)
            self.assertFalse(archive.exists())
            self.assertFalse(archive.with_name(archive.name + ".partial").exists())
            (self.cards / "large.md").write_bytes(b"x" * 10)  # 恰好等于上限
            self.backup.backup(self.cards, archive)
            self.assertIn("large.md", self.backup.restore(archive, self.tmp / "r")["restored"])
        finally:
            self.backup.MAX_CARD_BYTES = original

    def test_hidden_cards_are_left_out_of_backup(self):
        (self.cards / ".draft.md").write_text("hidden", encoding="utf-8")
        archive = self.tmp / "b.tar.gz"
        self.assertEqual(self.backup.backup(self.cards, archive), 2)
        self.backup.restore(archive, self.tmp / "r")

    def _bomb(self, count, size):
        archive = self.tmp / f"bomb-{count}-{size}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for i in range(count):
                info = tarfile.TarInfo(f"z{i}.md")
                info.size = size
                tar.addfile(info, io.BytesIO(b"\0" * size))
        return archive

    def test_decompression_bomb_limits(self):
        """数量或总解压量超限：整个恢复被拒绝，且一张卡都不写"""
        saved = (self.backup.MAX_CARDS, self.backup.MAX_TOTAL_BYTES)
        self.backup.MAX_CARDS, self.backup.MAX_TOTAL_BYTES = 5, 1000
        try:
            for archive in [self._bomb(6, 1), self._bomb(3, 400)]:
                target = self.tmp / ("t-" + archive.stem)
                with self.assertRaises(self.backup.BackupError):
                    self.backup.restore(archive, target)
                self.assertFalse(target.exists() and any(target.iterdir()))
            self.backup.restore(self._bomb(5, 200), self.tmp / "ok")
        finally:
            self.backup.MAX_CARDS, self.backup.MAX_TOTAL_BYTES = saved

    def _pax_archive(self, pax_headers, name="card.md", data=b"x"):
        archive = self.tmp / "pax.tar.gz"
        with tarfile.open(archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.pax_headers = pax_headers
            tar.addfile(info, io.BytesIO(data))
        return archive

    def test_pax_extended_header_counts_toward_limits(self):
        """PAX 扩展头也受上限约束：小压缩包里塞大扩展头会被拒绝，且不写任何卡"""
        archive = self._pax_archive({"comment": "x" * (1024 * 1024)})
        self.assertLess(archive.stat().st_size, 4096)
        target = self.tmp / "pax-target"
        with self.assertRaises(self.backup.BackupError):
            self.backup.restore(archive, target)
        self.assertFalse(target.exists() and any(target.iterdir()))

        # 陆行舟的原始复现：总量上限调到 1024 字节时同样必须拒绝
        saved = self.backup.MAX_TOTAL_BYTES
        self.backup.MAX_TOTAL_BYTES = 1024
        try:
            with self.assertRaises(self.backup.BackupError):
                self.backup.restore(archive, self.tmp / "pax-target-2")
        finally:
            self.backup.MAX_TOTAL_BYTES = saved

    def test_huge_numeric_pax_header_rejected_quickly(self):
        """超大数字扩展头不能让解析长时间占满 CPU"""
        archive = self._pax_archive({"mtime": "9" * (4 * 1024 * 1024)})
        started = time.monotonic()
        with self.assertRaises(self.backup.BackupError):
            self.backup.restore(archive, self.tmp / "slow")
        self.assertLess(time.monotonic() - started, 5)

    def test_long_and_unicode_names_roundtrip(self):
        """本工具生成的合法扩展头（长文件名、中文名）仍能正常恢复"""
        long_name = "长" * 40 + "-" + "x" * 60 + ".md"  # 超过 tar 普通头的 100 字节，需要扩展头
        (self.cards / long_name).write_text("long", encoding="utf-8")
        archive = self.tmp / "b.tar.gz"
        self.backup.backup(self.cards, archive)
        result = self.backup.restore(archive, self.tmp / "r")
        self.assertIn(long_name, result["restored"])
        self.assertIn("我的 卡片.md", result["restored"])

    def test_corrupt_archive_reports_backup_error(self):
        archive = self.tmp / "broken.tar.gz"
        archive.write_bytes(b"\x1f\x8b not really gzip")
        with self.assertRaises(self.backup.BackupError):
            self.backup.restore(archive, self.tmp / "r")

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
