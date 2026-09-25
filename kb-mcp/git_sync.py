# kb-mcp/git_sync.py — 随手学 Pro：卡片目录的可选 Git 同步
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
Pro 同步层：把卡片目录当作一个独立的 Git 仓库来管理。

设计约定（不能静默丢失或覆盖知识卡）：
  - 本地提交：kb_save / kb_update 成功后只做本地 commit，不联网。
    提交失败只返回 warning，绝不让保存本身失败。
  - 同步：只有显式调用 kb_sync 才联网，顺序是 fetch → merge → push。
  - 冲突：merge 出现冲突立即 abort，本地卡片保持合并前的样子，并列出冲突文件。
  - push 失败：本地 commit 保留，下次 kb_sync 重试。永远不 force push。
  - 凭据：本模块不读取、不保存任何 token。认证完全交给用户自己的
    Git 配置（SSH key 或 credential helper）。

只使用系统 git 命令，不引入额外 Python 依赖。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

LOCAL_TIMEOUT = 30
NETWORK_TIMEOUT = 120


class GitError(RuntimeError):
    """git 命令执行失败。"""


def _git(
    repo: Path,
    *args: str,
    timeout: int = LOCAL_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # MCP 走 stdio：git 绝不能停下来等密码输入，否则会卡死整个服务
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL,  # 不能继承 MCP 的 stdin
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise GitError("未找到 git 命令，请先安装 Git") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} 超时（{timeout} 秒）") from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise GitError(f"git {args[0]} 失败: {redact(detail)}")
    return proc


def redact(text: str) -> str:
    """去掉 URL 中的用户名/密码，防止 token 出现在返回给 AI 的内容里。"""
    return re.sub(r"(\w+://)[^/@\s]+@", r"\1***@", text)


def is_repo(cards_dir: Path) -> bool:
    """卡片目录本身必须是 Git 仓库的根目录。

    只在某个上级仓库里面（例如默认的 suishouxue-open/kb-mcp/cards）不算，
    否则卡片会被提交进项目仓库。
    """
    if not cards_dir.is_dir():
        return False
    try:
        proc = _git(cards_dir, "rev-parse", "--show-toplevel", check=False)
    except GitError:
        return False
    if proc.returncode != 0:
        return False
    return Path(proc.stdout.strip()).resolve() == cards_dir.resolve()


