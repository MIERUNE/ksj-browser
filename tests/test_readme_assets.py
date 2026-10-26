"""README と imgs/ の整合。相対リンクが実在し、画像が放置されていないこと。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
IMAGES = ROOT / "imgs"
# Markdown の `](target)` を拾う。空白や `)` を含むパスは使っていない。
LINK = re.compile(r"\]\(([^)\s]+)\)")


def relative_targets(markdown):
    """Markdown 内の相対リンク先。URL とページ内リンクは除く。"""
    return [
        target
        for target in LINK.findall(markdown.read_text(encoding="utf-8"))
        if not target.startswith(("http://", "https://", "#"))
    ]


def test_readme_relative_links_resolve():
    missing = [
        target for target in relative_targets(README) if not (ROOT / target).exists()
    ]
    assert missing == []


def test_every_image_is_referenced():
    # docs/superpowers/ の設計書・計画は履歴で、存在しない画像に触れることがあるため対象外。
    referenced = set()
    for markdown in [README, *ROOT.glob("specs/**/*.md")]:
        for target in relative_targets(markdown):
            referenced.add((markdown.parent / target).resolve())
    unreferenced = sorted(
        path.name
        for path in IMAGES.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.resolve() not in referenced
    )
    assert unreferenced == []
