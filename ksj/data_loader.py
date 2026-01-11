"""KSJデータコレクション定義を読み込むモジュール"""

import json
import re
from pathlib import Path


def load_data_collections() -> dict[str, dict[str, dict[str, str]]]:
    """
    data_collections配下のJSONファイルを読み込む

    Returns:
        dict: {
            "dosyasaigai_keikai_kuiki": {
                "2024年": {"北海道": "A33-24_01_SHP.zip", ...},
                ...
            },
            ...
        }
    """
    collections_dir = Path(__file__).parent / "data_collections"
    collections = {}

    for filepath in collections_dir.glob("*.json"):
        collection_name = filepath.stem
        with filepath.open(encoding="utf-8") as f:
            data = json.load(f)
            collections[collection_name] = data

    return collections


def get_data_collection_name(collection_id: str) -> str:
    """コレクションIDから人間が読める名前を取得"""
    name_mapping = {
        "dosyasaigai_keikai_kuiki": "土砂災害警戒区域",
    }
    return name_mapping.get(collection_id, collection_id)


def build_download_url(collection_id: str, year: str, filename: str) -> str:
    """
    ダウンロードURLを構築

    Args:
        collection_id: コレクションID（例: "dosyasaigai_keikai_kuiki"）
        year: 年度（例: "2024年"）
        filename: ファイル名（例: "A33-24_01_SHP.zip"）

    Returns:
        str: 完全なダウンロードURL
    """

    def parse_year_int(value: str) -> int:
        match = re.search(r"\d{4}", value)
        if not match:
            raise ValueError(f"年度を解釈できません: {value}")
        return int(match.group(0))

    # ファイル名から識別子を抽出（例: A33-24_01_SHP.zip -> A33, 24 / N03-20250101_01_GML.zip -> N03, 2025）
    base_name = filename.split(".")[0]
    parts = base_name.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"ファイル名が想定形式ではありません: {filename}")

    data_id = parts[0]
    second = parts[1]
    head_token = second.split("_", 1)[0]

    year_int = parse_year_int(year)

    # ディレクトリ年の決定
    # - 多くのデータ(A33等): {DATA_ID}-{YY}
    # - N03(行政区域): {DATA_ID}-{YYYY}（ファイル名は YYYYMMDD/YYMMDD/YY など揺れるため、入力 year を優先）
    if data_id == "N03":
        dir_year = str(year_int)
    else:
        # 4桁年 or YYYYMMDD がファイル名に入る場合は YYYY を採用
        if head_token.isdigit() and len(head_token) == 8:
            dir_year = head_token[:4]
        elif head_token.isdigit() and len(head_token) == 4:
            dir_year = head_token
        else:
            dir_year = head_token

    # URLの形式: https://nlftp.mlit.go.jp/ksj/gml/data/{DATA_ID}/{DATA_ID}-{DIR_YEAR}/{FILENAME}
    base_url = "https://nlftp.mlit.go.jp/ksj/gml/data"
    return f"{base_url}/{data_id}/{data_id}-{dir_year}/{filename}"


def get_shapefile_path_in_zip(year: str, filename: str) -> str:
    """
    ZIPファイル内のShapefileパスを取得（レガシー関数）

    ⚠️ 非推奨: この関数は固定パス前提の旧実装の名残です。
    新しい実装では zip_scanner.py を使用してZIP内を動的に走査します。
    この関数はテストコードとの互換性のためにのみ残されています。

    2024年はZIP直下、2023年以前はShape/配下にある

    Args:
        year: 年度（例: "2024年"）
        filename: ファイル名（例: "A33-24_01_SHP.zip"）

    Returns:
        str: ZIP内の相対パス（例: "A33-24_01Polygon.shp" or "Shape/A33-23_02Polygon.shp"）
    """
    # ファイル名からベース名を抽出
    base_name = filename.split(".")[0]  # A33-24_01_SHP or A33-23_02_GML

    # 年度を整数に変換
    year_int = int(year.replace("年", ""))

    # Shapefileの名前を構築
    if year_int >= 2024:
        # 2024年以降: ZIP直下
        shapefile_name = f"{base_name.replace('_SHP', '')}Polygon.shp"
    else:
        # 2023年以前: Shape/配下
        shapefile_name = f"Shape/{base_name.replace('_GML', '')}Polygon.shp"

    return shapefile_name