def _has_head(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", "HEAD", check=False).returncode == 0


def _short_head(repo: Path) -> str:
    return _git(repo, "rev-parse", "--short", "HEAD").stdout.strip()


def _commit(repo: Path, rel_paths: list[str], message: str) -> str | None:
    """只提交指定文件；没有实际变化时返回 None。"""
    _git(repo, "add", "--", *rel_paths)
    staged = _git(repo, "diff", "--cached", "--quiet", "--", *rel_paths, check=False)
    if staged.returncode == 0:
        return None
    _git(repo, "commit", "--quiet", "-m", message, "--", *rel_paths)
    return _short_head(repo)


def record_change(cards_dir: Path, card_path: Path, message: str) -> dict:
    """kb_save / kb_update 之后的本地提交。永不抛异常。"""
    if not is_repo(cards_dir):
        return {
            "committed": False,
            "warning": "卡片目录不是独立的 Git 仓库，本次只保存在本地文件。"
                       "请参考 docs/05-Pro-同步与展示.md 初始化。",
        }
    try:
        rel = card_path.resolve().relative_to(cards_dir.resolve()).as_posix()
        sha = _commit(cards_dir, [rel], message)
    except (GitError, ValueError) as exc:
        return {"committed": False, "warning": f"卡片已保存，但本地提交失败: {exc}"}
    if sha is None:
        return {"committed": False, "warning": "内容无变化，未产生提交"}
    return {"committed": True, "commit": sha}


def _pending_card_files(repo: Path) -> list[str]:
    """卡片目录顶层有改动（含新文件）的 .md 卡片。"""
    out = _git(repo, "status", "--porcelain", "-z", "--untracked-files=all").stdout
    files = []
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in "RC":  # 重命名条目后面紧跟原路径
            i += 1
        if "/" not in path and path.endswith(".md") and code != "!!":
            files.append(path)
    return files


def _tracked_dirty(repo: Path) -> list[str]:
    out = _git(repo, "status", "--porcelain", "--untracked-files=no").stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def status(cards_dir: Path, remote: str, branch: str) -> dict:
    """本地状态，不联网。"""
    if not is_repo(cards_dir):
        return {"status": "not_repo", "cards_dir": str(cards_dir),
                "message": "卡片目录不是独立的 Git 仓库"}
    url = _git(cards_dir, "remote", "get-url", remote, check=False)
    local_branch = _git(cards_dir, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return {
        "status": "ready" if url.returncode == 0 else "no_remote",
        "cards_dir": str(cards_dir),
        "local_branch": local_branch.stdout.strip() or None,
        "remote": remote,
        "remote_url": redact(url.stdout.strip()) if url.returncode == 0 else None,
        "branch": branch,
        "uncommitted_cards": len(_pending_card_files(cards_dir)),
    }


def sync(cards_dir: Path, remote: str, branch: str) -> dict:
    """fetch → merge → push。任何失败都保留本地卡片与本地提交。"""
    if not is_repo(cards_dir):
        return {"status": "not_repo",
                "message": "卡片目录不是独立的 Git 仓库，无法同步。"
                           "请参考 docs/05-Pro-同步与展示.md 初始化。"}
    try:
        return _sync(cards_dir, remote, branch)
    except GitError as exc:
        return {"status": "error", "message": str(exc),
                "note": "本地卡片未被修改；排除问题后可再次运行 kb_sync。"}


def _sync(repo: Path, remote: str, branch: str) -> dict:
    # 1. 先把手动改过的卡片提交掉，避免 merge 因脏工作区被拒
    committed_local = 0
    pending = _pending_card_files(repo)
    if pending:
        _commit(repo, pending, f"kb: 同步前提交 {len(pending)} 张卡片的本地改动")
        committed_local = len(pending)

    dirty = _tracked_dirty(repo)
    if dirty:
        return {"status": "dirty", "files": dirty,
                "message": "卡片目录里有未提交的非卡片文件改动，请先自行处理后再同步。"}

    if _git(repo, "remote", "get-url", remote, check=False).returncode != 0:
        return {"status": "no_remote",
                "message": f"没有名为 '{remote}' 的 remote。请在卡片目录执行 "
                           f"git remote add {remote} <你的私有仓库地址>"}

    # 2. fetch
    try:
        heads = _git(repo, "ls-remote", "--heads", remote, f"refs/heads/{branch}",
                     timeout=NETWORK_TIMEOUT).stdout.strip()
        if heads:
            _git(repo, "fetch", "--quiet", remote, f"refs/heads/{branch}",
                 timeout=NETWORK_TIMEOUT)
    except GitError as exc:
        return {"status": "fetch_failed", "message": str(exc),
                "committed_local": committed_local,
                "note": "无法连接远端（网络或认证问题）。本地卡片与提交都已保留。"}

    # 3. merge
    pulled = 0
    if heads:
        if _has_head(repo):
            pulled = int(_git(repo, "rev-list", "--count", "HEAD..FETCH_HEAD").stdout)
        else:
            pulled = int(_git(repo, "rev-list", "--count", "FETCH_HEAD").stdout)
        if pulled:
            merge = _git(repo, "merge", "--no-edit", "--allow-unrelated-histories",
                         "-m", f"kb: 合并 {remote}/{branch} 的卡片", "FETCH_HEAD",
                         check=False)
            if merge.returncode != 0:
                conflicts = _git(repo, "diff", "--name-only", "--diff-filter=U",
                                 check=False).stdout.split()
                _git(repo, "merge", "--abort", check=False)
                return {
                    "status": "conflict" if conflicts else "merge_failed",
                    "files": conflicts,
                    "message": redact((merge.stderr or merge.stdout).strip()),
                    "committed_local": committed_local,
                    "note": "已取消合并，本地卡片保持原样，没有任何卡片被覆盖。"
                            "请按 docs/05-Pro-同步与展示.md 的「处理冲突」手动解决。",
                }

    # 4. push（永不 force）
    if not _has_head(repo):
        return {"status": "ok", "pulled": pulled, "pushed": 0,
                "committed_local": committed_local, "message": "还没有任何卡片"}
    ahead_range = "FETCH_HEAD..HEAD" if heads else "HEAD"
    pushed = int(_git(repo, "rev-list", "--count", ahead_range).stdout)
    if pushed:
        try:
            _git(repo, "push", "--quiet", remote, f"HEAD:refs/heads/{branch}",
                 timeout=NETWORK_TIMEOUT)
        except GitError as exc:
            return {"status": "push_failed", "message": str(exc),
                    "pulled": pulled, "committed_local": committed_local,
                    "note": "推送失败，本地提交已保留。稍后再运行一次 kb_sync 即可重试。"}

    return {"status": "ok", "pulled": pulled, "pushed": pushed,
            "committed_local": committed_local, "commit": _short_head(repo)}
