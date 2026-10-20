"""
Tests for scripts/update_gyousei_kuiki.py

TDD approach: Write tests first, then implement
"""


# T008: N03ページのHTMLから対象テーブル行を抽出し、「年度/地域/ファイル名」の生データリストに変換するユニットテスト
def test_extract_table_rows_from_html():
    """N03ページのHTMLからテーブル行を抽出"""
    # サンプルHTML（実際のN03ページから抜粋した構造）
    sample_html = """
    <html>
    <body>
        <table id="DataTables_Table_0" class="mb30 responsive-table dataTables dataTable">
            <thead>
                <tr>
                    <th>地域</th>
                    <th>測地系</th>
                    <th>年</th>
                    <th>ファイル容量</th>
                    <th>ファイル名</th>
                    <th>ダウンロード</th>
                    <th>一括DL</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="bgc0" id="prefecture00">全国</td>
                    <td class="txtCenter">世界測地系</td>
                    <td class="txtCenter">2025年（令和7年）</td>
                    <td class="txtCenter">603.03MB</td>
                    <td class="txtCenter">N03-20250101_GML.zip</td>
                    <td class="txtCenter">...</td>
                    <td class="txtCenter">...</td>
                </tr>
                <tr>
                    <td class="bgc1" id="prefecture01">北海道</td>
                    <td class="txtCenter">世界測地系</td>
                    <td class="txtCenter">2025年（令和7年）</td>
                    <td class="txtCenter">54.71MB</td>
                    <td class="txtCenter">N03-20250101_01_GML.zip</td>
                    <td class="txtCenter">...</td>
                    <td class="txtCenter">...</td>
                </tr>
                <tr>
                    <td class="bgc2" id="prefecture02">青森県</td>
                    <td class="txtCenter">世界測地系</td>
                    <td class="txtCenter">2024年（令和6年）</td>
                    <td class="txtCenter">7.23MB</td>
                    <td class="txtCenter">N03-20240101_02_GML.zip</td>
                    <td class="txtCenter">...</td>
                    <td class="txtCenter">...</td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    # extract_table_rows()関数が実装されていないので失敗する
    from scripts.update_gyousei_kuiki import extract_table_rows

    rows = extract_table_rows(sample_html)

    # 期待される結果: 各行が{year_display, region_raw, filename}の辞書として返される
    assert len(rows) == 3
    assert rows[0] == {
        "prefecture_id": "prefecture00",
        "year_display": "2025年（令和7年）",
        "region_raw": "全国",
        "filename": "N03-20250101_GML.zip",
    }
    assert rows[1] == {
        "prefecture_id": "prefecture01",
        "year_display": "2025年（令和7年）",
        "region_raw": "北海道",
        "filename": "N03-20250101_01_GML.zip",
    }
    assert rows[2] == {
        "prefecture_id": "prefecture02",
        "year_display": "2024年（令和6年）",
        "region_raw": "青森県",
        "filename": "N03-20240101_02_GML.zip",
    }


# T009: 表示年度と地域名の正規化ロジックを検証するユニットテスト
def test_normalize_year_and_region():
    """年度と地域名の正規化"""
    from scripts.update_gyousei_kuiki import normalize_region, normalize_year

    # 年度正規化: "2025年（令和7年）" → "2025年"
    assert normalize_year("2025年（令和7年）") == "2025年"
    assert normalize_year("2024年（令和6年）") == "2024年"
    assert normalize_year("2023年（令和5年）") == "2023年"

    # specs/002-admin-area-data/spec.md FR-012: 都道府県名の表記を保持する。
    assert normalize_region("全国") == "全国"
    assert normalize_region("北海道") == "北海道"
    assert normalize_region("青森県") == "青森県"
    assert normalize_region("東京都") == "東京都"
    assert normalize_region("京都府") == "京都府"
    assert normalize_region("大阪府") == "大阪府"


# T010: 同一年・同一地域に複数候補がある場合のSHP優先・GML選択ロジックを検証するユニットテスト
def test_select_shp_over_gml():
    """SHP優先、無ければGMLを選択"""
    from scripts.update_gyousei_kuiki import build_collection_structure

    # 生データリスト（同一年・同一地域にSHPとGMLが両方ある場合）
    rows = [
        {
            "year_display": "2025年（令和7年）",
            "region_raw": "全国",
            "filename": "N03-20250101_GML.zip",
        },
        {
            "year_display": "2025年（令和7年）",
            "region_raw": "全国",
            "filename": "N03-20250101_SHP.zip",
        },
        {
            "year_display": "2025年（令和7年）",
            "region_raw": "北海道",
            "filename": "N03-20250101_01_GML.zip",
        },
    ]

    result = build_collection_structure(rows)

    # 期待される結果: 全国はSHPが選択され、北海道はGMLのみ
    assert result["2025年"]["全国"] == "N03-20250101_SHP.zip"
    assert result["2025年"]["北海道"] == "N03-20250101_01_GML.zip"


# T010 追加: JSON構造が期待どおりになることを検証
def test_build_collection_structure():
    """最終的なJSON構造（年度 → 地域 → ファイル名）が期待どおりになる"""
    from scripts.update_gyousei_kuiki import build_collection_structure

    rows = [
        {
            "year_display": "2025年（令和7年）",
            "region_raw": "全国",
            "filename": "N03-20250101_GML.zip",
        },
        {
            "year_display": "2025年（令和7年）",
            "region_raw": "北海道",
            "filename": "N03-20250101_01_GML.zip",
        },
        {
            "year_display": "2024年（令和6年）",
            "region_raw": "青森県",
            "filename": "N03-20240101_02_GML.zip",
        },
    ]

    result = build_collection_structure(rows)

    # 期待される構造
    expected = {
        "2025年": {"全国": "N03-20250101_GML.zip", "北海道": "N03-20250101_01_GML.zip"},
        "2024年": {"青森県": "N03-20240101_02_GML.zip"},
    }

    assert result == expected


# T011: ネットワークエラー・テーブル未検出・書き込み失敗時の終了コード検証
def test_error_handling_exit_codes(tmp_path):
    """エラー時の終了コード検証"""
    import sys

    from scripts.update_gyousei_kuiki import main

    # ネットワークエラー（無効なURL）: 終了コード1
    old_argv = sys.argv
    sys.argv = [
        "update_gyousei_kuiki.py",
        "--url",
        "http://invalid-domain-12345.invalid",
        "--output",
        str(tmp_path / "out.json"),
    ]
    result = main()
    sys.argv = old_argv
    assert result == 1

    # テーブル未検出（空のHTML）: 終了コード2
    empty_html_file = tmp_path / "empty.html"
    empty_html_file.write_text("<html><body>No table here</body></html>")
    sys.argv = [
        "update_gyousei_kuiki.py",
        "--html-file",
        str(empty_html_file),
        "--output",
        str(tmp_path / "out2.json"),
    ]
    result = main()
    sys.argv = old_argv
    assert result == 2

    # 書き込み失敗（読み取り専用ディレクトリ）: 終了コード3
    # NOTE: 環境によって再現が難しいため、この部分はモックで実装する想定
    # NOTE: 環境によって再現が難しいため、この部分はモックで実装する想定
