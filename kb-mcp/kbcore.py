# kb-mcp/kbcore.py — 随手学共享基础：配置加载与卡片文件解析
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
server.py 与 build_site.py 共用的基础逻辑。

本模块只依赖 PyYAML，不依赖 mcp，这样静态站点生成器可以在
GitHub Actions 等只装了最少依赖的环境里独立运行。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent  # kb-mcp/ 目录

# id 允许字符：与 server._slugify() 产出一致
CARD_ID_RE = re.compile(r"^[a-z][\w\-]{0,127}$", re.UNICODE)

# Git remote / 分支名白名单：禁止以 "-" 开头，防止被 git 当作命令行选项
_REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")
_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,127}$")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def strict_bool(value, name: str) -> bool:
    """严格解析布尔开关。

    YAML 里带引号的 "false" 是字符串，bool("false") 会得到 True；
    安全开关不能这样放行，所以无法识别的值一律报错。
    """
    if value is None:  # YAML 中留空：按关闭处理
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in _TRUE_VALUES | _FALSE_VALUES:
        return value.strip().lower() in _TRUE_VALUES
    raise ValueError(f"{name} 必须是 true 或 false")


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return strict_bool(raw, name)


def load_config() -> dict:
    """加载配置文件 config.yaml，如不存在则使用默认值。

    所有相对路径统一以 kb-mcp/ 目录为基准解析。
    环境变量可覆盖配置文件中的对应设置。
    """
    config_path = BASE_DIR / "config.yaml"
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

    config["sync"] = _load_sync_config(config.get("sync"))
    config["site"] = _load_site_config(config.get("site"))
    config["http"] = _load_http_config(config.get("http"))
    return config


def _load_sync_config(raw) -> dict:
    """Pro：Git 同步设置。默认关闭，关闭时行为与 Lite 完全一致。"""
    sync = dict(raw) if isinstance(raw, dict) else {}
    sync["enabled"] = strict_bool(sync.get("enabled", False), "sync.enabled")
    sync["remote"] = str(sync.get("remote") or "origin")
    sync["branch"] = str(sync.get("branch") or "main")

    env_enabled = _env_bool("SUISHOUXUE_SYNC_ENABLED")
    if env_enabled is not None:
        sync["enabled"] = env_enabled
    if os.environ.get("SUISHOUXUE_SYNC_REMOTE"):
        sync["remote"] = os.environ["SUISHOUXUE_SYNC_REMOTE"]
    if os.environ.get("SUISHOUXUE_SYNC_BRANCH"):
        sync["branch"] = os.environ["SUISHOUXUE_SYNC_BRANCH"]

    validate_sync_names(sync["remote"], sync["branch"])
    return sync


def validate_sync_names(remote: str, branch: str) -> None:
    """remote 必须是 remote 名称（如 origin），不接受 URL；分支名不得含 ".."。"""
    # 错误信息不回显原值：用户可能误把带 token 的 URL 填了进来
    if not _REMOTE_NAME_RE.match(remote):
        raise ValueError(
            "sync.remote 不合法：请填写 Git remote 名称（如 origin），"
            "不要填写 URL，更不要把 token 写进配置"
        )
    if not _BRANCH_NAME_RE.match(branch) or ".." in branch:
        raise ValueError(
            "sync.branch 不合法：只允许字母、数字和 . _ / -，不能以 - 开头，不能包含 .."
        )


def _load_site_config(raw) -> dict:
    """Pro：静态站点设置。"""
    site = dict(raw) if isinstance(raw, dict) else {}
    site["publish_tag"] = str(site.get("publish_tag") or "public")
    site["title"] = str(site.get("title") or "我的随手学知识库")
    site["output_dir"] = str(site.get("output_dir") or "./site")
    if os.environ.get("SUISHOUXUE_PUBLISH_TAG"):
        site["publish_tag"] = os.environ["SUISHOUXUE_PUBLISH_TAG"]
    return site


def _load_http_config(raw) -> dict:
    """Private：HTTP 传输设置。只在 --transport http 时使用。"""
    http = dict(raw) if isinstance(raw, dict) else {}
    http["host"] = str(http.get("host") or "127.0.0.1")
    http["port"] = int(http.get("port") or 8765)
    http["tokens_file"] = str(http.get("tokens_file") or "./tokens.json")
    http["allow_remote_bind"] = strict_bool(
        http.get("allow_remote_bind", False), "http.allow_remote_bind"
    )
    hosts = http.get("allowed_hosts") or []
    http["allowed_hosts"] = [str(h) for h in hosts] if isinstance(hosts, list) else []

    if os.environ.get("SUISHOUXUE_HTTP_HOST"):
        http["host"] = os.environ["SUISHOUXUE_HTTP_HOST"]
    if os.environ.get("SUISHOUXUE_HTTP_PORT"):
        http["port"] = int(os.environ["SUISHOUXUE_HTTP_PORT"])
    if os.environ.get("SUISHOUXUE_TOKENS_FILE"):
        http["tokens_file"] = os.environ["SUISHOUXUE_TOKENS_FILE"]
    env_remote = _env_bool("SUISHOUXUE_HTTP_ALLOW_REMOTE_BIND")
    if env_remote is not None:
        http["allow_remote_bind"] = env_remote
    if os.environ.get("SUISHOUXUE_ALLOWED_HOSTS"):
        http["allowed_hosts"] = [
            h.strip() for h in os.environ["SUISHOUXUE_ALLOWED_HOSTS"].split(",") if h.strip()
        ]
    return http


def resolve_path(raw: str) -> Path:
    """将配置中的路径解析为绝对路径（相对路径以 BASE_DIR 为基准）。"""
    p = Path(raw)
    if p.is_absolute():
        return p
    return (BASE_DIR / p).resolve()


# ---------------------------------------------------------------------------
# 卡片文件解析
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict | None:
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


def parse_body(text: str) -> str:
    """提取 frontmatter 之后的正文。"""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return text
    return parts[2].lstrip("\n")
