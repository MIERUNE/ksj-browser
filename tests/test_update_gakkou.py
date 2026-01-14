#!/usr/bin/env python3
"""
学校データ（P29）更新ツールのテスト

Test-First Development:
このテストファイルは実装前に作成され、実装時に成功することを期待します。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 相対インポートを使用せず、sys.pathを介してインポート
sys.path.insert(0, str(Path(__file__).parent.parent))

# テスト対象モジュールの関数（実装前なのでインポートエラーは許容）
try:
    from scripts.update_gakkou import (
        deduplicate_by_format,
        extract_table_rows,
        group_by_year_region,
        main,
        normalize_region,
        normalize_year,
    )

    FUNCTIONS_AVAILABLE = True
except ImportError:
    FUNCTIONS_AVAILABLE = False


# フィクスチャ: サンプルHTMLファイルのパス
@pytest.fixture
def p29_sample_html_path():
    """P29サンプルHTMLファイルのパスを返す"""
    return Path(__file__).parent / "fixtures" / "p29_sample.html"


@pytest.fixture
def p29_sample_html_content(p29_sample_html_path):
    """P29サンプルHTMLの内容を読み込んで返す"""
    if not p29_sample_html_path.exists():
        pytest.skip(f"Fixture file not found: {p29_sample_html_path}")
    return p29_sample_html_path.read_text(encoding="utf-8")


# T008: test_normalize_year
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_normalize_year():
    """年度正規化のテスト

    要件:
    - "2023年（令和5年）" → "2023年"
    - "令和5年" → "2023年"
    - "令和3年" → "2021年"
    - "平成25年" → "2013年"
    """
    assert normalize_year("2023年（令和5年）") == "2023年"
    assert normalize_year("令和5年") == "2023年"
    assert normalize_year("令和3年") == "2021年"
    assert normalize_year("平成25年") == "2013年"
    assert normalize_year("2023年") == "2023年"


# T009: test_normalize_region
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_normalize_region():
    """地域名正規化のテスト

    要件:
    - "青森県" → "青森"
    - "東京" → "東京" (既に正規化済み)
    - "北海道" → "北海道" (そのまま)
    - "全国" → "全国" (そのまま)
    """
    assert normalize_region("青森県") == "青森"
    assert normalize_region("青森") == "青森"
    assert normalize_region("東京") == "東京"
    assert normalize_region("北海道") == "北海道"
    assert normalize_region("全国") == "全国"


# T010: test_extract_table_rows
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_extract_table_rows(p29_sample_html_content):
    """HTMLテーブルパースのテスト

    要件:
    - サンプルHTMLから7行のデータを抽出（データ行のみ）
    - 各行に year_display, region_raw, filename が含まれる
    - 全国、北海道、青森、東京のデータが含まれる
    """
    rows = extract_table_rows(p29_sample_html_content)

    # 7行のデータが抽出される
    assert len(rows) == 7
    data_rows = rows

    # 最初のデータ行は全国
    assert data_rows[0]["region_raw"] == "全国"
    assert data_rows[0]["year_display"] == "2023年（令和5年）"
    assert data_rows[0]["filename"] == "P29-23_GML.zip"

    # 北海道2023のデータ
    hokkaido_2023 = [
        r
        for r in data_rows
        if r["region_raw"] == "北海道" and "2023" in r["year_display"]
    ]
    assert len(hokkaido_2023) == 1
    assert hokkaido_2023[0]["filename"] == "P29-23_01_GML.zip"

    # 青森のデータが2件（2023, 2021）
    aomori_rows = [r for r in data_rows if r["region_raw"] in ["青森県", "青森"]]
    assert len(aomori_rows) == 2

    # 2013年のSHPデータも含まれる
    shp_rows = [
        r for r in data_rows if ".zip" in r["filename"] and "_GML" not in r["filename"]
    ]
    assert len(shp_rows) == 1
    assert shp_rows[0]["filename"] == "P29-13_01.zip"


# T011: test_deduplicate_by_format
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_deduplicate_by_format():
    """SHP/GML重複解消のテスト

    要件:
    - 同一年度・地域にSHPとGMLがある場合、SHPを優先
    - GMLのみの場合はGMLを採用
    """
    # テストデータ: 北海道2013にSHPとGMLの両方がある場合
    rows = [
        {
            "year_display": "2013年（平成25年）",
            "region_raw": "北海道",
            "filename": "P29-13_01_GML.zip",
        },
        {
            "year_display": "2013年（平成25年）",
            "region_raw": "北海道",
            "filename": "P29-13_01.zip",  # SHP
        },
        {
            "year_display": "2023年（令和5年）",
            "region_raw": "北海道",
            "filename": "P29-23_01_GML.zip",  # GMLのみ
        },
    ]

    deduplicated = deduplicate_by_format(rows)

    # 3行→2行に削減される（2013北海道の重複解消）
    assert len(deduplicated) == 2

    # 2013北海道はSHPが残る
    hokkaido_2013 = [
        r
        for r in deduplicated
        if "2013" in r["year_display"] and r["region_raw"] == "北海道"
    ]
    assert len(hokkaido_2013) == 1
    assert hokkaido_2013[0]["filename"] == "P29-13_01.zip"

    # 2023北海道はGMLが残る
    hokkaido_2023 = [
        r
        for r in deduplicated
        if "2023" in r["year_display"] and r["region_raw"] == "北海道"
    ]
    assert len(hokkaido_2023) == 1
    assert hokkaido_2023[0]["filename"] == "P29-23_01_GML.zip"


# T012: test_main_success
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_main_success(p29_sample_html_content, tmp_path):
    """正常系のフルワークフローテスト

    要件:
    - HTTP取得をモック
    - ファイル書き込みが正しく行われる
    - 終了コード0を返す
    """
    output_file = tmp_path / "gakkou.json"

    # urlopen をモック
    with patch("scripts.update_gakkou.urlopen") as mock_urlopen:
        # モックレスポンスを設定
        mock_response = MagicMock()
        mock_response.read.return_value = p29_sample_html_content.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        # main関数を実行
        exit_code = main(
            url="https://example.com/test.html",
            output_path=str(output_file),
        )

    # 終了コード0
    assert exit_code == 0

    # ファイルが作成された
    assert output_file.exists()

    # JSONが正しく生成された
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2023年と2021年と2013年のデータが含まれる
    assert "2023年" in data
    assert "2021年" in data
    assert "2013年" in data

    # 2023年の全国データ
    assert data["2023年"]["全国"] == "P29-23_GML.zip"

    # 2023年の北海道データ
    assert data["2023年"]["北海道"] == "P29-23_01_GML.zip"


# T013: test_main_network_error
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_main_network_error(tmp_path):
    """ネットワークエラー時のテスト

    要件:
    - HTTP取得失敗時、終了コード1を返す
    - ファイルは作成されない
    """
    output_file = tmp_path / "gakkou.json"

    # urlopen をモックしてHTTPErrorを発生させる
    with patch("scripts.update_gakkou.urlopen") as mock_urlopen:
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError("url", 404, "Not Found", {}, None)

        # main関数を実行
        exit_code = main(
            url="https://example.com/notfound.html",
            output_path=str(output_file),
        )

    # 終了コード1
    assert exit_code == 1

    # ファイルは作成されない
    assert not output_file.exists()


# T014: test_main_parse_error
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_main_parse_error(tmp_path):
    """HTML解析失敗時のテスト

    要件:
    - テーブル未検出時、終了コード2を返す
    - ファイルは作成されない
    """
    output_file = tmp_path / "gakkou.json"

    # urlopen をモックしてテーブルがないHTMLを返す
    with patch("scripts.update_gakkou.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><body>No table here</body></html>"
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        # main関数を実行
        exit_code = main(
            url="https://example.com/notable.html",
            output_path=str(output_file),
        )

    # 終了コード2
    assert exit_code == 2

    # ファイルは作成されない
    assert not output_file.exists()


# Helper function test (optional, for implementation reference)
@pytest.mark.skipif(not FUNCTIONS_AVAILABLE, reason="Functions not yet implemented")
def test_group_by_year_region():
    """group_by_year_region のテスト

    要件:
    - 正規化された年度・地域でグループ化
    - 年度 → 地域 → ファイル名 の構造を生成
    """
    rows = [
        {
            "year_display": "2023年",
            "region_raw": "北海道",
            "filename": "P29-23_01_GML.zip",
        },
        {
            "year_display": "2023年",
            "region_raw": "青森",
            "filename": "P29-23_02_GML.zip",
        },
        {
            "year_display": "2021年",
            "region_raw": "北海道",
            "filename": "P29-21_01_GML.zip",
        },
    ]

    result = group_by_year_region(rows)

    assert "2023年" in result
    assert "2021年" in result
    assert result["2023年"]["北海道"] == "P29-23_01_GML.zip"
    assert result["2023年"]["青森"] == "P29-23_02_GML.zip"
    assert result["2021年"]["北海道"] == "P29-21_01_GML.zip"
