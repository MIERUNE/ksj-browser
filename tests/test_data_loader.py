"""test_data_loader.py

data_loader モジュールの回帰テスト（URL生成の正確性を検証）
"""

from ksj.data_loader import (
    build_download_url,
    get_data_collection_name,
    get_shapefile_path_in_zip,
    load_data_collections,
)


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


# T019: load_data_collections()がgyousei_kuiki.jsonを読み込む
def test_load_data_collections_includes_gyousei_kuiki():
    """load_data_collections()がgyousei_kuiki.jsonを読み込むこと"""
    collections = load_data_collections()

    # gyousei_kuikiが含まれていること
    assert "gyousei_kuiki" in collections

    # 既存コレクションと同じ構造（year -> region -> filename）
    gyousei_kuiki = collections["gyousei_kuiki"]
    assert isinstance(gyousei_kuiki, dict)

    # 少なくとも1つの年度が含まれていること
    assert len(gyousei_kuiki) > 0

    # 2025年のデータが含まれていること（サンプルチェック）
    if "2025年" in gyousei_kuiki:
        year_2025 = gyousei_kuiki["2025年"]
        assert isinstance(year_2025, dict)
        # 全国と北海道が含まれていること
        assert "全国" in year_2025
        assert "北海道" in year_2025
        # ファイル名がzipであること
        assert year_2025["全国"].endswith(".zip")


# T020: get_data_collection_name()が"gyousei_kuiki"に対して「行政区域」を返す
def test_get_data_collection_name_gyousei_kuiki():
    """get_data_collection_name()がgyousei_kuikiに対して「行政区域」を返すこと"""
    name = get_data_collection_name("gyousei_kuiki")
    assert name == "行政区域"


# T021: build_download_url()がN03のサンプル年度/ファイル名に対して正しいURLを生成する
def test_build_download_url_n03_samples():
    """N03のサンプル年度/ファイル名に対してbuild_download_url()が正しいURLを生成すること"""
    # 2025年全国
    url_2025_zenkoku = build_download_url(
        collection_id="gyousei_kuiki",
        year="2025年",
        filename="N03-20250101_GML.zip",
    )
    assert (
        url_2025_zenkoku
        == "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/N03-20250101_GML.zip"
    )

    # 2024年北海道
    url_2024_hokkaido = build_download_url(
        collection_id="gyousei_kuiki",
        year="2024年",
        filename="N03-20240101_01_GML.zip",
    )
    assert (
        url_2024_hokkaido
        == "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2024/N03-20240101_01_GML.zip"
    )

    # 2023年青森
    url_2023_aomori = build_download_url(
        collection_id="gyousei_kuiki",
        year="2023年",
        filename="N03-20230101_02_GML.zip",
    )
    assert (
        url_2023_aomori
        == "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2023/N03-20230101_02_GML.zip"
    )


# T027: load_data_collections()がgakkou.jsonを読み込む
def test_load_gakkou_collection():
    """load_data_collections()がgakkou.jsonを読み込むこと"""
    collections = load_data_collections()

    # gakkouが含まれていること
    assert "gakkou" in collections

    # 既存コレクションと同じ構造（year -> region -> filename）
    gakkou = collections["gakkou"]
    assert isinstance(gakkou, dict)

    # 少なくとも1つの年度が含まれていること
    assert len(gakkou) > 0

    # 2023年のデータが含まれていること（サンプルチェック）
    if "2023年" in gakkou:
        year_2023 = gakkou["2023年"]
        assert isinstance(year_2023, dict)
        # 全国と北海道が含まれていること
        assert "全国" in year_2023 or "北海道" in year_2023
        # ファイル名がzipであること
        if "北海道" in year_2023:
            assert year_2023["北海道"].endswith(".zip")


# T028: get_data_collection_name()が"gakkou"に対して「学校」を返す
def test_get_gakkou_collection_name():
    """get_data_collection_name()がgakkouに対して「学校」を返すこと"""
    name = get_data_collection_name("gakkou")
    assert name == "学校"


# T029: build_download_url()がP29のサンプル年度/ファイル名に対して正しいURLを生成する
def test_build_gakkou_download_url():
    """P29のサンプル年度/ファイル名に対してbuild_download_url()が正しいURLを生成すること"""
    # 2023年全国
    url_2023_zenkoku = build_download_url(
        collection_id="gakkou",
        year="2023年",
        filename="P29-23_GML.zip",
    )
    assert (
        url_2023_zenkoku
        == "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_GML.zip"
    )

    # 2023年北海道
    url_2023_hokkaido = build_download_url(
        collection_id="gakkou",
        year="2023年",
        filename="P29-23_01_GML.zip",
    )
    assert (
        url_2023_hokkaido
        == "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-23/P29-23_01_GML.zip"
    )

    # 2021年青森
    url_2021_aomori = build_download_url(
        collection_id="gakkou",
        year="2021年",
        filename="P29-21_02_GML.zip",
    )
    assert (
        url_2021_aomori
        == "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-21/P29-21_02_GML.zip"
    )

    # 2013年SHP形式（ファイル名から2桁年を抽出）
    url_2013_hokkaido = build_download_url(
        collection_id="gakkou",
        year="2013年",
        filename="P29-13_01.zip",
    )
    assert (
        url_2013_hokkaido
        == "https://nlftp.mlit.go.jp/ksj/gml/data/P29/P29-13/P29-13_01.zip"
    )
