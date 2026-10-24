"""Shapefile の文字コードを取得済みの .dbf から判定する。"""

import pytest
from qgis.core import QgsVectorLayer

from ksj import encoding_check
from tests.helpers import make_shapefile, point_file

TEXTS = ["札幌市中央区", "函館市"]


@pytest.mark.parametrize(
    "encoding,expected", [("cp932", "Shift_JIS"), ("utf-8", "UTF-8")]
)
def test_attribute_bytes_decide_the_encoding(tmp_path, encoding, expected):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, encoding)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_BYTES, True)


def test_attribute_bytes_override_a_wrong_cpg(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932", cpg="UTF-8")
    assert encoding_check.detect_shapefile_encoding(path).encoding == "Shift_JIS"


@pytest.mark.parametrize(
    "cpg,expected",
    [
        ("UTF-8", "UTF-8"),
        ("UTF8", "UTF-8"),
        ("CP932", "Shift_JIS"),
        ("SHIFT_JIS", "Shift_JIS"),
        ("SHIFT-JIS", "Shift_JIS"),
        ("SJIS", "Shift_JIS"),
        ("932", "Shift_JIS"),
    ],
)
def test_ascii_only_attributes_fall_back_to_cpg(tmp_path, cpg, expected):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii", cpg=cpg)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_CPG, False)


@pytest.mark.parametrize("ldid", [0x13, 0x7B])
def test_ascii_only_attributes_fall_back_to_language_id(tmp_path, ldid):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii", ldid=ldid)
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == ("Shift_JIS", encoding_check.REASON_LDID, False)


@pytest.mark.parametrize(
    "folder,expected", [("UTF-8", "UTF-8"), ("Shift_JIS", "Shift_JIS")]
)
def test_ascii_only_attributes_fall_back_to_folder_name(tmp_path, folder, expected):
    directory = tmp_path / "N03-20240101" / folder
    directory.mkdir(parents=True)
    path = make_shapefile(directory / "city.shp", ["Sapporo"], "ascii")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (expected, encoding_check.REASON_FOLDER, False)


def test_undetermined_without_non_ascii_bytes_or_hints(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == (None, encoding_check.UNDETERMINED, False)


def test_undecodable_bytes_fall_back_to_hints_without_confidence(tmp_path):
    # 0x81 の後ろの空白は UTF-8 でも cp932 でも不正。
    path = make_shapefile(tmp_path / "city.shp", [b"\x81 "], "ascii", cpg="CP932")
    detection = encoding_check.detect_shapefile_encoding(path)
    assert detection == ("Shift_JIS", encoding_check.REASON_CPG, False)


def test_missing_dbf_is_reported_as_undetermined(tmp_path):
    detection = encoding_check.detect_shapefile_encoding(tmp_path / "missing.shp")
    assert detection == (None, encoding_check.UNDETERMINED, False)


def test_apply_fixes_cp932_shapefile_without_cpg_and_logs(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(
        encoding_check,
        "log_message",
        lambda message, warning=False: logs.append(message),
    )
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    assert layer.isValid()
    detection = encoding_check.apply_detected_encoding(layer)
    assert detection.encoding == "Shift_JIS"
    assert layer.dataProvider().encoding() in {"Shift_JIS", "CP932"}
    assert [feature["name"] for feature in layer.getFeatures()] == TEXTS
    assert logs == ["文字コードを Shift_JIS と判定して適用: city.shp"]


def test_apply_reads_unicode_shapefile_and_ignores_other_formats(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "utf-8")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    assert encoding_check.apply_detected_encoding(layer).encoding == "UTF-8"
    assert [feature["name"] for feature in layer.getFeatures()] == TEXTS
    geojson = QgsVectorLayer(str(point_file(tmp_path)), "dams", "ogr")
    assert encoding_check.apply_detected_encoding(geojson) is None


def test_apply_leaves_undetermined_layer_untouched(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(
        encoding_check,
        "log_message",
        lambda message, warning=False: logs.append(message),
    )
    path = make_shapefile(tmp_path / "city.shp", ["Sapporo"], "ascii")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    before = layer.dataProvider().encoding()
    assert encoding_check.apply_detected_encoding(layer).encoding is None
    assert layer.dataProvider().encoding() == before
    assert logs == []


def test_source_path_strips_sublayer_suffix(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "utf-8")
    layer = QgsVectorLayer(f"{path}|layername=city", "city", "ogr")
    assert encoding_check.source_path(layer) == path
    assert encoding_check.is_shapefile_layer(layer)


@pytest.mark.parametrize("count,expected", [(19, "Shift_JIS"), (20, None)])
def test_sampling_stops_after_twenty_records(tmp_path, count, expected):
    path = make_shapefile(
        tmp_path / "city.shp", ["ASCII"] * count + ["札幌市"], "cp932"
    )
    assert encoding_check.detect_shapefile_encoding(path).encoding == expected


def test_uppercase_sidecars_are_used_for_fallback(tmp_path):
    path = make_shapefile(tmp_path / "city.shp", ["ASCII"], "ascii", cpg="CP932")
    for suffix in (".dbf", ".cpg"):
        path.with_suffix(suffix).rename(path.with_suffix(suffix.upper()))
    assert encoding_check.detect_shapefile_encoding(path) == (
        "Shift_JIS",
        encoding_check.REASON_CPG,
        False,
    )


@pytest.mark.parametrize("contents", [b"", b"short", bytes(32)])
def test_truncated_or_empty_headers_are_undetermined(tmp_path, contents):
    path = tmp_path / "city.shp"
    path.with_suffix(".dbf").write_bytes(contents)
    assert encoding_check.detect_shapefile_encoding(path).encoding is None


def test_reapplying_detected_encoding_does_not_log_again(tmp_path, monkeypatch):
    path = make_shapefile(tmp_path / "city.shp", TEXTS, "cp932")
    layer = QgsVectorLayer(str(path), "city", "ogr")
    encoding_check.apply_detected_encoding(layer)
    logs = []
    monkeypatch.setattr(encoding_check, "log_message", logs.append)
    encoding_check.apply_detected_encoding(layer)
    assert logs == []


@pytest.mark.parametrize("cpg", [None, "CP932"])
def test_application_preserves_windows_japanese_extensions(tmp_path, cpg):
    texts = ["①髙﨑㈱", "～－―∥￠￡￢"]
    path = make_shapefile(tmp_path / "city.shp", texts, "cp932", cpg=cpg)
    layer = QgsVectorLayer(str(path), "city", "ogr")
    assert encoding_check.apply_detected_encoding(layer).encoding == "Shift_JIS"
    assert [feature["name"] for feature in layer.getFeatures()] == texts
