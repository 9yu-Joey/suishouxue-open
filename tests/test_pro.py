#!/usr/bin/env python3
"""
随手学 Open — Pro 测试：Git 同步与静态站点

Git 测试使用临时目录里的 bare 仓库作为远端，不联网；
并隔离宿主机的全局 Git 配置（签名、hook 等不会干扰测试）。

Copyright (C) 2026 九聿 (Joey)
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "kb-mcp"))

_FULL_SLOTS = "## KNOW\n\ntest\n\n## UNDERSTAND\n\ntest\n\n## CONNECT\n\ntest\n\n## VERIFY\n\ntest"

_HAS_GIT = shutil.which("git") is not None
try:
    import markdown_it  # noqa: F401
    _HAS_MD = True
except ImportError:
    _HAS_MD = False

_GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class _TempEnv(unittest.TestCase):
    """临时目录 + 隔离的 Git 环境 + 可 patch 的 server 全局设置。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._saved_env = {k: os.environ.get(k) for k in [*_GIT_ENV, "GIT_CONFIG_GLOBAL"]}
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text("[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        os.environ.update(_GIT_ENV)
        os.environ["GIT_CONFIG_GLOBAL"] = str(gitconfig)

        import server
        self.server = server
        self._orig = (server.CARDS_DIR, server.SYNC)

    def tearDown(self):
        self.server.CARDS_DIR, self.server.SYNC = self._orig
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use_cards(self, path, enabled=True):
        self.server.CARDS_DIR = path
        self.server.SYNC = {"enabled": enabled, "remote": "origin", "branch": "main"}

    def make_remote(self):
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(remote)],
                       check=True)
        return remote

    def make_clone(self, name, remote):
        path = self.tmp / name
        path.mkdir()
        git(path, "init", "--quiet", "-b", "main")
        git(path, "remote", "add", "origin", str(remote))
        return path

    def save(self, title, extra="", tags=None):
        return self.server.kb_save(title=title, content=_FULL_SLOTS + extra,
                                   profile="general", tags=tags)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

class TestSyncConfig(unittest.TestCase):

    def test_sync_disabled_by_default(self):
        """默认 sync.enabled=false：Lite 行为不变"""
        import kbcore
        saved = os.environ.pop("SUISHOUXUE_SYNC_ENABLED", None)
        try:
            self.assertFalse(kbcore._load_sync_config(None)["enabled"])
        finally:
            if saved is not None:
                os.environ["SUISHOUXUE_SYNC_ENABLED"] = saved

    def test_env_enables_sync(self):
        import kbcore
        os.environ["SUISHOUXUE_SYNC_ENABLED"] = "true"
        try:
            self.assertTrue(kbcore._load_sync_config({"enabled": False})["enabled"])
        finally:
            del os.environ["SUISHOUXUE_SYNC_ENABLED"]

    def test_rejects_option_like_or_url_remote(self):
        """remote 不能是 git 选项，也不能是（可能带 token 的）URL"""
        import kbcore
        for bad in ["--upload-pack=touch x", "https://token@github.com/a/b.git", "-x"]:
            with self.assertRaises(ValueError):
                kbcore.validate_sync_names(bad, "main")
        with self.assertRaises(ValueError):
            kbcore.validate_sync_names("origin", "a..b")

    def test_redact_credentials(self):
        import git_sync
        self.assertEqual(
            git_sync.redact("https://user:FAKE_TOKEN_FOR_TEST@github.com/a/b.git"),
            "https://***@github.com/a/b.git",
        )


