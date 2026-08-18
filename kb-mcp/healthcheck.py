# kb-mcp/healthcheck.py — 随手学 MCP Server 健康检查
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
健康检查脚本

复用 server.py 的配置加载逻辑，检查 kb-mcp 服务运行所需的
目录和配置文件是否就绪。
退出码 0 表示一切正常，1 表示存在问题。

用法:
    python healthcheck.py
"""

import os
import sys
from pathlib import Path

# 复用 server.py 的配置
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import CARDS_DIR, PROFILES_DIR, DEFAULT_PROFILE, _BASE_DIR


def main() -> int:
    """
    执行健康检查并打印状态报告。

    检查项：
    1. config.yaml 是否存在且可读
    2. 卡片目录（cards_dir）是否存在且可写
    3. 至少一个 Profile YAML 是否存在
    4. 默认 Profile 是否存在

    Returns:
        0 = 健康，1 = 存在问题
    """
    issues: list[str] = []

    # --- 1. 检查 config.yaml ---
    config_path = _BASE_DIR / "config.yaml"
    if config_path.exists():
        print("[OK]  config.yaml 存在")
    else:
        print("[WARN] config.yaml 不存在（使用默认配置 + 环境变量）")

    # --- 2. 检查卡片目录 ---
    print(f"[INFO] 卡片目录: {CARDS_DIR}")
    if CARDS_DIR.exists():
        if os.access(CARDS_DIR, os.W_OK):
            card_count = len(list(CARDS_DIR.glob("*.md")))
            print(f"[OK]  卡片目录存在且可写，已有 {card_count} 张卡片")
        else:
            issues.append(f"卡片目录 {CARDS_DIR} 不可写")
            print(f"[ERR] 卡片目录 {CARDS_DIR} 不可写")
    else:
        # 卡片目录不存在——检查父目录是否可写（首次保存时会自动创建）
        parent = CARDS_DIR.parent
        if parent.exists() and os.access(parent, os.W_OK):
            print(f"[WARN] 卡片目录尚未创建（首次保存时自动创建）")
        else:
            issues.append(f"卡片目录 {CARDS_DIR} 不存在且父目录不可写，无法自动创建")
            print(f"[ERR] 卡片目录不存在且父目录 {parent} 不可写")

    # --- 3. 检查 Profile 目录 ---
    print(f"[INFO] Profile 目录: {PROFILES_DIR}")
    if PROFILES_DIR.exists():
        profiles = list(PROFILES_DIR.glob("*.yaml"))
        if profiles:
            names = [p.stem for p in profiles]
            print(f"[OK]  找到 {len(profiles)} 个 Profile: {', '.join(names)}")
        else:
            issues.append("Profile 目录存在但没有 .yaml 文件")
            print("[ERR] Profile 目录存在但没有 .yaml 文件")
    else:
        issues.append(f"Profile 目录 {PROFILES_DIR} 不存在")
        print(f"[ERR] Profile 目录 {PROFILES_DIR} 不存在")

    # --- 4. 检查默认 Profile ---
    default_profile_path = PROFILES_DIR / f"{DEFAULT_PROFILE}.yaml"
    if default_profile_path.exists():
        print(f"[OK]  默认 Profile '{DEFAULT_PROFILE}' 存在")
    else:
        issues.append(f"默认 Profile '{DEFAULT_PROFILE}' 不存在")
        print(f"[ERR] 默认 Profile '{DEFAULT_PROFILE}' 不存在")

    # --- 汇总 ---
    print()
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        return 1
    else:
        print("所有检查通过，服务就绪。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
