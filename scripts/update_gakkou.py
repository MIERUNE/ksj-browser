#!/usr/bin/env python3
"""
学校データ（P29）の定義ファイル自動生成ツール

Usage:
    python scripts/update_gakkou.py [--url URL] [--output OUTPUT]

Examples:
    # デフォルトURL（P29ページ）から取得してgakkou.jsonに保存
    python scripts/update_gakkou.py

    # カスタムURLから取得
    python scripts/update_gakkou.py --url https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html

    # カスタム出力パス
    python scripts/update_gakkou.py --output /path/to/output.json

Exit Codes:
    0: 成功
    1: ネットワークエラー（URL取得失敗）
    2: テーブル未検出（HTML解析失敗）
    3: 書き込み失敗（ファイル保存失敗）
"""

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# デフォルト設定
DEFAULT_P29_URL = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P29-2023.html"
DEFAULT_OUTPUT_PATH = (
    Path(__file__).parent.parent / "ksj" / "data_collections" / "gakkou.json"
)


class P29TableParser(HTMLParser):
    """P29ページのテーブルを解析するHTMLパーサー

    テーブル構造:
    <table class="responsive-table">
        <tbody>
            <tr>
                <th>地域</th>
                <th>測地系</th>
                <th>年</th>
                <th>ファイル容量</th>
                <th>ファイル名</th>
                <th>ダウンロード</th>
            </tr>
            <tr>
                <td id="prefecture0">全国</td>
                <td class="txtCenter">世界測地系</td>
                <td class="txtCenter">2023年（令和5年）</td>
                <td class="txtCenter">1.13MB</td>
                <td class="txtCenter">P29-23_GML.zip</td>
                ...
            </tr>
        </tbody>
    </table>
    """

    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.cell_index = 0
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # responsive-table クラスを持つ table タグを検出
        if tag == "table" and "class" in attrs_dict:
            if "responsive-table" in attrs_dict["class"]:
                self.in_table = True

        if self.in_table:
            if tag == "tbody":
                self.in_tbody = True
            elif tag == "tr" and self.in_tbody:
                self.in_row = True
                self.current_row = []
                self.cell_index = 0
            elif tag in ("td", "th") and self.in_row:
                self.in_cell = True

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            # ヘッダー行はスキップ（th のみの行）
            # データ行は6列: 地域、測地系、年、容量、ファイル名、ダウンロード
            if len(self.current_row) >= 5:
                region_raw = self.current_row[0].strip()
                year_display = self.current_row[2].strip()
                filename = self.current_row[4].strip()

                if (
                    region_raw
                    and year_display
                    and filename
                    and re.search(r"\d{4}年", year_display)
                    and filename.startswith("P29-")
                ):
                    self.rows.append(
                        {
                            "region_raw": region_raw,
                            "year_display": year_display,
                            "filename": filename,
                        }
                    )
        elif tag in ("td", "th"):
            self.in_cell = False
            self.cell_index += 1

    def handle_data(self, data):
        if self.in_cell:
            self.current_row.append(data)


def extract_table_rows(html: str) -> List[Dict[str, str]]:
    """
    HTMLからテーブル行を抽出

    Args:
        html: HTML文字列

    Returns:
        各行が {year_display, region_raw, filename} の辞書のリスト
    """
    parser = P29TableParser()
    parser.feed(html)
    return parser.rows


def normalize_year(year_display: str) -> str:
    """
    年度表示を正規化（YYYY年形式に統一）

    Args:
        year_display: 表示年度（例: "令和5年" or "2023年（令和5年）" or "平成25年"）

    Returns:
        正規化された年度（例: "2023年" or "2021年" or "2013年"）
    """
    # 和暦から西暦への変換マップ
    era_map = {
        "令和": (2019, 1),  # 令和元年 = 2019年
        "平成": (1989, 1),  # 平成元年 = 1989年
        "昭和": (1926, 1),  # 昭和元年 = 1926年
        "大正": (1912, 1),  # 大正元年 = 1912年
    }

    # まず西暦（4桁数字）があるかチェック
    match = re.match(r"(\d{4})年", year_display)
    if match:
        return f"{match.group(1)}年"

    # 和暦表記をチェック（例: "令和5年" or "平成25年"）
    for era_name, (base_year, base_era_year) in era_map.items():
        # 「元年」パターン
        if year_display.startswith(era_name + "元年"):
            return f"{base_year}年"

        # 「～年」パターン（例: "令和5年"）
        pattern = rf"{era_name}(\d+)年"
        match = re.match(pattern, year_display)
        if match:
            era_year = int(match.group(1))
            western_year = base_year + era_year - base_era_year
            return f"{western_year}年"

    return year_display


def normalize_region(region_raw: str) -> str:
    """
    地域名を正規化（都道府県サフィックスを削除）

    Args:
        region_raw: 元の地域名（例: "青森県", "東京", "北海道"）

    Returns:
        正規化された地域名（例: "青森", "東京", "北海道"）

    Note:
        - "北海道"はそのまま
        - "全国"はそのまま
        - "県"/"都"/"府"サフィックスを削除
    """
    # "北海道"はそのまま
    if region_raw == "北海道":
        return region_raw

    # "全国"や地方名はそのまま
    if region_raw == "全国" or "地方" in region_raw:
        return region_raw

    # "県"/"都"/"府"サフィックスを削除（もともと2文字の地名は除外）
    for suffix in ["県", "都", "府"]:
        if region_raw.endswith(suffix) and len(region_raw) > 2:
            return region_raw[:-1]

    return region_raw


