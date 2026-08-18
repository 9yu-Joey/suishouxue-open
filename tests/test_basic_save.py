#!/usr/bin/env python3
"""
随手学 Open — 基础保存测试

测试 kb-mcp 的核心功能：卡片保存、读取、搜索、更新。
测试直接调用 server.py 的工具函数，验证落盘文件符合 Core Schema。

Copyright (C) 2026 九聿 (Joey)
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

# 把 kb-mcp 目录加入路径
sys.path.insert(0, str(Path(__file__).parent.parent / "kb-mcp"))

# 四槽位完整内容模板（所有 kb_save 测试必须使用）
_FULL_SLOTS = "## KNOW\n\ntest\n\n## UNDERSTAND\n\ntest\n\n## CONNECT\n\ntest\n\n## VERIFY\n\ntest"


def _slots_with(extra: str) -> str:
    """在四槽位模板末尾追加自定义内容。"""
    return _FULL_SLOTS + "\n\n" + extra


class TestKbSave(unittest.TestCase):
    """测试 kb_save 工具函数"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # 动态 patch CARDS_DIR
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_returns_status_and_id(self):
        """kb_save 返回 status=saved, path, id"""
        import server
        result = server.kb_save(
            title="Test Concept",
            content=_FULL_SLOTS,
            profile="general",
        )
        self.assertEqual(result["status"], "saved")
        self.assertIn("id", result)
        self.assertIn("path", result)
        self.assertTrue(Path(result["path"]).exists())

    def test_save_creates_complete_metadata(self):
        """kb_save 生成的文件包含 Core Schema 要求的全部必填 Metadata"""
        import server
        result = server.kb_save(
            title="Metadata Test",
            content=_FULL_SLOTS,
            tags=["测试"],
            profile="general",
        )
        raw = Path(result["path"]).read_text(encoding="utf-8")
        fm = yaml.safe_load(raw.split("---", 2)[1])

        required = ["id", "title", "profile", "schema_version",
                     "profile_version", "created", "updated"]
        for field in required:
            self.assertIn(field, fm, f"缺少必填 Metadata 字段: {field}")

        self.assertEqual(fm["schema_version"], "0.1")
        self.assertEqual(fm["profile_version"], "0.1")
        self.assertEqual(fm["profile"], "general")
        self.assertEqual(fm["tags"], ["测试"])

    def test_save_validates_profile_exists(self):
        """kb_save 对不存在的 Profile 应抛出 ValueError"""
        import server
        with self.assertRaises(ValueError) as ctx:
            server.kb_save(
                title="Bad",
                content=_FULL_SLOTS,
                profile="nonexistent",
            )
        self.assertIn("未找到", str(ctx.exception))

    def test_save_validates_category_required(self):
        """ai-tech Profile 要求 category 必填"""
        import server
        with self.assertRaises(ValueError) as ctx:
            server.kb_save(
                title="No Category",
                content=_FULL_SLOTS,
                profile="ai-tech",
            )
        self.assertIn("category", str(ctx.exception))

    def test_save_validates_category_value(self):
        """category 必须在 Profile 定义的列表中"""
        import server
        with self.assertRaises(ValueError):
            server.kb_save(
                title="Bad Category",
                content=_FULL_SLOTS,
                profile="ai-tech",
                category="不存在的分类",
            )

    def test_save_with_valid_category(self):
        """ai-tech Profile + 合法 category 应成功"""
        import server
        result = server.kb_save(
            title="With Category",
            content=_FULL_SLOTS,
            profile="ai-tech",
            category="AI与数据科学",
        )
        self.assertEqual(result["status"], "saved")
        raw = Path(result["path"]).read_text(encoding="utf-8")
        fm = yaml.safe_load(raw.split("---", 2)[1])
        self.assertEqual(fm["category"], "AI与数据科学")

    def test_save_blocks_duplicate_id(self):
        """同一 profile+title 第二次保存应被拒绝"""
        import server
        server.kb_save(title="Duplicate", content=_FULL_SLOTS, profile="general")
        with self.assertRaises(ValueError) as ctx:
            server.kb_save(title="Duplicate", content=_FULL_SLOTS, profile="general")
        self.assertIn("已存在", str(ctx.exception))

    def test_same_second_no_overwrite(self):
        """同秒不同标题不应覆盖"""
        import server
        r1 = server.kb_save(title="Alpha", content=_FULL_SLOTS, profile="general")
        r2 = server.kb_save(title="Beta", content=_FULL_SLOTS, profile="general")
        self.assertNotEqual(r1["path"], r2["path"])
        self.assertTrue(Path(r1["path"]).exists())
        self.assertTrue(Path(r2["path"]).exists())


