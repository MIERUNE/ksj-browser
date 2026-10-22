import importlib
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from qgis.core import QgsApplication, QgsSettings

from ksj import catalog, local_storage
from tests.helpers import point_geojson, zip_bytes


def pytest_configure():
    """Configure pytest environment for tests.

    Add project root to sys.path for imports.

    Note: QGIS environment variables (DYLD_LIBRARY_PATH, PROJ_LIB, GDAL_DATA)
    must be set BEFORE running pytest, as pytest-qgis imports QGIS at plugin
    load time. Use: source setup_qgis_env.sh
    """

    # Add project root to sys.path
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, os.fspath(project_root))


@pytest.fixture
def storage_settings(qgis_app, tmp_path, monkeypatch):
    """保存先・追加方法の設定を試験用キーに退避し、未作成の保存先候補を返す。"""
    key = "ksj-tests/download-directory"
    monkeypatch.setattr(local_storage, "DIRECTORY_KEY", key)
    monkeypatch.setattr(local_storage, "MODE_KEY", key + "-mode")
    QgsSettings().remove(key)
    QgsSettings().remove(local_storage.MODE_KEY)
    yield tmp_path / "保存データ"
    QgsSettings().remove(key)
    QgsSettings().remove(local_storage.MODE_KEY)


@pytest.fixture
def http_data():
    body = zip_bytes([("point.geojson", point_geojson("test", 140, 40))])
    state = {
        "body": body,
        "requests": [],
        "status": 200,
        "delay": 0,
        "ranges": [],
        "bytes_sent": 0,
        "range_support": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            body = state["body"]
            requested = self.headers.get("Range")
            state["ranges"].append(requested)
            if state["range_support"] and requested and state["status"] == 200:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
                start, end = match.groups()
                start, end = (
                    (int(start), min(int(end), len(body) - 1))
                    if start
                    else (max(0, len(body) - int(end)), len(body) - 1)
                )
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
                self.send_header("ETag", '"test-v1"')
                body = body[start : end + 1]
            else:
                self.send_response(state["status"])
            self.send_header("Content-Length", str(state.get("length", len(body))))
            self.end_headers()
            time.sleep(state["delay"])
            try:
                self.wfile.write(body)
                state["bytes_sent"] += len(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}/data.zip"
    yield state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def processing_provider(qgis_app, monkeypatch):
    import qgis

    # macOS同梱PythonではpkgDataPathが実際のResourcesとずれる場合がある。
    candidates = [Path(QgsApplication.pkgDataPath()) / "python" / "plugins"]
    candidates.extend(
        parent / "Resources" / "python" / "plugins"
        for parent in Path(qgis.__file__).resolve().parents
    )
    for path in candidates:
        if (path / "processing").is_dir():
            monkeypatch.syspath_prepend(str(path))
            break
    from processing.core.Processing import Processing
    from ksj.processing_provider import KsjProcessingProvider

    Processing.initialize()
    provider = KsjProcessingProvider()
    registry = QgsApplication.processingRegistry()
    assert registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


@pytest.fixture
def sample_catalog(tmp_path, monkeypatch):
    directory = tmp_path / "catalog"
    directory.mkdir()
    records = [
        {
            "id": "dams",
            "title": "ダム（ポイント）",
            "category": "水域",
            "edition": "現行形式",
            "license": "非商用",
            "source_url": "https://example.org/dams",
            "resource_count": 3,
        },
        {
            "id": "old-dams",
            "title": "旧ダム",
            "category": "水域",
            "edition": "旧形式",
            "resource_count": 0,
        },
    ]
    resources = [
        {
            "url": "https://example.org/dams.zip",
            "filename": "dams.zip",
            "year": "2024年",
            "region": "東京都",
            "format": "SHP",
            "metadata": {"測地系": "世界測地系"},
            "source_url": "https://example.org/2024",
        },
        {
            "url": "https://example.org/old.zip",
            "filename": "old.zip",
            "year": "2020年",
            "region": "全国",
            "format": "GML",
            "metadata": {},
        },
        {
            "url": "https://example.org/old.lzh",
            "filename": "old.lzh",
            "year": "",
            "region": "",
            "format": "",
            "metadata": {},
        },
    ]
    (directory / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "2026-10-22",
                "datasets": records,
            }
        ),
        encoding="utf-8",
    )
    (directory / "dams.json").write_text(
        json.dumps({**records[0], "resources": resources}), encoding="utf-8"
    )
    monkeypatch.setattr(catalog, "CATALOG_DIR", directory)
    return resources


@pytest.fixture
def dialogs(processing_provider, monkeypatch):
    # pytest-qgisのifaceスタブにはbrowserModelがない。標準パネルをヘッドレスで作る。
    monkeypatch.setattr(
        importlib.import_module("processing.gui.ParametersPanel"), "iface", None
    )
    opened = []

    def create(name):
        algorithm = (
            QgsApplication.processingRegistry().algorithmById("ksj:" + name).create()
        )
        dialog = algorithm.createCustomParametersWidget(None)
        assert dialog is not None, "選択式のProcessing画面が必要"
        opened.append(dialog)
        return dialog

    yield create
    for dialog in opened:
        dialog.close()
        dialog.deleteLater()
