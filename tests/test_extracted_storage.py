"""展開した通常ファイルを永続化し、ZIPに依存しないことを検証する。"""

import stat
import zipfile
from pathlib import Path

import pytest
from osgeo import ogr
from qgis.core import QgsVectorLayer

from ksj import local_storage
from tests.helpers import mock_download, zip_bytes

URL = "https://example.org/data.zip"


def test_extracts_files_and_sidecars_and_reuses_without_zip(tmp_path, monkeypatch):
    entries = [("日本語/roads" + ext, ext) for ext in (".shp", ".dbf", ".shx", ".prj")]
    entries += [("schema.xsd", "<schema/>"), ("README.html", "<html>説明</html>")]
    calls = mock_download(monkeypatch, zip_bytes(entries))
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert root.is_dir()
    for name, contents in entries:
        assert (root / name).read_text() == contents
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))
    assert local_storage.ensure_local_data(URL, str(tmp_path)) == str(root)
    assert calls == [URL]


def test_shapefile_geometry_and_attributes_survive_extraction(
    qgis_app, tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(source))
    layer = dataset.CreateLayer("roads", geom_type=ogr.wkbPoint)
    layer.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetField("name", "test")
    feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (140 40)"))
    assert layer.CreateFeature(feature) == 0
    feature = layer = dataset = None
    mock_download(
        monkeypatch, zip_bytes([(p.name, p.read_bytes()) for p in source.iterdir()])
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    root = Path(local_storage.ensure_local_data(URL, str(saved)))
    loaded = QgsVectorLayer(str(root / "roads.shp"), "roads", "ogr")
    assert loaded.isValid() and loaded.featureCount() == 1
    feature = next(loaded.getFeatures())
    assert feature["name"] == "test"
    assert feature.geometry().asPoint().x() == 140


def test_nested_archives_become_folders(tmp_path, monkeypatch):
    inner = zip_bytes([("table.csv", "name,value\ntest,1\n")])
    mock_download(monkeypatch, zip_bytes([("folder/inner.zip", inner)]))
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / "folder/inner.zip.files/table.csv").is_file()
    assert not list(tmp_path.rglob("*.zip"))


def test_existing_zip_is_extracted_without_download_or_deletion(tmp_path, monkeypatch):
    original = local_storage._destination(URL, str(tmp_path))
    original.parent.mkdir(parents=True)
    original.write_bytes(zip_bytes([("table.csv", "name\ntest\n")]))
    calls = mock_download(monkeypatch, b"must not be requested")
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / "table.csv").read_text() == "name\ntest\n"
    assert original.is_file() and calls == []


@pytest.mark.parametrize(
    "name",
    [
        "../escape.csv",
        "/escape.csv",
        "C:/escape.csv",
        "folder/../../escape.csv",
        "..\\escape.csv",
    ],
)
def test_unsafe_paths_are_rejected_without_completed_data(tmp_path, monkeypatch, name):
    mock_download(monkeypatch, zip_bytes([(name, "data")]))
    with pytest.raises(local_storage.DownloadError):
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert not list(tmp_path.rglob("*.csv"))
    assert not list(tmp_path.rglob("*.zip"))
    assert not list(tmp_path.rglob("*.part"))


def test_symlinks_are_rejected(tmp_path, monkeypatch):
    entry = zipfile.ZipInfo("link")
    entry.create_system = 3
    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    mock_download(monkeypatch, zip_bytes([(entry, "../outside")]))
    with pytest.raises(local_storage.DownloadError):
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert not list(tmp_path.rglob("link"))


@pytest.mark.parametrize(
    "entries",
    [
        [("same.csv", "first"), ("same.csv", "second")],
        [
            ("inner.zip", zip_bytes([("a.csv", "data")])),
            ("inner.zip.files/a.csv", "other"),
        ],
    ],
)
def test_colliding_names_do_not_overwrite(tmp_path, monkeypatch, entries):
    mock_download(monkeypatch, zip_bytes(entries))
    with pytest.raises(local_storage.DownloadError):
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert not list(tmp_path.rglob("*.csv"))