class TestKbGet(unittest.TestCase):
    """测试 kb_get 工具函数"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_returns_full_card(self):
        """kb_get 返回完整卡片信息"""
        import server
        saved = server.kb_save(title="Get Test", content=_slots_with("body text"), profile="general")
        card = server.kb_get(saved["id"])
        self.assertEqual(card["id"], saved["id"])
        self.assertEqual(card["title"], "Get Test")
        self.assertIn("body text", card["content"])

    def test_get_nonexistent_raises(self):
        """kb_get 对不存在的 id 应抛出 ValueError"""
        import server
        with self.assertRaises(ValueError):
            server.kb_get("general-does-not-exist")


class TestKbUpdate(unittest.TestCase):
    """测试 kb_update 工具函数"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_update_preserves_created(self):
        """kb_update 保留 created 时间"""
        import server
        saved = server.kb_save(title="Update Test", content=_FULL_SLOTS, profile="general")
        card_before = server.kb_get(saved["id"])

        updated_content = _slots_with("v2 new content")
        server.kb_update(id=saved["id"], content=updated_content)
        card_after = server.kb_get(saved["id"])

        self.assertEqual(card_after["metadata"]["created"],
                         card_before["metadata"]["created"])
        self.assertNotEqual(card_after["metadata"]["updated"],
                            card_before["metadata"]["updated"])
        self.assertIn("v2 new content", card_after["content"])

    def test_update_nonexistent_raises(self):
        """kb_update 对不存在的 id 应抛出 ValueError"""
        import server
        with self.assertRaises(ValueError):
            server.kb_update(id="general-nonexistent", content="new")


