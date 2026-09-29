#!/usr/bin/env python3
"""
随手学 Open — 配置加载测试：.env 文件与优先级

Copyright (C) 2026 九聿 (Joey)
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "kb-mcp"))

import kbcore  # noqa: E402

KB_MCP = Path(__file__).parent.parent / "kb-mcp"


class _EnvIsolation(unittest.TestCase):
    """每个测试前后恢复 SUISHOUXUE_* 等环境变量，并使用临时目录。"""

    watched = ("HTTP_PROXY", "PATH", "suishouxue_lower")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._saved = {k: v for k, v in os.environ.items()
                       if k.startswith("SUISHOUXUE_") or k in self.watched}
        for key in list(os.environ):
            if key.startswith("SUISHOUXUE_"):
                del os.environ[key]

    def tearDown(self):
        for key in list(os.environ):
            if key.startswith("SUISHOUXUE_") or key in self.watched:
                del os.environ[key]
        os.environ.update(self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_env(self, text):
        path = self.tmp / ".env"
        path.write_text(text, encoding="utf-8")
        return path


class TestLoadDotenv(_EnvIsolation):

    def test_parses_common_forms(self):
        path = self.write_env(
            "# 注释\n"
            "\n"
            "SUISHOUXUE_CARDS_DIR=/data/cards\n"
            "export SUISHOUXUE_DEFAULT_PROFILE=ai-tech\n"
            'SUISHOUXUE_SYNC_REMOTE="upstream"\n'
            "SUISHOUXUE_SYNC_BRANCH='notes' \n"
            "SUISHOUXUE_PUBLISH_TAG=公开 # 行尾注释\n"
            "SUISHOUXUE_ALLOWED_HOSTS = a.example.com,b.example.com\n"
        )
        applied = kbcore.load_dotenv(path)
        self.assertEqual(os.environ["SUISHOUXUE_CARDS_DIR"], "/data/cards")
        self.assertEqual(os.environ["SUISHOUXUE_DEFAULT_PROFILE"], "ai-tech")
        self.assertEqual(os.environ["SUISHOUXUE_SYNC_REMOTE"], "upstream")
        self.assertEqual(os.environ["SUISHOUXUE_SYNC_BRANCH"], "notes")
        self.assertEqual(os.environ["SUISHOUXUE_PUBLISH_TAG"], "公开")
        self.assertEqual(os.environ["SUISHOUXUE_ALLOWED_HOSTS"], "a.example.com,b.example.com")
        self.assertEqual(len(applied), 6)

    def test_only_suishouxue_variables_are_read(self):
        """.env 不能改动代理、PATH 等影响本程序或 git 的变量"""
        original_path = os.environ.get("PATH")
        os.environ.pop("HTTP_PROXY", None)
        path = self.write_env(
            "HTTP_PROXY=http://evil.example:8080\n"
            "PATH=/tmp/evil\n"
            "suishouxue_lower=x\n"
            "SUISHOUXUE_CARDS_DIR=./cards\n"
        )
        self.assertEqual(kbcore.load_dotenv(path), ["SUISHOUXUE_CARDS_DIR"])
        self.assertNotIn("HTTP_PROXY", os.environ)
        self.assertEqual(os.environ.get("PATH"), original_path)
        self.assertNotIn("suishouxue_lower", os.environ)

    def test_existing_environment_wins(self):
        os.environ["SUISHOUXUE_CARDS_DIR"] = "/from/mcp/client"
        path = self.write_env("SUISHOUXUE_CARDS_DIR=/from/dotenv\n")
        self.assertEqual(kbcore.load_dotenv(path), [])
        self.assertEqual(os.environ["SUISHOUXUE_CARDS_DIR"], "/from/mcp/client")

    def test_missing_file_is_fine(self):
        self.assertEqual(kbcore.load_dotenv(self.tmp / "nope.env"), [])

    def test_copied_example_changes_nothing(self):
        """照 README 执行 cp .env.example .env 后，不会悄悄覆盖 config.yaml"""
        path = self.tmp / ".env"
        shutil.copy(KB_MCP / ".env.example", path)
        self.assertEqual(kbcore.load_dotenv(path), [])
        self.assertFalse(any(k.startswith("SUISHOUXUE_") for k in os.environ))


class TestConfigPrecedence(_EnvIsolation):
    """系统环境变量 > .env > config.yaml > 默认值"""

    def setUp(self):
        super().setUp()
        self._base = kbcore.BASE_DIR
        kbcore.BASE_DIR = self.tmp

    def tearDown(self):
        kbcore.BASE_DIR = self._base
        super().tearDown()

    def test_precedence(self):
        (self.tmp / "config.yaml").write_text(
            'cards_dir: "/from/config"\n'
            'default_profile: "language"\n'
            "sync:\n  enabled: true\n",
            encoding="utf-8",
        )
        self.write_env(
            "SUISHOUXUE_CARDS_DIR=/from/dotenv\n"
            "SUISHOUXUE_SYNC_ENABLED=false\n"
            "SUISHOUXUE_PROFILES_DIR=/from/dotenv/profiles\n"
        )
        os.environ["SUISHOUXUE_PROFILES_DIR"] = "/from/env"

        config = kbcore.load_config()
        self.assertEqual(config["cards_dir"], "/from/dotenv")          # .env > config.yaml
        self.assertIs(config["sync"]["enabled"], False)                 # .env > config.yaml
        self.assertEqual(config["profiles_dir"], "/from/env")          # 环境变量 > .env
        self.assertEqual(config["default_profile"], "language")        # 仅 config.yaml
        self.assertEqual(config["http"]["host"], "127.0.0.1")          # 默认值

    def test_invalid_bool_in_dotenv_is_rejected(self):
        self.write_env("SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND=sure\n")
        with self.assertRaises(ValueError):
            kbcore.load_config()


if __name__ == "__main__":
    unittest.main(verbosity=2)