def test_cancel_during_extraction_removes_partial_files(tmp_path, monkeypatch):
    mock_download(monkeypatch, zip_bytes([("large.bin", b"x" * (2 * 1024 * 1024))]))
    with pytest.raises(local_storage.DownloadCanceled):
        local_storage.ensure_local_data(
            URL,
            str(tmp_path),
            is_canceled=lambda: bool(list(tmp_path.rglob("large.bin"))),
        )
    assert not list(tmp_path.rglob("large.bin"))
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize("encoding", ["cp932", "utf-8"])
def test_filename_without_utf8_flag_is_restored(tmp_path, monkeypatch, encoding):
    # 同じ長さのASCII名を差し替え、UTF-8フラグなしのZIPを再現する。
    # 日本の旧ZIPはCP932名、macOSのアーカイブ機能はUTF-8名をフラグなしで書く。
    name = "道路.csv"
    encoded = name.encode(encoding)
    data = zip_bytes([("x" * len(encoded), "name\ntest\n")])
    data = data.replace(b"x" * len(encoded), encoded)
    mock_download(monkeypatch, data)
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / name).read_text() == "name\ntest\n"


def test_stale_staging_folder_is_removed_on_next_download(tmp_path, monkeypatch):
    # 強制終了などで残った作業フォルダは、同じURLのロックを取った時点で回収する。
    mock_download(monkeypatch, zip_bytes([("table.csv", "name\ntest\n")]))
    stale = local_storage._destination(URL, str(tmp_path)).parent / "download-x.part"
    stale.mkdir(parents=True)
    (stale / "download").write_bytes(b"partial")
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / "table.csv").is_file()
    assert not stale.exists()
    assert not list(tmp_path.rglob("*.part"))


def test_storage_folder_is_named_after_distribution_file(tmp_path, monkeypatch):
    # 「保存先を開く」で配布ファイル名から見分けられ、同名の別配布は識別子で分かれる。
    mock_download(monkeypatch, zip_bytes([("table.csv", "name\ntest\n")]))
    roots = [
        Path(local_storage.ensure_local_data(url, str(tmp_path)))
        for url in (URL, "https://example.org/other/data.zip")
    ]
    assert {root.name for root in roots} == {"data"}
    assert all(root.parent.parent == tmp_path for root in roots)
    assert all(root.parent.name.startswith("data-") for root in roots)
    assert roots[0].parent != roots[1].parent
    assert all(
        len(root.parent.name) == len("data-") + local_storage.FOLDER_ID_LENGTH
        for root in roots
    )


def test_lock_held_elsewhere_times_out_with_guidance(tmp_path, monkeypatch):
    from qgis.PyQt.QtCore import QLockFile

    calls = mock_download(monkeypatch, zip_bytes([("table.csv", "name\ntest\n")]))
    monkeypatch.setattr(local_storage, "LOCK_WAIT_SECONDS", 0.3)
    original = local_storage._destination(URL, str(tmp_path))
    original.parent.mkdir(parents=True)
    holder = QLockFile(str(original) + ".lock")
    assert holder.tryLock(0)
    with pytest.raises(local_storage.DownloadError, match="ロック") as info:
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert str(original) + ".lock" in str(info.value)
    assert calls == []
    holder.unlock()
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / "table.csv").is_file() and calls == [URL]


def test_missing_directory_is_not_recreated(tmp_path, monkeypatch):
    # 取り外した外部ドライブなどの保存先を内蔵ディスク側に作り直さない。
    calls = mock_download(monkeypatch, zip_bytes([("table.csv", "name\ntest\n")]))
    missing = tmp_path / "unplugged"
    with pytest.raises(local_storage.DownloadError, match="保存先フォルダ"):
        local_storage.ensure_local_data(URL, str(missing))
    assert not missing.exists() and calls == []


def test_too_deep_nested_archive_is_rejected(tmp_path, monkeypatch):
    data = zip_bytes([("table.csv", "name\ntest\n")])
    for _ in range(10):
        data = zip_bytes([("inner.zip", data)])
    mock_download(monkeypatch, data)
    with pytest.raises(local_storage.DownloadError, match="入れ子"):
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert not list(tmp_path.rglob("*.zip"))


def test_disk_full_cleans_staging_files(tmp_path, monkeypatch):
    mock_download(monkeypatch, zip_bytes([("table.csv", "name\ntest\n")]))
    original_open = Path.open

    def open_file(path, mode="r", *args, **kwargs):
        if path.name == "table.csv" and "x" in mode:
            raise OSError("No space left on device")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(local_storage.DownloadError, match="保存"):
        local_storage.ensure_local_data(URL, str(tmp_path))
    assert not list(tmp_path.rglob("*.part"))
    assert not list(tmp_path.rglob("*.zip"))