class TestKbSearch(unittest.TestCase):
    """测试 kb_search 工具函数"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_search_returns_id_and_profile(self):
        """kb_search 结果包含 id, title, profile"""
        import server
        server.kb_save(title="Search Test", content=_slots_with("hello world"), profile="general")
        result = server.kb_search(query="hello")
        self.assertEqual(result["total"], 1)
        r = result["results"][0]
        self.assertIn("id", r)
        self.assertIn("title", r)
        self.assertIn("profile", r)
        self.assertIn("snippet", r)

    def test_search_context_snippet(self):
        """kb_search 返回命中附近的上下文，不是前200字符"""
        import server
        long_content = _FULL_SLOTS + "\n\n" + "A" * 500 + " FINDME " + "B" * 500
        server.kb_save(title="Snippet Test", content=long_content, profile="general")
        result = server.kb_search(query="FINDME")
        snippet = result["results"][0]["snippet"]
        self.assertIn("FINDME", snippet)
        self.assertLess(len(snippet), 300)

    def test_search_empty_dir(self):
        """空目录搜索不报错"""
        import server
        result = server.kb_search(query="anything")
        self.assertEqual(result["total"], 0)

    def test_search_limit(self):
        """limit 参数正常工作"""
        import server
        for i in range(5):
            server.kb_save(title=f"Item {i}", content=_slots_with(f"common keyword {i}"), profile="general")
        result = server.kb_search(query="common", limit=3)
        self.assertLessEqual(result["total"], 3)


class TestKbGuide(unittest.TestCase):
    """测试 kb_guide 工具函数"""

    def setUp(self):
        pass

    def test_guide_returns_profile_and_schema_version(self):
        """kb_guide 返回 profile, fields, schema_version, available_profiles"""
        import server
        result = server.kb_guide(profile="general")
        self.assertEqual(result["profile"], "general")
        self.assertIn("fields", result)
        self.assertIn("schema_version", result)
        self.assertIn("available_profiles", result)
        self.assertIn("general", result["available_profiles"])

    def test_guide_invalid_profile_raises(self):
        """kb_guide 对不存在的 Profile 应抛出 ValueError"""
        import server
        with self.assertRaises(ValueError):
            server.kb_guide(profile="nonexistent")


class TestPathTraversal(unittest.TestCase):
    """安全测试：路径穿越防护"""

    def test_profile_path_traversal_blocked(self):
        """Profile 名含 ../ 应被拒绝"""
        import server
        with self.assertRaises(ValueError):
            server._validate_profile_name("../../../etc/passwd")

    def test_profile_name_whitelist(self):
        """只接受合法 Profile 名"""
        import server
        # 合法
        server._validate_profile_name("general")
        server._validate_profile_name("ai-tech")
        server._validate_profile_name("language")

        # 非法
        for bad in ["UPPER", "has space", "has.dot", "../evil", "", "a" * 100]:
            with self.assertRaises(ValueError, msg=f"应拒绝: {bad}"):
                server._validate_profile_name(bad)


class TestProfileFormat(unittest.TestCase):
    """测试 Profile YAML 的格式正确性"""

    def test_profiles_exist(self):
        """v1 必须包含三个内置 Profile"""
        profiles_dir = Path(__file__).parent.parent / "profiles"
        expected = ["general.yaml", "ai-tech.yaml", "language.yaml"]
        for filename in expected:
            filepath = profiles_dir / filename
            self.assertTrue(filepath.exists(), f"缺少 Profile 文件: {filename}")

    def test_profile_has_required_fields(self):
        """每个 Profile 必须包含必要的元信息和四个槽位"""
        profiles_dir = Path(__file__).parent.parent / "profiles"
        required_meta = ["name", "display_name", "description",
                         "version", "min_schema_version"]
        required_slots = ["know", "understand", "connect", "verify"]

        for yaml_file in profiles_dir.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                profile = yaml.safe_load(f)

            for field in required_meta:
                self.assertIn(field, profile,
                              f"{yaml_file.name} 缺少必填字段: {field}")

            self.assertIn("slots", profile,
                          f"{yaml_file.name} 缺少 slots 定义")
            for slot in required_slots:
                self.assertIn(slot, profile["slots"],
                              f"{yaml_file.name} 缺少槽位: {slot}")

                fields = profile["slots"][slot].get("fields", [])
                self.assertGreater(len(fields), 0,
                                   f"{yaml_file.name} 的 {slot} 槽位没有定义字段")


class TestExampleCards(unittest.TestCase):
    """测试示例卡片的完整性"""

    def test_examples_exist(self):
        """v1 必须包含两张示例卡片"""
        examples_dir = Path(__file__).parent.parent / "examples"
        expected = ["embedding.md", "apple.md"]
        for filename in expected:
            filepath = examples_dir / filename
            self.assertTrue(filepath.exists(), f"缺少示例卡片: {filename}")

    def test_examples_have_complete_metadata(self):
        """示例卡片必须包含完整 Metadata"""
        examples_dir = Path(__file__).parent.parent / "examples"
        required = ["id", "title", "profile", "schema_version",
                     "profile_version", "created", "updated"]

        for md_file in examples_dir.glob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            self.assertGreaterEqual(len(parts), 3,
                                    f"{md_file.name} 缺少 frontmatter")
            fm = yaml.safe_load(parts[1])
            for field in required:
                self.assertIn(field, fm,
                              f"{md_file.name} 缺少 Metadata 字段: {field}")

    def test_examples_match_profiles(self):
        """示例卡片的 profile 字段必须对应一个已有的 Profile"""
        examples_dir = Path(__file__).parent.parent / "examples"
        profiles_dir = Path(__file__).parent.parent / "profiles"

        available_profiles = set()
        for yaml_file in profiles_dir.glob("*.yaml"):
            with open(yaml_file, "r", encoding="utf-8") as f:
                profile = yaml.safe_load(f)
                available_profiles.add(profile.get("name", ""))

        for md_file in examples_dir.glob("*.md"):
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1])
                if fm and "profile" in fm:
                    self.assertIn(fm["profile"], available_profiles,
                                  f"{md_file.name} 引用了不存在的 Profile: {fm['profile']}")


class TestSecurityCheck(unittest.TestCase):
    """安全检查：确保仓库中没有真实凭证"""

    def test_no_real_tokens(self):
        """所有配置文件只能包含示例值，不能有真实 token"""
        repo_root = Path(__file__).parent.parent
        sensitive_patterns = [
            "ghp_",      # GitHub Personal Access Token
            "sk-",       # OpenAI API Key
            "Bearer ",   # Auth header with real token
        ]

        config_files = list(repo_root.rglob("*.example.*"))
        config_files += list(repo_root.rglob(".env*"))
        config_files += list(repo_root.rglob("config*.yaml"))
        config_files += list(repo_root.rglob("config*.yml"))

        for config_file in config_files:
            if not config_file.is_file():
                continue
            with open(config_file, "r", encoding="utf-8") as f:
                content = f.read()
            for pattern in sensitive_patterns:
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    if pattern in line:
                        after = line.split(pattern, 1)[1]
                        is_placeholder = any(word in after.lower()
                                             for word in ["xxxx", "your_", "example",
                                                          "placeholder", "这里填"])
                        self.assertTrue(
                            is_placeholder or "#" in line.split(pattern)[0],
                            f"⚠️ 疑似真实凭证！文件 {config_file.name} 第 {i} 行包含 '{pattern}'"
                        )


class TestR1ChineseId(unittest.TestCase):
    """R1 回归：中文标题生成的卡片可正常保存、读取、更新、搜索"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_chinese_roundtrip(self):
        """中文标题：save → get → update → search 完整往返"""
        import server
        content = "## KNOW\n\n嵌入向量\n\n## UNDERSTAND\n\ntest\n\n## CONNECT\n\ntest\n\n## VERIFY\n\ntest"
        saved = server.kb_save(title="嵌入向量", content=content, profile="general")
        self.assertEqual(saved["status"], "saved")
        self.assertIn("嵌入向量", saved["id"])

        card = server.kb_get(saved["id"])
        self.assertEqual(card["title"], "嵌入向量")

        server.kb_update(id=saved["id"], content=content + "\n\n追加内容")
        updated = server.kb_get(saved["id"])
        self.assertIn("追加内容", updated["content"])

        found = server.kb_search(query="嵌入向量")
        self.assertGreaterEqual(found["total"], 1)


