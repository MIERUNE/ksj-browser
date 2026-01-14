#!/usr/bin/env python3
"""CLI tool to refresh dosyasaigai_keikai_kuiki.json from the MLIT A33 dataset page."""

from __future__ import annotations

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path
import sys
from typing import Dict, List, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_A33_URL = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A33-2024.html"
DEFAULT_OUTPUT_PATH = (
    Path(__file__).parent.parent
    / "ksj"
    / "data_collections"
    / "dosyasaigai_keikai_kuiki.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Update ksj/data_collections/dosyasaigai_keikai_kuiki.json by scraping the"
            " MLIT A33 listing."
        )
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_A33_URL,
        help="Override the A33 listing URL to fetch (default: %(default)s)",
    )
    parser.add_argument(
        "--html-file",
        help="Use a saved HTML file instead of performing a network request",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path to the JSON file to update (default: %(default)s)",
    )
    return parser


class A33TableParser(HTMLParser):
    """HTML parser that extracts rows from the A33 listing table."""

    def __init__(self) -> None:
        super().__init__()
        self.in_target_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_header_row = False
        self.current_row: Dict[str, str] = {}
        self.rows: List[Dict[str, str]] = []
        self.current_td_text = ""
        self.current_cells: List[str] = []

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        attrs_dict = dict(attrs)
        if tag == "table":
            classes = attrs_dict.get("class", "")
            if "mb30" in classes and "responsive-table" in classes:
                self.in_target_table = True
        elif tag == "tbody" and self.in_target_table:
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = {}
            self.current_cells = []
        elif tag == "th" and self.in_tr:
            self.in_header_row = True
            self.current_td_text = ""
        elif tag == "td" and self.in_tr:
            self.current_td_text = ""

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag == "table" and self.in_target_table:
            self.in_target_table = False
            self.in_tbody = False
        elif tag == "tbody" and self.in_tbody:
            self.in_tbody = False
        elif tag == "td" and self.in_tr and not self.in_header_row:
            value = self.current_td_text.strip()
            self.current_cells.append(value)
            self.current_td_text = ""
        elif tag == "th" and self.in_header_row:
            self.current_td_text = ""
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if self.in_header_row:
                self.in_header_row = False
            elif len(self.current_cells) >= 6:
                self.rows.append(
                    {
                        "region_raw": self.current_cells[0],
                        "year_display": self.current_cells[3],
                        "filename": self.current_cells[5],
                    }
                )
            elif len(self.current_cells) >= 5:
                self.rows.append(
                    {
                        "region_raw": self.current_cells[0],
                        "year_display": self.current_cells[2],
                        "filename": self.current_cells[4],
                    }
                )

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self.in_tr:
            self.current_td_text += data


def extract_table_rows(html: str) -> List[Dict[str, str]]:
    """Parse the HTML and return a list of row dictionaries."""

    parser = A33TableParser()
    parser.feed(html)
    return parser.rows


YEAR_RE = re.compile(r"(\d{4})年")
ERA_MAP = {
    "令和": (2019, 1),
    "平成": (1989, 1),
    "昭和": (1926, 1),
    "大正": (1912, 1),
}


def normalize_year(year_display: str) -> str:
    """Convert strings such as "2024年(令和6年)" or "令和5年" into "2024年"."""

    match = YEAR_RE.search(year_display)
    if match:
        return f"{match.group(1)}年"

    for era, (base_year, base_era_year) in ERA_MAP.items():
        if year_display.startswith(f"{era}元年"):
            return f"{base_year}年"
        m = re.search(rf"{era}(\d+)年", year_display)
        if m:
            era_year = int(m.group(1))
            western_year = base_year + era_year - base_era_year
            return f"{western_year}年"

    return year_display


def normalize_region(region_raw: str) -> str:
    """Normalize prefecture names to match existing JSON keys."""

    region = region_raw.strip()
    if region in {"全国", "北海道"}:
        return region

    suffixes = ("都", "道", "府", "県")
    if region and region[-1] in suffixes and len(region) > 2:
        return region[:-1]
    return region


def _prefer_new_filename(current: str | None, candidate: str) -> str:
    """Return the filename that should be stored for a region."""

    if not current:
        return candidate
    if current.endswith("_SHP.zip"):
        return current
    if candidate.endswith("_SHP.zip"):
        return candidate
    return current


def build_collection_structure(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Build {year: {region: filename}} with sorting and SHP preference."""

    structure: Dict[str, Dict[str, str]] = {}
    year_region_order: Dict[str, List[str]] = {}
    for row in rows:
        year = normalize_year(row["year_display"])
        region = normalize_region(row["region_raw"])
        filename = row["filename"].strip()
        structure.setdefault(year, {})
        year_region_order.setdefault(year, [])
        if region not in year_region_order[year]:
            year_region_order[year].append(region)
        current = structure[year].get(region)
        structure[year][region] = _prefer_new_filename(current, filename)

    sorted_structure: Dict[str, Dict[str, str]] = {}
    for year in sorted(structure.keys(), key=lambda y: int(y.rstrip("年")), reverse=True):
        regions = structure[year]
        order = year_region_order.get(year, [])
        sorted_structure[year] = {
            region: regions[region]
            for region in order
            if region in regions
        }
    return sorted_structure


def write_collection_json(data: Dict[str, Dict[str, str]], output_path: Path) -> None:
    """Write the JSON file using repo conventions."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent="\t")
        fp.write("\n")


def fetch_html(url: str) -> str:
    """Download HTML from the given URL using a simple User-Agent."""

    request = Request(url, headers={"User-Agent": "ksj-provider-update/1.0"})
    with urlopen(request) as response:  # type: ignore[no-untyped-call]
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset)


def load_html_from_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_update(args: argparse.Namespace) -> Dict[str, Dict[str, str]]:
    html_file = Path(args.html_file) if args.html_file else None
    output_path = Path(args.output)

    if html_file is not None:
        html_source = load_html_from_file(html_file)
    else:
        html_source = fetch_html(args.url)

    rows = extract_table_rows(html_source)
    if not rows:
        raise ValueError("Failed to locate any data rows in the HTML table.")

    collection = build_collection_structure(rows)
    write_collection_json(collection, output_path)
    return collection


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        collection = run_update(args)
    except (URLError, HTTPError) as exc:
        print(f"[error] ネットワークから HTML を取得できませんでした: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"[error] HTML ファイルを読み込めません: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"[error] HTML テーブルの解析に失敗しました: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[error] JSON 書き込みに失敗しました: {exc}", file=sys.stderr)
        return 3

    total_regions = sum(len(regions) for regions in collection.values())
    print(
        f"Updated {Path(args.output)} with {len(collection)} years / {total_regions} regions",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