# ---------------------------------------------------------------------------
# 本地提交
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GIT, "需要 git")
class TestLocalCommit(_TempEnv):

    def test_disabled_does_not_touch_git(self):
        """sync 关闭时：返回值与 Lite 相同，不产生任何提交"""
        cards = self.make_clone("cards", self.make_remote())
        self.use_cards(cards, enabled=False)
        result = self.save("Plain")
        self.assertNotIn("sync", result)
        self.assertEqual(git(cards, "status", "--porcelain").count("??"), 1)
        self.assertEqual(self.server.kb_sync()["status"], "disabled")

    def test_save_and_update_commit_locally(self):
        cards = self.make_clone("cards", self.make_remote())
        self.use_cards(cards)
        saved = self.save("Alpha")
        self.assertTrue(saved["sync"]["committed"])
        self.server.kb_update(id=saved["id"], content=_FULL_SLOTS + "\n\nmore")
        log = git(cards, "log", "--format=%s")
        self.assertIn("kb: 新增卡片 general-alpha", log)
        self.assertIn("kb: 更新卡片 general-alpha", log)
        self.assertEqual(git(cards, "status", "--porcelain"), "")

    def test_commit_only_touches_the_card(self):
        """本地提交只包含本次卡片，不会顺带提交别的文件"""
        cards = self.make_clone("cards", self.make_remote())
        (cards / "notes.txt").write_text("private scratch", encoding="utf-8")
        self.use_cards(cards)
        self.save("Beta")
        self.assertNotIn("notes.txt", git(cards, "show", "--name-only", "--format="))

    def test_nested_in_parent_repo_is_not_used(self):
        """卡片目录只是在上级仓库里面时，不能把卡片提交进上级仓库"""
        parent = self.make_clone("project", self.make_remote())
        (parent / "README.md").write_text("x", encoding="utf-8")
        git(parent, "add", "README.md")
        git(parent, "commit", "-q", "-m", "init")
        self.use_cards(parent / "kb-mcp" / "cards")
        result = self.save("Gamma")
        self.assertEqual(result["status"], "saved")
        self.assertFalse(result["sync"]["committed"])
        self.assertEqual(git(parent, "rev-list", "--count", "HEAD"), "1")

    def test_plain_directory_saves_with_warning(self):
        self.use_cards(self.tmp / "plain")
        result = self.save("Delta")
        self.assertTrue(Path(result["path"]).exists())
        self.assertIn("warning", result["sync"])
        self.assertEqual(self.server.kb_sync()["status"], "not_repo")


# ---------------------------------------------------------------------------
# kb_sync
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GIT, "需要 git")
class TestKbSync(_TempEnv):

    def test_first_sync_creates_remote_branch(self):
        remote = self.make_remote()
        cards = self.make_clone("a", remote)
        self.use_cards(cards)
        self.save("One")
        result = self.server.kb_sync()
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["pushed"], 1)
        self.assertEqual(git(remote, "rev-list", "--count", "main"), "1")

    def test_sync_is_idempotent(self):
        cards = self.make_clone("a", self.make_remote())
        self.use_cards(cards)
        self.save("One")
        self.server.kb_sync()
        again = self.server.kb_sync()
        self.assertEqual((again["status"], again["pulled"], again["pushed"]), ("ok", 0, 0))

    def test_pull_cards_from_other_device(self):
        remote = self.make_remote()
        a = self.make_clone("a", remote)
        b = self.make_clone("b", remote)
        self.use_cards(a)
        self.save("From A")
        self.server.kb_sync()

        self.use_cards(b)
        self.save("From B")
        result = self.server.kb_sync()
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["pulled"], 1)
        self.assertIsNotNone(self.server._find_card_by_id("general-from-a"))

        self.use_cards(a)
        self.assertEqual(self.server.kb_sync()["status"], "ok")
        self.assertIsNotNone(self.server._find_card_by_id("general-from-b"))

    def test_empty_local_repo_pulls_existing_cards(self):
        """新设备上的空仓库可以直接拉下已有卡片"""
        remote = self.make_remote()
        a = self.make_clone("a", remote)
        self.use_cards(a)
        self.save("Existing")
        self.server.kb_sync()

        fresh = self.make_clone("fresh", remote)
        self.use_cards(fresh)
        result = self.server.kb_sync()
        self.assertEqual(result["status"], "ok", result)
        self.assertIsNotNone(self.server._find_card_by_id("general-existing"))

    def test_conflict_aborts_and_keeps_local_card(self):
        """两端改了同一张卡：取消合并，本地内容一字不改，不留下合并中间状态"""
        remote = self.make_remote()
        a = self.make_clone("a", remote)
        self.use_cards(a)
        card_id = self.save("Shared")["id"]
        self.server.kb_sync()

        b = self.make_clone("b", remote)
        self.use_cards(b)
        self.server.kb_sync()
        self.server.kb_update(id=card_id, content=_FULL_SLOTS + "\n\nedited on B")
        self.server.kb_sync()

        self.use_cards(a)
        self.server.kb_update(id=card_id, content=_FULL_SLOTS + "\n\nedited on A")
        card_path = self.server._find_card_by_id(card_id)
        before = card_path.read_text(encoding="utf-8")

        result = self.server.kb_sync()
        self.assertEqual(result["status"], "conflict", result)
        self.assertEqual(result["files"], [card_path.name])
        self.assertEqual(card_path.read_text(encoding="utf-8"), before)
        self.assertFalse((a / ".git" / "MERGE_HEAD").exists())
        self.assertEqual(git(a, "status", "--porcelain"), "")

    def test_push_failure_keeps_local_commits_and_retries(self):
        remote = self.make_remote()
        hook = remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        cards = self.make_clone("a", remote)
        self.use_cards(cards)
        self.save("Retry")

        failed = self.server.kb_sync()
        self.assertEqual(failed["status"], "push_failed", failed)
        self.assertEqual(git(cards, "rev-list", "--count", "HEAD"), "1")

        hook.unlink()
        retried = self.server.kb_sync()
        self.assertEqual(retried["status"], "ok", retried)
        self.assertEqual(retried["pushed"], 1)

    def test_unreachable_remote_reports_fetch_failed(self):
        cards = self.make_clone("a", self.tmp / "does-not-exist.git")
        self.use_cards(cards)
        self.save("Offline")
        result = self.server.kb_sync()
        self.assertEqual(result["status"], "fetch_failed", result)
        self.assertEqual(git(cards, "rev-list", "--count", "HEAD"), "1")

    def test_manual_edits_are_committed_before_sync(self):
        """在编辑器里手动改卡片，同步时会先提交再推送"""
        remote = self.make_remote()
        cards = self.make_clone("a", remote)
        self.use_cards(cards)
        path = Path(self.save("Manual")["path"])
        self.server.kb_sync()
        path.write_text(path.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")

        result = self.server.kb_sync()
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["committed_local"], 1)
        self.assertIn("hand edit", git(remote, "show", f"main:{path.name}"))

    def test_status_redacts_remote_credentials(self):
        cards = self.make_clone("a", self.make_remote())
        git(cards, "remote", "set-url", "origin", "https://user:FAKE_TOKEN_FOR_TEST@example.invalid/x.git")
        self.use_cards(cards)
        result = self.server.kb_sync(action="status")
        self.assertEqual(result["status"], "ready")
        self.assertNotIn("FAKE_TOKEN_FOR_TEST", str(result))

    def test_missing_remote(self):
        cards = self.tmp / "solo"
        cards.mkdir()
        git(cards, "init", "-q", "-b", "main")
        self.use_cards(cards)
        self.save("Solo")
        self.assertEqual(self.server.kb_sync()["status"], "no_remote")

    def test_invalid_action(self):
        with self.assertRaises(ValueError):
            self.server.kb_sync(action="push --force")