class TestR2SlotValidation(unittest.TestCase):
    """R2 回归：保存时检查四槽位标题"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_slots_saves(self):
        """四槽位齐全时正常保存"""
        import server
        result = server.kb_save(
            title="Complete Card",
            content=_FULL_SLOTS,
            profile="general",
        )
        self.assertEqual(result["status"], "saved")

    def test_missing_slots_rejects(self):
        """缺少槽位时拒绝保存"""
        import server
        with self.assertRaises(ValueError) as ctx:
            server.kb_save(
                title="Incomplete Card",
                content="## KNOW\n\nonly know",
                profile="general",
            )
        self.assertIn("UNDERSTAND", str(ctx.exception))
        self.assertIn("CONNECT", str(ctx.exception))
        self.assertIn("VERIFY", str(ctx.exception))

    def test_update_rejects_missing_slots(self):
        """kb_update 更新内容时也拒绝缺槽"""
        import server
        saved = server.kb_save(
            title="Slot Update Test",
            content=_FULL_SLOTS,
            profile="general",
        )
        with self.assertRaises(ValueError) as ctx:
            server.kb_update(id=saved["id"], content="## KNOW\n\nonly know")
        self.assertIn("UNDERSTAND", str(ctx.exception))


class TestR3UpdateCategoryValidation(unittest.TestCase):
    """R3 回归：kb_update 中 category 验证不被吞掉"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        import server
        self._orig_cards_dir = server.CARDS_DIR
        server.CARDS_DIR = Path(self.test_dir) / "cards"

    def tearDown(self):
        import server
        server.CARDS_DIR = self._orig_cards_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_update_rejects_invalid_category(self):
        """kb_update 传入非法 category 应抛出 ValueError"""
        import server
        saved = server.kb_save(
            title="Cat Test",
            content=_FULL_SLOTS,
            profile="ai-tech",
            category="AI与数据科学",
        )
        with self.assertRaises(ValueError) as ctx:
            server.kb_update(id=saved["id"], category="不存在的分类")
        self.assertIn("不在", str(ctx.exception))


class TestR4SymlinkBypass(unittest.TestCase):
    """R4 回归：_safe_profile_path 使用 is_relative_to 而非 startswith"""

    def test_safe_profile_path_uses_is_relative_to(self):
        """确认 _safe_profile_path 内部不使用字符串 startswith"""
        import server
        import inspect
        source = inspect.getsource(server._safe_profile_path)
        self.assertNotIn("startswith", source,
                         "_safe_profile_path 应使用 is_relative_to 而非 startswith")
        self.assertIn("is_relative_to", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
