#!/usr/bin/env python3
"""
行政区域データ（N03）の定義ファイル自動生成ツール

Usage:
    python scripts/update_gyousei_kuiki.py [--url URL] [--output OUTPUT]

Examples:
    # デフォルトURL（N03ページ）から取得してgyousei_kuiki.jsonに保存
    python scripts/update_gyousei_kuiki.py

    # カスタムURLから取得
    python scripts/update_gyousei_kuiki.py --url https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_1.html

    # カスタム出力パス
    python scripts/update_gyousei_kuiki.py --output /path/to/output.json

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
DEFAULT_N03_URL = "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_1.html"
DEFAULT_OUTPUT_PATH = (
    Path(__file__).parent.parent / "ksj" / "data_collections" / "gyousei_kuiki.json"
)


class N03TableParser(HTMLParser):
    """N03ページのテーブルを解析するHTMLパーサー

    テーブル構造:
    <table class="mb30 responsive-table">
        <tbody>
            <tr>
                <th class="txtCenter">地域</th>
                <th class="txtCenter">測地系</th>
                <th class="txtCenter">年</th>
                <th class="txtCenter">ファイル容量</th>
                <th class="txtCenter">ファイル名</th>
                <th class="txtCenter">ダウンロード</th>
            </tr>
            <tr>
                <td class="bgc0" id="prefecture00">全国</td>
                <td class="txtCenter">世界測地系</td>
                <td class="txtCenter">令和5年</td>
                <td class="txtCenter">427MB</td>
                <td class="txtCenter">N03-20230101_GML.zip</td>
                ...
            </tr>
        </tbody>
    </table>
    """

    def __init__(self):
        super().__init__()
        self.in_target_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_header_row = False
        self.current_td_index = 0
        self.current_row: Dict[str, str] = {}
        self.rows: List[Dict[str, str]] = []
        self.current_td_text = ""
        self.header_row_count = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # class="mb30 responsive-table"のテーブルを探す
        if tag == "table":
            classes = attrs_dict.get("class", "")
            if "responsive-table" in classes and "mb30" in classes:
                self.in_target_table = True
                self.header_row_count = 0
        elif tag == "tbody" and self.in_target_table:
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = {}
            self.current_td_index = 0
        elif tag == "td" and self.in_tr:
            self.current_td_text = ""
            # idを持つtdの場合、そのid値を保存（地域識別に使用）
            if "id" in attrs_dict:
                self.current_row["prefecture_id"] = attrs_dict["id"]
        elif tag == "th" and self.in_tr:
            # ヘッダー行を検出
            self.in_header_row = True
            self.current_td_text = ""

    def handle_endtag(self, tag):
        if tag == "table" and self.in_target_table:
            self.in_target_table = False
            self.in_tbody = False
        elif tag == "tbody" and self.in_tbody:
            # tbody終了時にフラグをリセット（次のテーブルのため）
            pass
        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            # ヘッダー行はスキップ
            if self.in_header_row:
                self.in_header_row = False
                self.header_row_count += 1
            # 行データが完全な場合のみ追加（地域、年、ファイル名が揃っている）
            elif all(
                k in self.current_row
                for k in ["region_raw", "year_display", "filename"]
            ):
                self.rows.append(self.current_row.copy())
        elif tag == "td" and self.in_tr and not self.in_header_row:
            text = self.current_td_text.strip()
            # カラムインデックスに応じてデータを格納
            # 0: 地域, 1: 測地系（スキップ）, 2: 年, 3: ファイル容量（スキップ）, 4: ファイル名
            if self.current_td_index == 0:
                self.current_row["region_raw"] = text
            elif self.current_td_index == 2:
                self.current_row["year_display"] = text
            elif self.current_td_index == 4:
                self.current_row["filename"] = text
            self.current_td_index += 1
        elif tag == "th" and self.in_header_row:
            # ヘッダーのthタグはスキップ
            pass

    def handle_data(self, data):
        if self.in_tr and (self.in_header_row or self.current_td_text is not None):
            self.current_td_text += data


def extract_table_rows(html: str) -> List[Dict[str, str]]:
    """
    N03ページのHTMLからテーブル行を抽出

    Args:
        html: N03ページのHTML文字列

    Returns:
        各行が {year_display, region_raw, filename} の辞書のリスト
    """
    parser = N03TableParser()
    parser.feed(html)
    return parser.rows


def normalize_year(year_display: str) -> str:
    """
    年度表示を正規化（YYYY年形式に統一）

    Args:
        year_display: 表示年度（例: "令和5年" or "2025年（令和7年）" or "平成28年"）

    Returns:
        正規化された年度（例: "2023年" or "2025年" or "2016年"）
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
    
    # 和暦表記をチェック（例: "令和5年" or "平成28年"）
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
        region_raw: 元の地域名（例: "青森", "東京", "京都"）

    Returns:
        正規化された地域名（例: "青森", "東京", "京都"）

    Note:
        - "北海道"はそのまま
        - "全国"はそのまま
        - 地域名はすでにサフィックスが削除された形式で来るためそのまま返す
    """
    # HTML上ではすでに「青森」「東京」の形式で来るためそのまま返す
    return region_raw


def build_collection_structure(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """
    生データリストから最終的なJSON構造を構築

    Args:
        rows: 各行が {year_display, region_raw, filename} の辞書のリスト

    Returns:
        年度 → 地域 → ファイル名 の辞書構造

    Note:
        同一年・同一地域に複数候補がある場合、SHP優先・無ければGMLを選択
    """
    result: Dict[str, Dict[str, str]] = {}

    for row in rows:
        year = normalize_year(row["year_display"])
        region = normalize_region(row["region_raw"])
        filename = row["filename"]

        # 年度がまだない場合は初期化
        if year not in result:
            result[year] = {}

        # SHP/GML優先ロジック
        if region in result[year]:
            # すでに存在する場合、SHPを優先
            existing_filename = result[year][region]
            if "_SHP.zip" in filename:
                # 新しいファイルがSHPなら上書き
                result[year][region] = filename
            elif "_GML.zip" in existing_filename:
                # 既存がGMLで新しいもSHPでない場合は上書きしない
                pass
        else:
            # まだ存在しない場合は追加
            result[year][region] = filename

    return result


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


def main() -> int:
    """
    メイン処理

    Returns:
        終了コード（0:成功, 1:ネットワークエラー, 2:テーブル未検出, 3:書き込み失敗）
    """
    parser = argparse.ArgumentParser(
        description="行政区域データ（N03）の定義ファイル自動生成"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_N03_URL,
        help=f"N03データ一覧ページのURL（デフォルト: {DEFAULT_N03_URL}）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"出力JSONファイルパス（デフォルト: {DEFAULT_OUTPUT_PATH}）",
    )
    parser.add_argument(
        "--html-file", type=Path, help="HTMLファイルから読み込む（テスト用）"
    )

    args = parser.parse_args()

    try:
        # HTMLを取得
        if args.html_file:
            print(f"HTMLファイルを読み込み中: {args.html_file}")
            html = args.html_file.read_text(encoding="utf-8")
        else:
            print(f"N03ページを取得中: {args.url}")
            html = fetch_html(args.url)

        # テーブル行を抽出
        print("テーブル行を抽出中...")
        rows = extract_table_rows(html)

        if not rows:
            print("エラー: テーブルが見つかりませんでした", file=sys.stderr)
            return 2

        print(f"{len(rows)}行のデータを抽出しました")

        # JSON構造を構築
        print("JSON構造を構築中...")
        result = build_collection_structure(rows)

        # JSONファイルに保存
        print(f"JSONファイルに保存中: {args.output}")
        save_json(result, args.output)

        print(f"✓ 成功: {args.output} を更新しました")
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
        return 1


if __name__ == "__main__":
    sys.exit(main())
