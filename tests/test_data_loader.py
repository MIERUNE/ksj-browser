"""test_data_loader.py

data_loader モジュールの回帰テスト（URL生成の正確性を検証）
"""

from ksj.data_loader import build_download_url, get_shapefile_path_in_zip


def test_build_download_url_2024():
    """2024年のURL生成が正しいこと"""
    url = build_download_url(
        collection_id="dosyasaigai_keikai_kuiki",
        year="2024年",
        filename="A33-24_01_SHP.zip",
    )

    expected = "https://nlftp.mlit.go.jp/ksj/gml/data/A33/A33-24/A33-24_01_SHP.zip"
    assert url == expected


def test_build_download_url_2023():
    """2023年のURL生成が正しいこと"""
    url = build_download_url(
        collection_id="dosyasaigai_keikai_kuiki",
        year="2023年",
        filename="A33-23_02_GML.zip",
    )

    expected = "https://nlftp.mlit.go.jp/ksj/gml/data/A33/A33-23/A33-23_02_GML.zip"
    assert url == expected


def test_get_shapefile_path_in_zip_2024():
    """2024年のZIP内パス取得が正しいこと（ZIP直下）"""
    path = get_shapefile_path_in_zip(year="2024年", filename="A33-24_01_SHP.zip")

    expected = "A33-24_01Polygon.shp"
    assert path == expected


def test_get_shapefile_path_in_zip_2023():
    """2023年のZIP内パス取得が正しいこと（Shape/配下）"""
    path = get_shapefile_path_in_zip(year="2023年", filename="A33-23_02_GML.zip")

    expected = "Shape/A33-23_02Polygon.shp"
    assert path == expected


def test_build_download_url_various_data_ids():
    """異なるデータIDでもURL生成が正しいこと"""
    # A33以外のデータID
    url = build_download_url(
        collection_id="test_collection", year="2024年", filename="P01-24_01_SHP.zip"
    )

    expected = "https://nlftp.mlit.go.jp/ksj/gml/data/P01/P01-24/P01-24_01_SHP.zip"
    assert url == expected


def test_build_download_url_n03_2025():
    """N03(行政区域)はディレクトリが4桁年になること"""
    url = build_download_url(
        collection_id="gyousei_kuiki",
        year="2025年",
        filename="N03-20250101_01_GML.zip",
    )

    expected = (
        "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/N03-20250101_01_GML.zip"
    )
    assert url == expected


def test_build_download_url_n03_old_style_filename():
    """N03の旧形式(YYなど)でも入力yearからディレクトリを決められること"""
    url = build_download_url(
        collection_id="gyousei_kuiki",
        year="2006年",
        filename="N03-06_01_GML.zip",
    )

    expected = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2006/N03-06_01_GML.zip"
    assert url == expected
