"""展開した通常ファイルを永続化し、ZIPに依存しないことを検証する。"""

import io
import stat
import zipfile
from pathlib import Path

import pytest
from osgeo import ogr
from qgis.core import QgsVectorLayer

from ksj import local_storage

URL = "https://example.org/data.zip"


def zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, contents in entries:
            archive.writestr(name, contents)
    return buffer.getvalue()


def mock_download(monkeypatch, data):
    calls = []

    def download(url, destination, *args):
        calls.append(url)
        destination.write_bytes(data)

    monkeypatch.setattr(local_storage, "_download", download)
    return calls


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
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path / "saved")))
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
        local_storage.ensure_local_data(URL, str(tmp_path / "saved"))
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


def test_cp932_filename_is_restored(tmp_path, monkeypatch):
    # 同じ長さのASCII名を差し替え、UTF-8フラグなしの旧形式ZIPを再現する。
    name = "道路.csv"
    encoded = name.encode("cp932")
    data = zip_bytes([("x" * len(encoded), "name\ntest\n")])
    data = data.replace(b"x" * len(encoded), encoded)
    mock_download(monkeypatch, data)
    root = Path(local_storage.ensure_local_data(URL, str(tmp_path)))
    assert (root / name).read_text() == "name\ntest\n"


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
