"""同じ配布フォルダへの追記・共有ファイル・確定失敗時の復旧を検証する。"""

import io
from pathlib import Path

import pytest

from ksj import local_storage, remote_zip, zip_scanner
from tests.helpers import mock_download, zip_bytes

URL = "https://example.org/data.zip"


@pytest.fixture
def archive(monkeypatch):
    entries = [
        ("first.xml", "<first/>"),
        ("0101/second.xml", "<second/>"),
        ("schema/shared.xsd", "<schema/>"),
    ]
    data = zip_bytes(entries)
    monkeypatch.setattr(remote_zip, "RangeReader", lambda *args: io.BytesIO(data))
    mock_download(monkeypatch, data)
    return entries


def test_shared_schema_keeps_existing_file_and_reuses_both_layers(tmp_path, archive):
    first = Path(remote_zip.ensure_member(URL, "first.xml", str(tmp_path)))
    root = first.parent
    schema = root / "schema/shared.xsd"
    schema.touch()
    before = schema.stat()
    second = Path(remote_zip.ensure_member(URL, "0101/second.xml", str(tmp_path)))
    assert second == root / "0101/second.xml"
    assert schema.stat().st_mtime_ns == before.st_mtime_ns
    assert schema.stat().st_ino == before.st_ino
    assert schema.read_text() == "<schema/>"
    for name, contents in archive:
        assert (root / name).read_text() == contents
    assert remote_zip.saved_member(URL, "first.xml", str(tmp_path)) == str(first)
    assert remote_zip.saved_member(URL, "0101/second.xml", str(tmp_path)) == str(second)
    assert set(zip_scanner.list_entries_recursive(str(root))) == {
        name for name, _ in archive
    }


def test_missing_companion_is_repaired_before_reuse(tmp_path, archive):
    path = Path(remote_zip.ensure_member(URL, "first.xml", str(tmp_path)))
    schema = path.parent / "schema/shared.xsd"
    schema.unlink()
    assert remote_zip.saved_member(URL, "first.xml", str(tmp_path)) is None
    assert remote_zip.ensure_member(URL, "first.xml", str(tmp_path)) == str(path)
    assert schema.read_text() == "<schema/>"


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("failure", ["move", "marker", "cancel"])
def test_failed_publication_preserves_previous_selection_and_can_retry(
    tmp_path, archive, monkeypatch, full, failure
):
    first = Path(remote_zip.ensure_member(URL, "first.xml", str(tmp_path)))
    root = first.parent
    second = root / "0101/second.xml"

    def save(is_canceled=None):
        if full:
            return local_storage.ensure_local_data(URL, str(tmp_path), is_canceled)
        return remote_zip.ensure_member(
            URL, "0101/second.xml", str(tmp_path), is_canceled
        )

    replace = local_storage.os.replace

    def fail(source, destination):
        if (failure == "move" and Path(destination) == second) or (
            failure == "marker" and Path(source).name == "state.json"
        ):
            raise OSError("disk full")
        return replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(local_storage.os, "replace", fail)
        with pytest.raises(local_storage.DownloadError):
            save(lambda: failure == "cancel" and second.exists())
    assert first.read_text() == "<first/>"
    assert (root / "schema/shared.xsd").read_text() == "<schema/>"
    assert not second.exists()
    assert not second.parent.exists()
    assert not list(tmp_path.rglob("*.part"))
    assert remote_zip.saved_member(URL, "first.xml", str(tmp_path)) == str(first)
    assert remote_zip.saved_member(URL, "0101/second.xml", str(tmp_path)) is None
    save()
    assert second.read_text() == "<second/>"


@pytest.mark.parametrize("collision", ["file", "symlink", "directory"])
def test_conflicting_destination_is_not_overwritten(tmp_path, archive, collision):
    first = Path(remote_zip.ensure_member(URL, "first.xml", str(tmp_path)))
    target = first.parent / "0101"
    outside = tmp_path / "outside"
    outside.mkdir()
    if collision == "file":
        target.write_text("keep")
    elif collision == "symlink":
        target.symlink_to(outside, target_is_directory=True)
    else:
        (target / "second.xml").mkdir(parents=True)
    with pytest.raises(local_storage.DownloadError):
        remote_zip.ensure_member(URL, "0101/second.xml", str(tmp_path))
    assert not list(outside.iterdir())
    assert first.read_text() == "<first/>"
    if collision == "file":
        assert target.read_text() == "keep"


def test_archive_cannot_overwrite_storage_metadata(tmp_path, monkeypatch):
    data = zip_bytes([(".ksj/complete", ""), ("point.geojson", "{}")])
    monkeypatch.setattr(remote_zip, "RangeReader", lambda *args: io.BytesIO(data))
    with pytest.raises(local_storage.DownloadError, match="予約名"):
        remote_zip.ensure_member(URL, "point.geojson", str(tmp_path))
    assert not list(tmp_path.rglob("complete"))
    assert not list(tmp_path.rglob("point.geojson"))
