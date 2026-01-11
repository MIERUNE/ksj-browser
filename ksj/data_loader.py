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
        "gyousei_kuiki": "行政区域",
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

    # ディレクトリ年の決定（戦略パターン）
    strategy = _DIR_YEAR_STRATEGIES.get(data_id, _get_dir_year_from_filename_yy)
    dir_year = strategy(year_int, head_token)

    # URLの形式: https://nlftp.mlit.go.jp/ksj/gml/data/{DATA_ID}/{DATA_ID}-{DIR_YEAR}/{FILENAME}
    base_url = "https://nlftp.mlit.go.jp/ksj/gml/data"
    return f"{base_url}/{data_id}/{data_id}-{dir_year}/{filename}"


def _get_dir_year_from_filename_yy(year_int: int, head_token: str) -> str:
    """
    既存データID（A33等）向け戦略: ファイル名の先頭トークンからディレクトリ年を決定

    Args:
        year_int: 入力年度の4桁整数（使用されない）
        head_token: ファイル名の先頭トークン（例: "24", "20240101"）

    Returns:
        str: ディレクトリ年文字列（"24", "2024"等）
    """
    # 4桁年 or YYYYMMDD がファイル名に入る場合は YYYY を採用
    if head_token.isdigit() and len(head_token) == 8:
        return head_token[:4]
    elif head_token.isdigit() and len(head_token) == 4:
        return head_token
    else:
        return head_token


def _get_dir_year_from_input_yyyy(year_int: int, head_token: str) -> str:
    """
    N03（行政区域）向け戦略: 入力年度から4桁ディレクトリ年を決定

    ファイル名には YYYYMMDD/YYMMDD/YY など揺れがあるため、
    入力 year（ページの「年」列）を信頼してディレクトリを決定する。

    Args:
        year_int: 入力年度の4桁整数（例: 2025）
        head_token: ファイル名の先頭トークン（使用されない）

    Returns:
        str: ディレクトリ年文字列（"2025"等）
    """
    return str(year_int)


# データIDごとのディレクトリ年決定戦略マッピング
_DIR_YEAR_STRATEGIES: dict[str, callable] = {
    "N03": _get_dir_year_from_input_yyyy,
    # 新規データID追加時はここに1行追加するだけで済む
    # "L01": _get_dir_year_from_filename_yy,  # 例: 既存パターンを明示的に指定
}


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
