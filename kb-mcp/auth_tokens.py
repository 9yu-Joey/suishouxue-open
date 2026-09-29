# kb-mcp/auth_tokens.py — 随手学 Private：访问令牌管理
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
Private 模式的静态访问令牌（Bearer token）。

模型：单用户、多设备。每台设备一个 token，可以单独吊销。

安全约定：
  - 令牌文件只保存 SHA-256 哈希，不保存明文；明文只在创建时显示一次。
  - 比对使用 hmac.compare_digest（常数时间）。
  - 令牌文件以 0600 权限原子写入。
  - 每次校验都会检查文件是否被修改，吊销无需重启即可生效。
  - 签发与吊销在跨进程文件锁内完成“读取—修改—写回”，并发操作不会互相覆盖
    （否则可能把已吊销的令牌写回成有效）。
  - 令牌文件结构损坏时直接报错，服务拒绝启动，校验一律失败。

用法:
    python auth_tokens.py create laptop     # 创建，明文只显示这一次
    python auth_tokens.py list
    python auth_tokens.py revoke laptop
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TOKEN_PREFIX = "ssx_"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class TokenFileError(ValueError):
    """令牌文件损坏或结构不对。"""


def _check_entry(entry) -> None:
    if (not isinstance(entry, dict)
            or not isinstance(entry.get("name"), str) or not _NAME_RE.match(entry["name"])
            or not isinstance(entry.get("hash"), str) or not _HASH_RE.match(entry["hash"])
            or not isinstance(entry.get("revoked"), (str, type(None)))):
        raise TokenFileError("令牌文件中有结构不正确的条目，请检查或重新签发令牌")


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    """跨进程互斥锁（POSIX 用 flock，Windows 用 msvcrt）。"""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as fh:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenStore:
    """令牌文件的读写。文件格式: {"tokens": [{name, hash, created, revoked}]}"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._cache_key: tuple[int, int] | None = None
        self._cache: list[dict] = []

    # -- 读取 ---------------------------------------------------------------

    def _load(self) -> list[dict]:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            self._cache_key, self._cache = None, []
            return []
        key = (stat.st_mtime_ns, stat.st_size)
        if key != self._cache_key:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise TokenFileError(f"令牌文件不是合法的 JSON: {self.path}") from exc
            tokens = data.get("tokens", []) if isinstance(data, dict) else None
            if not isinstance(tokens, list):
                raise TokenFileError(f"令牌文件格式错误: {self.path}")
            for entry in tokens:
                _check_entry(entry)
            self._cache_key, self._cache = key, tokens
        return self._cache

    def entries(self) -> list[dict]:
        """所有条目（不含哈希）。"""
        return [
            {k: e.get(k) for k in ("name", "created", "revoked")}
            for e in self._load()
        ]

    def active_count(self) -> int:
        return sum(1 for e in self._load() if not e.get("revoked"))

    def verify(self, token: str) -> str | None:
        """令牌有效时返回设备名，否则返回 None。"""
        if not token or not token.startswith(TOKEN_PREFIX):
            return None
        digest = _hash(token)
        matched = None
        # 遍历全部条目，不提前退出
        for entry in self._load():
            if hmac.compare_digest(str(entry.get("hash", "")), digest):
                if not entry.get("revoked"):
                    matched = entry.get("name")
        return matched

    # -- 写入 ---------------------------------------------------------------

    @contextlib.contextmanager
    def _transaction(self):
        """持锁读取最新内容，交给调用方修改，再在同一把锁内写回。"""
        with _file_lock(self.path.with_name(self.path.name + ".lock")):
            self._cache_key = None  # 强制重新读取，不用锁外的缓存
            tokens = [dict(e) for e in self._load()]
            yield tokens
            self._save(tokens)

    def _save(self, tokens: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tokens-")
        try:
            os.chmod(tmp, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"tokens": tokens}, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self._cache_key = None

    def create(self, name: str) -> str:
        """创建令牌并返回明文。同名的有效令牌不能重复创建。"""
        if not _NAME_RE.match(name):
            raise ValueError("设备名只允许字母、数字和 . _ -，且以字母或数字开头")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        with self._transaction() as tokens:
            if any(e.get("name") == name and not e.get("revoked") for e in tokens):
                raise ValueError(f"设备 '{name}' 已有有效令牌，请先吊销或换个名字")
            tokens.append({
                "name": name,
                "hash": _hash(token),
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "revoked": None,
            })
        return token

    def revoke(self, name: str) -> int:
        """吊销该设备名下所有有效令牌，返回吊销数量。"""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        count = 0
        with self._transaction() as tokens:
            for entry in tokens:
                if entry.get("name") == name and not entry.get("revoked"):
                    entry["revoked"] = now
                    count += 1
        return count


def main(argv: list[str] | None = None) -> int:
    from kbcore import load_config, resolve_path

    parser = argparse.ArgumentParser(description="管理随手学 Private 的访问令牌")
    parser.add_argument("--file", help="令牌文件路径（默认读取配置中的 http.tokens_file）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="为一台设备创建令牌").add_argument("name")
    sub.add_parser("revoke", help="吊销一台设备的令牌").add_argument("name")
    sub.add_parser("list", help="列出所有令牌（不显示令牌本身）")
    args = parser.parse_args(argv)

    try:
        path = Path(args.file) if args.file else resolve_path(load_config()["http"]["tokens_file"])
        store = TokenStore(path)
        if args.command == "create":
            token = store.create(args.name)
            print(f"已为设备 '{args.name}' 创建令牌（只显示这一次，请立即保存到客户端配置）：")
            print()
            print(f"    {token}")
            print()
            print(f"令牌文件: {path}")
        elif args.command == "revoke":
            count = store.revoke(args.name)
            if not count:
                print(f"设备 '{args.name}' 没有有效令牌", file=sys.stderr)
                return 1
            print(f"已吊销设备 '{args.name}' 的令牌，立即生效，无需重启服务")
        else:
            entries = store.entries()
            if not entries:
                print("还没有任何令牌。用 `python auth_tokens.py create <设备名>` 创建。")
            for e in entries:
                state = f"已吊销 {e['revoked']}" if e["revoked"] else "有效"
                print(f"{e['name']:<24} 创建于 {e['created']}  {state}")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