# ---------------------------------------------------------------------------
# 静态站点
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_MD, "需要 markdown-it-py（requirements-pro.txt）")
class TestBuildSite(_TempEnv):

    def setUp(self):
        super().setUp()
        import build_site
        self.bs = build_site
        self.cards = self.tmp / "cards"
        self.use_cards(self.cards, enabled=False)

    def build(self, out=None):
        out = out or self.tmp / "site"
        return self.bs.build_site(self.cards, out, "public", "测试站点"), out

    def all_output(self, out):
        return "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.html"))

    def test_only_tagged_cards_are_published(self):
        """默认不公开：没有 public 标签的卡片不会出现在任何输出文件里"""
        self.save("Open Card", tags=["public", "ai"])
        self.save("Secret Diary", extra="\n\nvery private", tags=["ai"])
        self.save("No Tags")
        stats, out = self.build()
        self.assertEqual((stats["published"], stats["skipped"]), (1, 2))
        html = self.all_output(out)
        self.assertIn("Open Card", html)
        self.assertNotIn("Secret Diary", html)
        self.assertNotIn("very private", html)
        self.assertTrue((out / "cards" / "general-open-card.html").exists())
        self.assertTrue((out / ".nojekyll").exists())

    def test_html_is_escaped(self):
        self.save("<script>alert(1)</script>",
                  extra="\n\n<img src=x onerror=alert(2)>\n\n[x](javascript:alert(3))",
                  tags=["public"])
        _, out = self.build()
        html = self.all_output(out)
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('href="javascript:', html)

    def test_rebuild_removes_unpublished_cards(self):
        card_id = self.save("Temp", tags=["public"])["id"]
        _, out = self.build()
        self.server.kb_update(id=card_id, tags=["private"])
        self.build(out)
        self.assertFalse((out / "cards" / f"{card_id}.html").exists())

    def test_refuses_foreign_non_empty_output(self):
        out = self.tmp / "important"
        out.mkdir()
        (out / "keep.txt").write_text("do not delete", encoding="utf-8")
        self.save("X", tags=["public"])
        with self.assertRaises(self.bs.SiteError):
            self.build(out)
        self.assertTrue((out / "keep.txt").exists())

    def test_refuses_output_containing_cards(self):
        self.save("Y", tags=["public"])
        with self.assertRaises(self.bs.SiteError):
            self.build(self.tmp)
        with self.assertRaises(self.bs.SiteError):
            self.build(self.cards)
        self.assertTrue(any(self.cards.glob("*.md")))

    def test_cli(self):
        self.save("Cli", tags=["public"])
        out = self.tmp / "cli-site"
        code = self.bs.main(["--cards", str(self.cards), "--out", str(out), "--tag", "public"])
        self.assertEqual(code, 0)
        self.assertTrue((out / "index.html").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