def deduplicate_by_format(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    同一年度・地域の重複を解消（SHP優先）

    Args:
        rows: 各行が {year_display, region_raw, filename} の辞書のリスト

    Returns:
        重複解消後のリスト

    Note:
        同一年・同一地域に複数候補がある場合:
        - SHP (.zip で _GML を含まない) を優先
        - SHP が存在しない場合は GML (_GML.zip) を採用
    """
    # 年度・地域をキーにした辞書で管理
    unique_map: Dict[tuple, Dict[str, str]] = {}

    for row in rows:
        year = row["year_display"]
        region = row["region_raw"]
        filename = row["filename"]
        key = (year, region)

        if key in unique_map:
            # すでに存在する場合、SHPを優先
            existing_filename = unique_map[key]["filename"]
            is_current_shp = filename.endswith(".zip") and "_GML" not in filename
            is_existing_shp = (
                existing_filename.endswith(".zip") and "_GML" not in existing_filename
            )

            if is_current_shp and not is_existing_shp:
                # 新しいファイルがSHPで既存がGML → SHPで上書き
                unique_map[key] = row
            # 既存がSHPなら上書きしない
        else:
            # まだ存在しない場合は追加
            unique_map[key] = row

    return list(unique_map.values())


def group_by_year_region(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    生データリストから最終的なJSON構造を構築

    Args:
        rows: 各行が {year_display, region_raw, filename} の辞書のリスト

    Returns:
        年度 → 地域 → ファイル名 の辞書構造
    """
    result: Dict[str, Dict[str, str]] = {}

    for row in rows:
        year = normalize_year(row["year_display"])
        region = normalize_region(row["region_raw"])
        filename = row["filename"]

        # 年度がまだない場合は初期化
        if year not in result:
            result[year] = {}

        # 地域を追加
        result[year][region] = filename

    # 年度を降順ソート
    sorted_result = dict(sorted(result.items(), reverse=True))
    return sorted_result


def fetch_html(url: str) -> str:
    """
    指定URLからHTMLを取得

    Args:
        url: 取得対象のURL

    Returns:
        HTML文字列

    Raises:
        URLError: ネットワークエラー
        HTTPError: HTTPエラー
    """
    # User-Agent を指定してリクエスト
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as response:
        html_bytes = response.read()
        # エンコーディングを推測（デフォルトはUTF-8）
        return html_bytes.decode("utf-8", errors="replace")


def save_json(data: Dict, output_path: Path) -> None:
    """
    JSON形式でファイルに保存

    Args:
        data: 保存するデータ
        output_path: 出力ファイルパス

    Raises:
        IOError: 書き込み失敗
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main(url: str = None, output_path: str = None) -> int:
    """
    メイン処理

    Args:
        url: P29データ一覧ページのURL（省略時はデフォルト）
        output_path: 出力JSONファイルパス（省略時はデフォルト）

    Returns:
        終了コード（0:成功, 1:ネットワークエラー, 2:テーブル未検出, 3:書き込み失敗）
    """
    # コマンドライン引数が優先、関数引数が次、デフォルト値が最後
    if url is None:
        parser = argparse.ArgumentParser(
            description="学校データ（P29）の定義ファイル自動生成"
        )
        parser.add_argument(
            "--url",
            default=DEFAULT_P29_URL,
            help=f"P29データ一覧ページのURL（デフォルト: {DEFAULT_P29_URL}）",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=str(DEFAULT_OUTPUT_PATH),
            help=f"出力JSONファイルパス（デフォルト: {DEFAULT_OUTPUT_PATH}）",
        )

        args = parser.parse_args()
        url = args.url
        output_path = args.output

    # 出力パスをPathオブジェクトに変換
    output_file = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    try:
        # HTMLを取得
        print(f"P29ページを取得中: {url}")
        html = fetch_html(url)

        # テーブル行を抽出
        print("テーブル行を抽出中...")
        rows = extract_table_rows(html)

        if not rows:
            print("エラー: テーブルが見つかりませんでした", file=sys.stderr)
            return 2

        print(f"{len(rows)}行のデータを抽出しました")

        # 重複を解消
        print("重複を解消中...")
        deduplicated_rows = deduplicate_by_format(rows)
        print(f"{len(deduplicated_rows)}行に削減しました")

        # JSON構造を構築
        print("JSON構造を構築中...")
        result = group_by_year_region(deduplicated_rows)

        # JSONファイルに保存
        print(f"JSONファイルに保存中: {output_file}")
        save_json(result, output_file)

        print(f"✓ 成功: {output_file} を更新しました")
        print(f"  - 年度数: {len(result)}")
        print(f"  - 地域数: {sum(len(regions) for regions in result.values())}")

        return 0

    except (URLError, HTTPError) as e:
        print(f"エラー: ネットワークエラー - {e}", file=sys.stderr)
        return 1
    except IOError as e:
        print(f"エラー: 書き込み失敗 - {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"エラー: 予期しないエラー - {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
