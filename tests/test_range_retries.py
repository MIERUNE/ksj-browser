"""一時的な配布サーバー障害でも取得済み範囲を保ってレイヤーを追加する。"""

from collections import Counter
import threading
import time

import pytest
from qgis.core import QgsNetworkAccessManager, QgsProject, QgsSettings
from qgis.PyQt.QtCore import QTimer

from ksj import local_storage, remote_zip
from tests.helpers import (
    make_shapefile,
    pump_until,
    run_workers,
    shapefile_entries,
    wait_for_layer_loading,
    zip_bytes,
)
from tests.test_lazy_loading import listing


@pytest.mark.parametrize("status", [502, 503, 504])
def test_double_click_retries_failed_range_and_adds_shapefile(
    qgis_app, qgis_new_project, storage_settings, tmp_path, http_data, status
):
    source = tmp_path / "source"
    source.mkdir()
    shp = make_shapefile(
        source / "N03-20260101.shp", ["行政区域"], "utf-8", cpg="UTF-8"
    )
    http_data.update(
        range_support=True,
        body=zip_bytes(shapefile_entries(shp) + [("unused.bin", b"x" * 200_000)]),
    )
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    item = listing(qgis_app, http_data)[0]
    http_data["ranges"].clear()
    http_data["if_ranges"].clear()
    # 目次を取得した後の先頭範囲に一時的な障害を起こす。
    failed_range = "bytes=0-32767"
    http_data["range_statuses"][failed_range] = [status]
    assert item.handleDoubleClick()
    wait_for_layer_loading(qgis_app)
    layers = list(QgsProject.instance().mapLayers().values())
    assert len(layers) == 1
    assert layers[0].isValid() and layers[0].featureCount() == 1
    assert next(layers[0].getFeatures())["name"] == "行政区域"
    counts = Counter(http_data["ranges"])
    assert counts[failed_range] == 2
    assert all(count == 1 for key, count in counts.items() if key != failed_range)
    assert [
        tag
        for key, tag in zip(http_data["ranges"], http_data["if_ranges"])
        if key == failed_range
    ] == ['"test-v1"', '"test-v1"']
    assert not list(storage_settings.rglob("*.part"))


def test_persistent_server_failure_is_bounded(qgis_app, http_data):
    http_data["status"] = 502
    with pytest.raises(local_storage.DownloadError, match="HTTP 502") as error:
        remote_zip.list_members(http_data["url"])
    assert len(http_data["requests"]) == 3
    assert "部分取得に対応していない" not in str(error.value)


@pytest.mark.parametrize("status", [200, 403, 404, 416])
def test_permanent_http_failure_is_not_retried(qgis_app, http_data, status):
    http_data["status"] = status
    with pytest.raises(local_storage.DownloadError, match=f"HTTP {status}"):
        remote_zip.list_members(http_data["url"])
    assert len(http_data["requests"]) == 1


@pytest.mark.parametrize("worker", [False, True])
def test_cancel_during_retry_wait_does_not_send_another_request(
    qgis_app, http_data, worker
):
    http_data["status"] = 502
    canceled = threading.Event()
    QTimer.singleShot(300, canceled.set)

    def download():
        return remote_zip.list_members(http_data["url"], is_canceled=canceled.is_set)

    with pytest.raises(local_storage.DownloadCanceled):
        if worker:
            run_workers(qgis_app, [download])
        else:
            download()
    # 再試行の予約時刻を過ぎても取消済みの通信が始まらない。
    waited = []
    QTimer.singleShot(1200, lambda: waited.append(True))
    pump_until(qgis_app, lambda: waited, timeout=3)
    assert len(http_data["requests"]) == 1


def test_retry_budget_resets_after_each_successful_range(qgis_app, http_data):
    http_data.update(range_support=True, body=b"abcdefgh")
    http_data["range_statuses"] = {
        "bytes=0-3": [502, 502],
        "bytes=4-7": [502, 502],
    }
    first = remote_zip._range_request(http_data["url"], 0, 3, lambda: False)
    second = remote_zip._range_request(
        http_data["url"], 4, 7, lambda: False, first[1], first[2]
    )
    assert first[0] + second[0] == b"abcdefgh"
    assert Counter(http_data["ranges"]) == {"bytes=0-3": 3, "bytes=4-7": 3}


def test_changed_archive_after_transient_error_is_not_accepted(qgis_app, http_data):
    http_data.update(range_support=True, body=b"abcdefgh")
    http_data["range_statuses"]["bytes=0-3"] = [502]
    with pytest.raises(local_storage.DownloadError, match="更新されました"):
        remote_zip._range_request(
            http_data["url"], 0, 3, lambda: False, 8, b'"previous-version"'
        )
    assert len(http_data["requests"]) == 2


def test_receiving_data_continues_beyond_network_timeout(qgis_app, http_data):
    http_data.update(
        range_support=True, body=b"x" * 32768, chunk_size=4096, chunk_delay=0.25
    )
    previous = QgsNetworkAccessManager.timeout()
    QgsNetworkAccessManager.setTimeout(1000)
    started = time.monotonic()
    try:
        data, size, _ = remote_zip._range_request(
            http_data["url"], 0, 32767, lambda: False
        )
    finally:
        QgsNetworkAccessManager.setTimeout(previous)
    assert time.monotonic() - started > 1
    assert data == b"x" * 32768 and size == 32768
    assert len(http_data["requests"]) == 1
