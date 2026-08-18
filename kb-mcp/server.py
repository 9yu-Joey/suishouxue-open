# kb-mcp/server.py — 随手学 Knowledge Card MCP Server
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
随手学 MCP Server — 知识卡片的保存、搜索、读取、更新与引导

基于官方 MCP Python SDK v2 (MCPServer) 实现，通过 stdio 传输协议与
AI 客户端（Claude、ChatGPT 等）通信。

工具列表：
  kb_save   — 创建一张新知识卡片
  kb_get    — 按 id 读取完整卡片
  kb_update — 按 id 更新已有卡片
  kb_search — 按关键词搜索卡片
  kb_guide  — 加载 Profile 字段定义，引导 AI 生成卡片

要求 Python 3.10+
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml
from mcp.server import MCPServer

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CORE_SCHEMA_VERSION = "0.1"

# Profile 名称白名单正则：只允许小写字母、数字、连字符
_PROFILE_NAME_RE = re.compile(r"^[a-z][a-z0-9\-]{0,63}$")

# id 允许字符：小写字母、数字、连字符、CJK 等 Unicode 字符
# 与 _slugify() 产出一致：首字符为小写字母，后续为 Unicode 字母/数字/连字符
_CARD_ID_RE = re.compile(r"^[a-z][\w\-]{0,127}$", re.UNICODE)

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent  # kb-mcp/ 目录


def load_config() -> dict:
    """加载配置文件 config.yaml，如不存在则使用默认值。

    所有相对路径统一以 server.py 所在目录 (kb-mcp/) 为基准解析。
    环境变量可覆盖配置文件中的对应设置。
    """
    config_path = _BASE_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    else:
        config = {}

    # 默认值
    config.setdefault("cards_dir", "./cards")
    config.setdefault("profiles_dir", "../profiles")
    config.setdefault("default_profile", "general")

    # 环境变量覆盖
    if os.environ.get("SUISHOUXUE_CARDS_DIR"):
        config["cards_dir"] = os.environ["SUISHOUXUE_CARDS_DIR"]
    if os.environ.get("SUISHOUXUE_PROFILES_DIR"):
        config["profiles_dir"] = os.environ["SUISHOUXUE_PROFILES_DIR"]
    if os.environ.get("SUISHOUXUE_DEFAULT_PROFILE"):
        config["default_profile"] = os.environ["SUISHOUXUE_DEFAULT_PROFILE"]

    return config


def _resolve_path(raw: str) -> Path:
    """将配置中的路径解析为绝对路径（相对路径以 _BASE_DIR 为基准）。"""
    p = Path(raw)
    if p.is_absolute():
        return p
    return (_BASE_DIR / p).resolve()


CONFIG = load_config()
CARDS_DIR = _resolve_path(CONFIG["cards_dir"])
PROFILES_DIR = _resolve_path(CONFIG["profiles_dir"])
DEFAULT_PROFILE = CONFIG["default_profile"]


# ---------------------------------------------------------------------------
# Profile 辅助
# ---------------------------------------------------------------------------

def _validate_profile_name(name: str) -> None:
    """校验 Profile 名称：只允许安全字符集。"""
    if not _PROFILE_NAME_RE.match(name):
        raise ValueError(
            f"Profile 名称 '{name}' 不合法，只允许小写字母、数字和连字符，"
            f"且以字母开头（最长 64 字符）"
        )


def _safe_profile_path(name: str) -> Path:
    """返回安全的 Profile 文件路径，防止路径穿越。"""
    _validate_profile_name(name)
    path = (PROFILES_DIR / f"{name}.yaml").resolve()
    # 确保解析后仍在 PROFILES_DIR 内（使用 Path API 避免字符串前缀误判）
    if not path.is_relative_to(PROFILES_DIR.resolve()):
        raise ValueError(f"Profile 路径越界: {name}")
    return path


