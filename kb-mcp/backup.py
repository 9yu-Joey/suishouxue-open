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
内容相同的直接跳过。

安全检查（备份与恢复使用同一套规则，本工具生成的备份一定能恢复）：
  - 只接受顶层、非隐藏的 .md 普通文件；子目录、符号链接、带 ../ 的路径
    都会让整个恢复被拒绝
  - 单张卡片、卡片数量、解压后总大小都有上限，防止解压炸弹
  - 在 tarfile 解析之前对解压流逐字节计量，扩展头等元数据同样受限
  - 恢复分两遍：第一遍只读条目头做检查，全部通过后第二遍才写卡片

令牌文件不在备份范围内：换服务器后请重新签发令牌。

用法:
    python backup.py backup --out cards-20260929.tar.gz
    python backup.py restore --from cards-20260929.tar.gz
"""

from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from kbcore import load_config, resolve_path


# 备份与恢复共用同一套上限，保证本工具生成的备份一定能恢复，
# 同时让恶意备份包（解压炸弹）无法耗尽内存或磁盘。
MAX_CARD_BYTES = 10 * 1024 * 1024    # 单张卡片
MAX_CARDS = 50_000                   # 卡片数量
MAX_TOTAL_BYTES = 256 * 1024 * 1024  # 解压后总大小
# 相邻两张卡片之间允许的元数据（tar 头、PAX/GNU 扩展头、填充）。
# 本工具生成的备份每张卡只有几百字节元数据；tarfile 读取缓冲也在此范围内。
MAX_META_BYTES = 64 * 1024


class BackupError(RuntimeError):
    """备份或恢复失败。"""


def _name_ok(name: str) -> bool:
    return ("/" not in name and "\\" not in name
            and not name.startswith(".") and name.endswith(".md"))


class _Budget:
    """累计数量与大小，超过上限立即报错。"""

    def __init__(self, action: str):
        self.action = action
        self.count = 0
        self.total = 0

    def add(self, name: str, size: int) -> None:
        if size > MAX_CARD_BYTES:
            raise BackupError(f"{name!r} 超过单张卡片上限 {MAX_CARD_BYTES} 字节，已拒绝{self.action}")
        self.count += 1
        self.total += size
        if self.count > MAX_CARDS:
            raise BackupError(f"卡片数量超过上限 {MAX_CARDS}，已拒绝{self.action}")
        if self.total > MAX_TOTAL_BYTES:
            raise BackupError(f"卡片总大小超过上限 {MAX_TOTAL_BYTES} 字节，已拒绝{self.action}")


def backup(cards_dir: Path, out: Path) -> int:
    if not cards_dir.is_dir():
        raise BackupError(f"卡片目录不存在: {cards_dir}")
    if out.exists():
        raise BackupError(f"备份文件已存在，不会覆盖: {out}")
    cards = sorted(
        p for p in cards_dir.glob("*.md")
        if p.is_file() and not p.is_symlink() and _name_ok(p.name)
    )
    # 先检查，确认生成的备份一定能被 restore 接受，再开始写
    budget = _Budget("备份")
    for card in cards:
        budget.add(card.name, card.stat().st_size)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".partial")
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            for card in cards:
                tar.add(card, arcname=card.name, recursive=False)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    return len(cards)


def _padded(size: int) -> int:
    return (size + 511) // 512 * 512


class _MeteredStream:
    """对 gzip 解压后的字节流计量，在 tarfile 解析任何头部之前就设好上限。

    tarfile 会先自行解压并解析 PAX/GNU 扩展头，之后才把普通条目交给我们检查；
    扩展头因此不在 _Budget 的统计里。这里按“步”计量：每一步是一张卡片的数据
    加上下一张卡片的全部头部，元数据最多 MAX_META_BYTES；另有整体上限。
    """

    def __init__(self, raw):
        self.raw = raw
        self.total = 0
        self.total_limit = MAX_TOTAL_BYTES + (MAX_CARDS + 1) * MAX_META_BYTES
        self.step = 0
        self.step_limit = MAX_META_BYTES

    def begin_step(self, allowance: int) -> None:
        self.step = 0
        self.step_limit = allowance

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.step_limit - self.step + 1  # 绝不无上限地读取
        data = self.raw.read(size)
        self.step += len(data)
        self.total += len(data)
        if self.step > self.step_limit or self.total > self.total_limit:
            raise BackupError("备份包含超出上限的元数据或内容（疑似解压炸弹），已拒绝整个恢复")
        return data


def _walk(archive: Path, on_member) -> None:
    """流式遍历备份包，逐条校验后交给 on_member(tar, member)。"""
    budget = _Budget("整个恢复")
    with gzip.open(archive, "rb") as raw:
        stream = _MeteredStream(raw)
        try:
            with tarfile.open(fileobj=stream, mode="r|") as tar:
                while (member := tar.next()) is not None:
                    if not member.isfile() or not _name_ok(member.name):
                        raise BackupError(
                            f"备份包含不允许的条目，已拒绝整个恢复: {member.name!r}")
                    budget.add(member.name, member.size)
                    # 下一步：本卡数据 + 下一张卡的全部头部
                    stream.begin_step(_padded(member.size) + MAX_META_BYTES)
                    on_member(tar, member)
        except (tarfile.TarError, EOFError, OSError) as exc:
            raise BackupError(f"备份文件损坏或格式不对: {exc}") from exc


def _validate_archive(archive: Path) -> None:
    """第一遍：只做检查，不写任何文件；超限立即停止读取。"""
    _walk(archive, lambda tar, member: None)


def restore(archive: Path, cards_dir: Path) -> dict:
    if not archive.is_file():
        raise BackupError(f"备份文件不存在: {archive}")
    _validate_archive(archive)

    cards_dir.mkdir(parents=True, exist_ok=True)
    restored, identical, conflicts = [], [], []

    # 第二遍：同样的流式校验（防止两遍之间备份包被替换），通过后才写入
    def write(tar, member):
        data = tar.extractfile(member).read(member.size)
        target = cards_dir / member.name
        if target.exists():
            if target.read_bytes() == data:
                identical.append(member.name)
            else:
                conflicts.append(member.name)
            return
        with open(target, "xb") as fh:  # x：文件已存在时绝不覆盖
            fh.write(data)
        restored.append(member.name)

    _walk(archive, write)
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
