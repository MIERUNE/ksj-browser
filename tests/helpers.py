"""テスト間で共有する補助関数。"""

import io
import time
import zipfile

from ksj import local_storage


def zip_bytes(entries, **zip_options):
    """[(エントリ名, 内容), ...] をメモリ上のZIPにする。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", **zip_options) as archive:
        for name, contents in entries:
            archive.writestr(name, contents)
    return buffer.getvalue()


def mock_download(monkeypatch, data):
    """取得を固定データに差し替え、要求されたURLの一覧を返す。"""
    calls = []

    def download(url, destination, *args):
        calls.append(url)
        destination.write_bytes(data)

    monkeypatch.setattr(local_storage, "_download", download)
    return calls


def pump_until(app, predicate, timeout, interval=0.01):
    """イベントを処理しながら条件が成り立つまで待つ。"""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(interval)
    assert predicate(), "時間内に条件を満たしませんでした"