def _load_profile(name: str) -> dict:
    """加载并返回 Profile 数据，不存在则抛出 ValueError。"""
    path = _safe_profile_path(name)
    if not path.exists():
        available = [
            p.stem for p in PROFILES_DIR.glob("*.yaml")
        ] if PROFILES_DIR.exists() else []
        raise ValueError(
            f"Profile '{name}' 未找到。可用: {', '.join(available) or '无'}"
        )
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _list_profiles() -> list[str]:
    """列出所有可用的 Profile 名称。"""
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.yaml"))


# ---------------------------------------------------------------------------
# 卡片 ID 生成与冲突检测
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """将标题转为 URL-safe slug。"""
    # NFKD 分解后去掉音调符号
    text = unicodedata.normalize("NFKD", text)
    # 保留字母、数字、连字符、空格；中文字符保留
    out = []
    for ch in text:
        if ch.isalnum() or ch == "-":
            out.append(ch.lower())
        elif ch in (" ", "_"):
            out.append("-")
        # 中文等 CJK 字符直接保留
        elif "一" <= ch <= "鿿":
            out.append(ch)
    slug = "-".join(part for part in "".join(out).split("-") if part)
    return slug[:80] or "untitled"


def _generate_card_id(profile: str, title: str) -> str:
    """按 Core Schema 建议生成 id：profile-slug。"""
    slug = _slugify(title)
    return f"{profile}-{slug}"


def _find_card_by_id(card_id: str) -> Path | None:
    """在 CARDS_DIR 中查找指定 id 的卡片文件。"""
    if not CARDS_DIR.exists():
        return None
    for md_file in CARDS_DIR.glob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _parse_frontmatter(text)
        if fm and fm.get("id") == card_id:
            return md_file
    return None


def _parse_frontmatter(text: str) -> dict | None:
    """从 Markdown 文本中解析 YAML frontmatter。"""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def _parse_body(text: str) -> str:
    """提取 frontmatter 之后的正文。"""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")


