# kb-mcp/backup.py — 随手学 Private：知识卡备份与恢复
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
把卡片目录顶层的 .md 卡片打包成 tar.gz，或从备份包恢复。

恢复永不覆盖：目标里已有同名但内容不同的卡片会被跳过并报告，
内容相同的直接跳过。备份包里任何不是顶层 .md 普通文件的条目
（子目录、符号链接、带 ../ 的路径）都会被拒绝。

令牌文件不在备份范围内：换服务器后请重新签发令牌。

用法:
    python backup.py backup --out cards-20260929.tar.gz
    python backup.py restore --from cards-20260929.tar.gz
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from kbcore import load_config, resolve_path


MAX_CARD_BYTES = 10 * 1024 * 1024  # 单张卡片上限，防止恶意备份包撑爆磁盘


class BackupError(RuntimeError):
    """备份或恢复失败。"""


def backup(cards_dir: Path, out: Path) -> int:
    if not cards_dir.is_dir():
        raise BackupError(f"卡片目录不存在: {cards_dir}")
    if out.exists():
        raise BackupError(f"备份文件已存在，不会覆盖: {out}")
    cards = sorted(p for p in cards_dir.glob("*.md") if p.is_file() and not p.is_symlink())
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    with tarfile.open(tmp, "w:gz") as tar:
        for card in cards:
            tar.add(card, arcname=card.name, recursive=False)
    tmp.replace(out)
    return len(cards)


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    for m in members:
        if (not m.isfile() or "/" in m.name or "\\" in m.name
                or m.name.startswith(".") or not m.name.endswith(".md")):
            raise BackupError(f"备份包含不允许的条目，已拒绝整个恢复: {m.name!r}")
        if m.size > MAX_CARD_BYTES:
            raise BackupError(f"备份中的 {m.name!r} 超过 {MAX_CARD_BYTES} 字节，已拒绝整个恢复")
    return members


def restore(archive: Path, cards_dir: Path) -> dict:
    if not archive.is_file():
        raise BackupError(f"备份文件不存在: {archive}")
    cards_dir.mkdir(parents=True, exist_ok=True)
    restored, identical, conflicts = [], [], []
    with tarfile.open(archive, "r:gz") as tar:
        for member in _safe_members(tar):
            data = tar.extractfile(member).read()
            target = cards_dir / member.name
            if target.exists():
                if target.read_bytes() == data:
                    identical.append(member.name)
                else:
                    conflicts.append(member.name)
                continue
            with open(target, "xb") as fh:  # x：文件已存在时绝不覆盖
                fh.write(data)
            restored.append(member.name)
    return {"restored": restored, "identical": identical, "conflicts": conflicts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="备份 / 恢复随手学知识卡")
    parser.add_argument("--cards", help="卡片目录（默认读取配置中的 cards_dir）")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup", help="打包卡片")
    b.add_argument("--out", help="备份文件路径（默认 cards-<时间>.tar.gz）")
    r = sub.add_parser("restore", help="从备份包恢复（不覆盖已有卡片）")
    r.add_argument("--from", dest="archive", required=True, help="备份文件路径")
    args = parser.parse_args(argv)

    try:
        cards_dir = Path(args.cards) if args.cards else resolve_path(load_config()["cards_dir"])
        if args.command == "backup":
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            out = Path(args.out or f"cards-{stamp}.tar.gz")
            count = backup(cards_dir, out)
            print(f"[OK]  已备份 {count} 张卡片 → {out}")
        else:
            result = restore(Path(args.archive), cards_dir)
            print(f"[OK]  恢复 {len(result['restored'])} 张卡片，"
                  f"{len(result['identical'])} 张已存在且内容相同")
            if result["conflicts"]:
                print(f"[WARN] {len(result['conflicts'])} 张卡片与现有文件同名但内容不同，"
                      f"已保留现有文件、未恢复：")
                for name in result["conflicts"]:
                    print(f"       {name}")
    except (BackupError, OSError, tarfile.TarError) as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
