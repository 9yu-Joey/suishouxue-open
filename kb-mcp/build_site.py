# kb-mcp/build_site.py — 随手学 Pro：知识卡片只读静态站点生成器
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
把卡片目录生成为只读 HTML 站点，可部署到 GitHub Pages 等静态托管。

默认不公开任何卡片：只有 tags 中包含发布标签（默认 "public"）的卡片
才会被生成。其余卡片不会出现在输出目录里，标题也不会打印到日志。

用法:
    python build_site.py                          # 使用 config.yaml 中的设置
    python build_site.py --cards ../my-cards --out ./site
    python build_site.py --tag 公开 --title "我的知识库"

依赖: pyyaml、markdown-it-py（见 requirements-pro.txt）。不依赖 mcp。
"""

from __future__ import annotations

import argparse
import html
import shutil
import sys
from pathlib import Path
from urllib.parse import quote

from kbcore import CARD_ID_RE, load_config, parse_body, parse_frontmatter, resolve_path

SITE_MARKER = ".suishouxue-site"


class SiteError(RuntimeError):
    """站点生成被拒绝或失败。"""


def _markdown_renderer():
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise SiteError(
            "缺少依赖 markdown-it-py，请先运行: pip install -r requirements-pro.txt"
        ) from exc
    # html=False：卡片里的原始 HTML 会被转义而不是执行
    return MarkdownIt("commonmark", {"html": False}).enable("table")


def collect_cards(cards_dir: Path, publish_tag: str) -> tuple[list[dict], int]:
    """返回 (要发布的卡片, 被跳过的卡片数)。"""
    published: list[dict] = []
    skipped = 0
    seen: set[str] = set()
    for md_file in sorted(cards_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        fm = parse_frontmatter(text)
        tags = fm.get("tags") if isinstance(fm, dict) else None
        if not isinstance(tags, list) or publish_tag not in [str(t) for t in tags]:
            skipped += 1
            continue
        card_id = str(fm.get("id", ""))
        if not CARD_ID_RE.match(card_id) or card_id in seen:
            print(f"[WARN] 跳过 id 缺失、不合法或重复的公开卡片: {md_file.name}",
                  file=sys.stderr)
            skipped += 1
            continue
        seen.add(card_id)
        published.append({
            "id": card_id,
            "title": str(fm.get("title") or card_id),
            "profile": str(fm.get("profile") or ""),
            "category": str(fm.get("category") or ""),
            "tags": [str(t) for t in tags if str(t) != publish_tag],
            "updated": str(fm.get("updated") or "")[:10],
            "body": parse_body(text),
        })
    published.sort(key=lambda c: c["updated"], reverse=True)
    return published, skipped


def _check_output_dir(out_dir: Path, cards_dir: Path) -> None:
    out = out_dir.resolve()
    cards = cards_dir.resolve()
    if out == cards or out in cards.parents:
        raise SiteError(f"输出目录 {out} 不能是卡片目录本身或它的上级目录")
    if out.exists():
        if not out.is_dir():
            raise SiteError(f"输出路径 {out} 已存在且不是目录")
        if any(out.iterdir()) and not (out / SITE_MARKER).exists():
            raise SiteError(
                f"输出目录 {out} 非空，且不是随手学生成的站点，拒绝覆盖。"
                f"请换一个空目录。"
            )


_CSS = """
:root{--bg:#fbfaf7;--fg:#1f2328;--muted:#656d76;--line:#e4e1da;--accent:#3b6e8f;--code:#f1efe9}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--fg:#e6e6e3;--muted:#9ba1a8;--line:#2c3036;--accent:#8ab8d6;--code:#22262b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}
a{color:var(--accent)}
h1{font-size:1.6rem;line-height:1.3;margin:0 0 8px}
.meta{color:var(--muted);font-size:.875rem;margin:0 0 24px}
.card-list{list-style:none;padding:0;margin:0}
.card-list li{padding:14px 0;border-bottom:1px solid var(--line)}
.card-list a{font-weight:600;text-decoration:none}
.tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:0 8px;margin-right:4px;font-size:.75rem}
article h2{font-size:1.2rem;margin-top:32px;padding-bottom:4px;border-bottom:1px solid var(--line)}
pre,code{background:var(--code);border-radius:4px;font-size:.875em}
pre{padding:12px;overflow-x:auto}
code{padding:1px 4px}
pre code{padding:0}
table{border-collapse:collapse;display:block;overflow-x:auto}
th,td{border:1px solid var(--line);padding:4px 10px}
footer{margin-top:48px;color:var(--muted);font-size:.8rem}
"""


def _page(title: str, body: str, css_href: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"zh-CN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n"
        f"<link rel=\"stylesheet\" href=\"{css_href}\">\n"
        "</head>\n<body>\n<main>\n"
        f"{body}\n"
        "<footer>由 <a href=\"https://github.com/9yu-Joey/suishouxue-open\">随手学 Open</a> 生成</footer>\n"
        "</main>\n</body>\n</html>\n"
    )


def _meta_line(card: dict) -> str:
    parts = [p for p in (card["profile"], card["category"], card["updated"]) if p]
    tags = "".join(f"<span class=\"tag\">{html.escape(t)}</span>" for t in card["tags"])
    return html.escape(" · ".join(parts)) + (" " + tags if tags else "")


def build_site(cards_dir: Path, out_dir: Path, publish_tag: str, title: str) -> dict:
    """生成站点，返回统计信息。"""
    md = _markdown_renderer()
    if not cards_dir.is_dir():
        raise SiteError(f"卡片目录不存在: {cards_dir}")
    _check_output_dir(out_dir, cards_dir)

    cards, skipped = collect_cards(cards_dir, publish_tag)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "cards").mkdir(parents=True)
    (out_dir / SITE_MARKER).write_text("generated by suishouxue build_site.py\n",
                                       encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    (out_dir / "style.css").write_text(_CSS.lstrip(), encoding="utf-8")

    items = []
    for card in cards:
        href = f"cards/{quote(card['id'])}.html"
        items.append(
            f"<li><a href=\"{href}\">{html.escape(card['title'])}</a>"
            f"<div class=\"meta\" style=\"margin:0\">{_meta_line(card)}</div></li>"
        )
        article = (
            f"<p><a href=\"../index.html\">← {html.escape(title)}</a></p>\n"
            f"<h1>{html.escape(card['title'])}</h1>\n"
            f"<p class=\"meta\">{_meta_line(card)}</p>\n"
            f"<article>\n{md.render(card['body'])}</article>"
        )
        (out_dir / "cards" / f"{card['id']}.html").write_text(
            _page(f"{card['title']} · {title}", article, "../style.css"),
            encoding="utf-8",
        )

    listing = "\n".join(items) or "<li>还没有公开的卡片。</li>"
    index = (
        f"<h1>{html.escape(title)}</h1>\n"
        f"<p class=\"meta\">共 {len(cards)} 张公开卡片</p>\n"
        f"<ul class=\"card-list\">\n{listing}\n</ul>"
    )
    (out_dir / "index.html").write_text(_page(title, index, "style.css"),
                                        encoding="utf-8")
    return {"published": len(cards), "skipped": skipped, "out_dir": str(out_dir)}


def main(argv: list[str] | None = None) -> int:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"[ERR] 配置有误: {exc}", file=sys.stderr)
        return 1
    site = config["site"]
    parser = argparse.ArgumentParser(description="生成随手学知识卡片的只读静态站点")
    parser.add_argument("--cards", help="卡片目录（默认读取配置中的 cards_dir）")
    parser.add_argument("--out", help="输出目录（默认读取配置中的 site.output_dir）")
    parser.add_argument("--tag", help=f"发布标签（默认 {site['publish_tag']!r}）")
    parser.add_argument("--title", help="站点标题")
    args = parser.parse_args(argv)

    cards_dir = Path(args.cards).resolve() if args.cards else resolve_path(config["cards_dir"])
    out_dir = Path(args.out).resolve() if args.out else resolve_path(site["output_dir"])
    tag = args.tag or site["publish_tag"]

    try:
        stats = build_site(cards_dir, out_dir, tag, args.title or site["title"])
    except SiteError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK]  已生成 {stats['published']} 张公开卡片 → {stats['out_dir']}")
    print(f"[INFO] {stats['skipped']} 张卡片未带 '{tag}' 标签，未发布")
    if stats["published"]:
        print("[提醒] 部署到 GitHub Pages 后，站点对所有人可见——私有仓库 ≠ 私有网站。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