def _collision_safe_filename(card_id: str) -> str:
    """生成防冲突文件名：timestamp-slug.md，同秒追加序号。"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_id = re.sub(r"[^\w\-]", "-", card_id)[:80]
    base = f"{timestamp}-{safe_id}"

    filepath = CARDS_DIR / f"{base}.md"
    if not filepath.exists():
        return f"{base}.md"

    # 同秒冲突：追加序号
    counter = 1
    while True:
        candidate = f"{base}-{counter}.md"
        if not (CARDS_DIR / candidate).exists():
            return candidate
        counter += 1
        if counter > 999:
            raise RuntimeError("文件名冲突过多，请稍后重试")


# ---------------------------------------------------------------------------
# MCP Server 实例
# ---------------------------------------------------------------------------

mcp = MCPServer(name="suishouxue-kb", version="0.1.0")


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------

@mcp.tool()
def kb_save(
    title: str,
    content: str,
    tags: list[str] | None = None,
    profile: str | None = None,
    category: str | None = None,
) -> dict:
    """保存一张新知识卡片为 Markdown 文件（含完整 YAML frontmatter）。

    服务端自动生成 id、schema_version、profile_version、created、updated。
    保存前会验证 Profile 是否存在，并检查 category 必填规则。

    Args:
        title:    卡片标题
        content:  卡片正文（Markdown 格式，应包含四个槽位）
        tags:     可选标签列表
        profile:  使用的 Profile 名称，缺省为 default_profile
        category: 所属分类（部分 Profile 要求必填）

    Returns:
        包含保存结果的字典：status, path, id
    """
    profile = profile or DEFAULT_PROFILE
    tags = tags or []

    # 验证 Profile 存在并读取其元信息
    profile_data = _load_profile(profile)
    profile_version = profile_data.get("version", "0.1")

    # 检查 category 必填规则
    if profile_data.get("category_required") and not category:
        available_categories = profile_data.get("categories", [])
        raise ValueError(
            f"Profile '{profile}' 要求必须指定 category。"
            f"可选值: {', '.join(available_categories)}"
        )

    # 如果提供了 category，验证它在 Profile 定义的列表中
    if category:
        valid_categories = profile_data.get("categories", [])
        if valid_categories and category not in valid_categories:
            raise ValueError(
                f"category '{category}' 不在 Profile '{profile}' "
                f"允许的分类中。可选值: {', '.join(valid_categories)}"
            )

    # 检查四槽位标题是否齐全（硬校验：缺失则拒绝保存）
    _SLOT_HEADERS = ["KNOW", "UNDERSTAND", "CONNECT", "VERIFY"]
    content_upper = content.upper()
    missing_slots = [
        s for s in _SLOT_HEADERS if f"## {s}" not in content_upper
    ]
    if missing_slots:
        raise ValueError(
            f"卡片正文缺少以下顶层槽位: {', '.join(missing_slots)}。"
            f"Core Schema 要求包含四个完整槽位 (## KNOW / ## UNDERSTAND / ## CONNECT / ## VERIFY)。"
        )

    # 生成唯一 id
    card_id = _generate_card_id(profile, title)

    # 检查 id 冲突
    existing = _find_card_by_id(card_id)
    if existing:
        raise ValueError(
            f"id '{card_id}' 已存在（文件: {existing.name}）。"
            f"如需更新，请使用 kb_update 工具。"
        )

    # 确保目标目录存在
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # 生成防冲突文件名
    filename = _collision_safe_filename(card_id)
    filepath = CARDS_DIR / filename

    now = datetime.now(timezone.utc).isoformat()

    # 构建完整 Metadata（符合 Core Schema v0.1）
    frontmatter: dict = {
        "id": card_id,
        "title": title,
        "profile": profile,
        "schema_version": CORE_SCHEMA_VERSION,
        "profile_version": profile_version,
        "created": now,
        "updated": now,
    }
    if category:
        frontmatter["category"] = category
    if tags:
        frontmatter["tags"] = tags

    # 写入文件
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write("---\n")
        yaml.dump(
            frontmatter,
            fh,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        fh.write("---\n\n")
        fh.write(content)
        if not content.endswith("\n"):
            fh.write("\n")

    return {"status": "saved", "path": str(filepath), "id": card_id}


@mcp.tool()
def kb_get(id: str) -> dict:
    """按 id 读取一张完整的知识卡片。

    Args:
        id: 卡片唯一标识符（如 ai-tech-embedding）

    Returns:
        包含完整卡片信息的字典：id, title, profile, metadata, content
    """
    if not _CARD_ID_RE.match(id):
        raise ValueError(f"id 格式不合法: {id}")

    card_path = _find_card_by_id(id)
    if card_path is None:
        raise ValueError(f"未找到 id 为 '{id}' 的卡片")

    text = card_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text) or {}
    body = _parse_body(text)

    return {
        "id": fm.get("id", id),
        "title": fm.get("title", ""),
        "profile": fm.get("profile", ""),
        "metadata": fm,
        "content": body,
        "file": card_path.name,
    }


@mcp.tool()
def kb_update(
    id: str,
    content: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
    title: str | None = None,
) -> dict:
    """按 id 更新已有知识卡片的内容或元信息。

    保留原始 created 时间，自动刷新 updated 时间。

    Args:
        id:       卡片唯一标识符
        content:  新的卡片正文（可选，不提供则保留原正文）
        tags:     新的标签列表（可选，不提供则保留原标签）
        category: 新的分类（可选，不提供则保留原分类）
        title:    新的标题（可选，不提供则保留原标题）

    Returns:
        包含更新结果的字典：status, path, id
    """
    if not _CARD_ID_RE.match(id):
        raise ValueError(f"id 格式不合法: {id}")

    card_path = _find_card_by_id(id)
    if card_path is None:
        raise ValueError(f"未找到 id 为 '{id}' 的卡片")

    text = card_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text) or {}
    old_body = _parse_body(text)

    # 更新字段
    if title is not None:
        fm["title"] = title
    if tags is not None:
        fm["tags"] = tags
    if category is not None:
        # 验证 category 合法性
        profile_name = fm.get("profile", DEFAULT_PROFILE)
        try:
            profile_data = _load_profile(profile_name)
        except ValueError:
            profile_data = None  # Profile 不存在时跳过分类校验

        if profile_data is not None:
            valid_categories = profile_data.get("categories", [])
            if valid_categories and category not in valid_categories:
                raise ValueError(
                    f"category '{category}' 不在 Profile '{profile_name}' "
                    f"允许的分类中。可选值: {', '.join(valid_categories)}"
                )

        fm["category"] = category

    # 刷新 updated 时间，保留 created
    fm["updated"] = datetime.now(timezone.utc).isoformat()

    new_body = content if content is not None else old_body

    # 如果更新了正文，校验四槽位
    if content is not None:
        _SLOT_HEADERS = ["KNOW", "UNDERSTAND", "CONNECT", "VERIFY"]
        content_upper = content.upper()
        missing_slots = [
            s for s in _SLOT_HEADERS if f"## {s}" not in content_upper
        ]
        if missing_slots:
            raise ValueError(
                f"更新内容缺少以下顶层槽位: {', '.join(missing_slots)}。"
                f"Core Schema 要求包含四个完整槽位 (## KNOW / ## UNDERSTAND / ## CONNECT / ## VERIFY)。"
            )

    # 写回文件
    with open(card_path, "w", encoding="utf-8") as fh:
        fh.write("---\n")
        yaml.dump(
            fm,
            fh,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        fh.write("---\n\n")
        fh.write(new_body)
        if not new_body.endswith("\n"):
            fh.write("\n")

    return {"status": "updated", "path": str(card_path), "id": id}


@mcp.tool()
def kb_search(query: str, limit: int = 10) -> dict:
    """按关键词搜索已有知识卡片（简单文本匹配，不区分大小写）。

    返回匹配卡片的 id、title、profile 和命中附近的摘要。
    完整内容请通过 kb_get 读取。

    Args:
        query: 搜索关键词
        limit: 返回结果数量上限，默认 10

    Returns:
        包含匹配结果列表的字典：results, total
    """
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    results = []
    query_lower = query.lower()

    if not CARDS_DIR.exists():
        return {"results": [], "total": 0, "message": "卡片目录尚未创建"}

    for md_file in sorted(CARDS_DIR.glob("*.md"), reverse=True):
        if len(results) >= limit:
            break
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        text_lower = text.lower()
        if query_lower not in text_lower:
            continue

        fm = _parse_frontmatter(text) or {}
        body = _parse_body(text)

        # 生成命中附近的摘要
        snippet = _context_snippet(body, query, window=80)

        results.append({
            "id": fm.get("id", md_file.stem),
            "title": fm.get("title", md_file.stem),
            "profile": fm.get("profile", ""),
            "file": md_file.name,
            "snippet": snippet,
        })

    return {"results": results, "total": len(results)}


def _context_snippet(text: str, query: str, window: int = 80) -> str:
    """从文本中提取查询词附近的上下文片段。"""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:160].strip()

    start = max(0, idx - window)
    end = min(len(text), idx + len(query) + window)

    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


@mcp.tool()
def kb_guide(profile: str | None = None) -> dict:
    """加载 Profile YAML 并返回字段定义，引导 AI 按模板生成知识卡片。

    返回 Profile 的完整定义，包括四个槽位的字段、分类列表、
    AI 指令等，供 AI 客户端据此生成结构化的卡片内容。

    Args:
        profile: Profile 名称，缺省使用 default_profile

    Returns:
        包含 Profile 字段定义和可用 Profile 列表的字典。
    """
    profile = profile or DEFAULT_PROFILE
    profile_data = _load_profile(profile)

    return {
        "profile": profile,
        "fields": profile_data,
        "available_profiles": _list_profiles(),
        "schema_version": CORE_SCHEMA_VERSION,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
