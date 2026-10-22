"""HTTP RangeでZIPの目次を読み、選択したレイヤー一式だけを取得する。"""

import io
import json
import os
import re
import tempfile
import threading
import time
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import (
    QEventLoop,
    QLockFile,
    QObject,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from . import local_storage, zip_scanner
from .local_storage import DownloadError, _check_canceled, _entry_parts

# ZIPのEnd of Central Directory最小長。コメント付きZIPはzipfileが追加で読む。
ZIP_END_SIZE = 22
CHUNK_SIZE = local_storage.VALIDATION_CHUNK_SIZE
MANIFEST = ".ksj-entries.json"
SHAPEFILE_SIDECARS = {
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".qpj",
    ".cpg",
    ".qix",
    ".sbn",
    ".sbx",
    ".fbn",
    ".fbx",
    ".ain",
    ".aih",
    ".ixs",
    ".mxs",
    ".atx",
    ".shp.xml",
}


class _RangeRequests(QObject):
    """通信オブジェクトはGUIスレッドで非同期に扱い、ワーカーへ値だけ返す。"""

    requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.thread_id = threading.get_ident()
        self.active = {}
        self.requested.connect(self.start)

    @pyqtSlot(object)
    def start(self, job):
        try:
            _start_range_request(job)
        except Exception as exc:
            job["error"] = str(exc)
            job["done"].set()


_range_requests = _RangeRequests()


def _range_request(url, start, end, is_canceled, expected_size=None, validator=None):
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise DownloadError("配布URLはHTTPまたはHTTPSで指定してください。")
    _check_canceled(is_canceled)
    job = {
        "args": (url, start, end, expected_size, validator),
        "canceled": threading.Event(),
        "done": threading.Event(),
        "result": None,
        "error": None,
    }
    if threading.get_ident() == _range_requests.thread_id:
        # GUIから直接呼ぶ場合も、通信中はイベントを処理する。
        loop, timer = QEventLoop(), QTimer()

        def poll():
            if is_canceled():
                job["canceled"].set()
            if job["done"].is_set() or job["canceled"].is_set():
                loop.quit()

        timer.timeout.connect(poll)
        timer.start(local_storage.POLL_INTERVAL_MS)
        _range_requests.start(job)
        if not job["done"].is_set():
            loop.exec()
        timer.stop()
    else:
        _range_requests.requested.emit(job)
        # QGIS終了時はGUIがタスク終了を待つため、GUIの応答を待たず取消可能にする。
        while not job["done"].wait(local_storage.POLL_INTERVAL_MS / 1000):
            if is_canceled():
                job["canceled"].set()
                break
    _check_canceled(lambda: job["canceled"].is_set() or is_canceled())
    if job["error"]:
        raise DownloadError(job["error"])
    return job["result"]


def _start_range_request(job):
    """200応答はヘッダー受信時に中止し、全体取得へフォールバックしない。"""
    if job["canceled"].is_set():
        job["done"].set()
        return
    url, start, end, expected_size, validator = job["args"]
    request = QNetworkRequest(QUrl(url))
    request.setAttribute(
        QNetworkRequest.Attribute.RedirectPolicyAttribute,
        QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.CacheLoadControlAttribute,
        QNetworkRequest.CacheLoadControl.AlwaysNetwork,
    )
    request.setAttribute(
        QNetworkRequest.Attribute.AutoDeleteReplyOnFinishAttribute, False
    )
    request.setRawHeader(
        b"Range", f"bytes={'' if start is None else start}-{end}".encode()
    )
    request.setRawHeader(b"Accept-Encoding", b"identity")
    if validator:
        request.setRawHeader(b"If-Range", validator)
    reply = QgsNetworkAccessManager.instance().get(request)
    reply.setReadBufferSize(CHUNK_SIZE)
    errors, metadata = [], []
    data = bytearray()

    def fail(message):
        if not errors:
            errors.append(message)
            reply.abort()

    def headers():
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is None or 300 <= status < 400:
            return
        if status != 206:
            fail(
                f"配布元が部分取得に対応していないか、配布内容が変わりました（HTTP {status}）。"
                "右クリックから配布ファイル全体を取得できます。"
            )
            return
        match = re.fullmatch(
            rb"bytes (\d+)-(\d+)/(\d+)", bytes(reply.rawHeader(b"Content-Range"))
        )
        if not match:
            fail("部分取得の応答範囲を確認できません。")
            return
        first, last, total = map(int, match.groups())
        wanted_first = max(0, total - end) if start is None else start
        wanted_last = total - 1 if start is None else min(end, total - 1)
        if (first, last) != (wanted_first, wanted_last) or first > last:
            fail("部分取得で要求と異なる範囲が返されました。")
            return
        tag = bytes(reply.rawHeader(b"ETag"))
        if not tag or tag.startswith(b"W/"):
            tag = bytes(reply.rawHeader(b"Last-Modified"))
        if (expected_size is not None and total != expected_size) or (
            validator and tag != validator
        ):
            fail("取得中に配布ファイルが更新されました。ZIPを再読み込みしてください。")
            return
        if bytes(reply.rawHeader(b"Content-Encoding")) not in {b"", b"identity"}:
            fail("部分取得の応答がHTTP圧縮されています。")
            return
        metadata[:] = [first, last, total, tag]

    def read():
        if errors:
            return
        if not metadata:
            headers()
        if metadata and not errors:
            data.extend(bytes(reply.readAll()))
            if len(data) > metadata[1] - metadata[0] + 1:
                fail("部分取得で要求した量を超えるデータが返されました。")

    def finished():
        if job["done"].is_set():
            return
        try:
            read()
            if errors:
                job["error"] = errors[0]
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                job["error"] = f"ZIPの部分取得に失敗しました: {reply.errorString()}"
            elif not metadata or len(data) != metadata[1] - metadata[0] + 1:
                job["error"] = "ZIPの部分取得が途中で終了しました。"
            else:
                job["result"] = bytes(data), metadata[2], metadata[3]
        except Exception as exc:
            job["error"] = str(exc)
        finally:
            timer.stop()
            reply.deleteLater()
            timer.deleteLater()
            _range_requests.active.pop(id(job), None)
            job["done"].set()

    timer = QTimer()
    timer.timeout.connect(lambda: reply.abort() if job["canceled"].is_set() else None)
    timer.start(local_storage.POLL_INTERVAL_MS)
    _range_requests.active[id(job)] = (reply, timer)
    reply.metaDataChanged.connect(headers)
    reply.readyRead.connect(read)
    reply.finished.connect(finished)
    if reply.isFinished():
        finished()


class RangeReader(io.RawIOBase):
    """zipfileが要求した範囲だけを読み込むseek可能なHTTPファイル。"""

    def __init__(self, url, is_canceled):
        self.url, self.is_canceled = url, is_canceled
        tail, self.size, self.validator = _range_request(
            url, None, ZIP_END_SIZE, is_canceled
        )
        self.position = 0
        self.tail = tail

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = (
            offset
            + {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[
                whence
            ]
        )
        if position < 0:
            raise OSError("ZIPの読み取り位置が不正です。")
        self.position = position
        return position

    def read(self, size=-1):
        _check_canceled(self.is_canceled)
        end = self.size if size < 0 else min(self.size, self.position + size)
        result = bytearray()
        while self.position < end:
            stop = min(end, self.position + CHUNK_SIZE)
            if self.position >= self.size - len(self.tail):
                chunk = self.tail[
                    self.position - (self.size - len(self.tail)) : stop
                    - (self.size - len(self.tail))
                ]
            else:
                chunk, _, _ = _range_request(
                    self.url,
                    self.position,
                    stop - 1,
                    self.is_canceled,
                    self.size,
                    self.validator,
                )
            result.extend(chunk)
            self.position = stop
        return bytes(result)


def _entries(archive):
    entries, folded = {}, set()
    for entry in archive.infolist():
        parts = _entry_parts(entry)
        if not parts or entry.is_dir() or entry.filename.endswith("\\"):
            continue
        name = "/".join(parts)
        if name.casefold() in folded:
            raise DownloadError(f"ZIP内のファイル名が重複しています: {name}")
        folded.add(name.casefold())
        entries[name] = entry
    return entries


def _original(url, directory):
    if not directory or not Path(directory).is_dir():
        return None
    return local_storage._destination(url, directory)


def _validate_member(member):
    # ブラウザや保存済み目次の名前はすでにUnicodeに復号済み。
    entry = zipfile.ZipInfo(member)
    entry.flag_bits |= 0x800
    parts = _entry_parts(entry)
    if not parts or "/".join(parts) != member:
        raise DownloadError("ZIP内のファイル指定が不正です。")


def saved_member(url, member, directory):
    """Processingの全体保存と、ブラウザの選択保存を通信せず再利用する。"""
    _validate_member(member)
    original = _original(url, directory)
    if original is None:
        return None
    for root in (
        original.with_suffix(""),
        original.parent / "selected" / local_storage.url_key(member),
    ):
        path = root / member
        if path.is_file():
            return str(path)
    return None


def list_members(url, directory="", is_canceled=None):
    is_canceled = is_canceled or (lambda: False)
    original = _original(url, directory)
    if original is not None:
        if original.with_suffix("").is_dir():
            return zip_scanner.list_entries_recursive(str(original.with_suffix("")))
        for manifest in sorted((original.parent / "selected").glob(f"*/{MANIFEST}")):
            try:
                names = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(names, list) and all(
                    isinstance(name, str) for name in names
                ):
                    for name in names:
                        _validate_member(name)
                    return names
            except (OSError, ValueError, DownloadError):
                continue
    try:
        with (
            RangeReader(url, is_canceled) as reader,
            zipfile.ZipFile(reader) as archive,
        ):
            return list(_entries(archive))
    except (OSError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise DownloadError(f"ZIPの一覧を読み込めません: {exc}") from exc


def related_members(member, names):
    """同名・同フォルダの付属ファイルを選択。別レイヤーの本体は含めない。"""
    path = PurePosixPath(member)
    if member not in names:
        raise DownloadError(f"ZIP内のファイルが見つかりません: {member}")
    if path.suffix.lower() == ".vrt":
        raise DownloadError(
            "VRTは他のデータを参照するため、配布ファイル全体を取得して開いてください。"
        )
    suffixes = {path.suffix.lower(), ".prj", ".qpj", ".cpg"}
    if path.suffix.lower() == ".shp":
        suffixes |= SHAPEFILE_SIDECARS
    elif path.suffix.lower() in {".gml", ".xml"}:
        suffixes |= {".xsd", ".gfs"}
    elif path.suffix.lower() == ".csv":
        suffixes |= {".csvt"}
    elif path.suffix.lower() in zip_scanner.RASTER_EXTENSIONS:
        suffixes |= {".tfw", ".tifw", ".wld", ".ige", ".aux", ".rrd"}
    wanted = {path.stem.casefold() + suffix for suffix in suffixes}
    wanted |= {path.name.casefold() + suffix for suffix in (".aux.xml", ".ovr")}
    result = [
        name
        for name in names
        if PurePosixPath(name).parent == path.parent
        and PurePosixPath(name).name.casefold() in wanted
    ]
    # GMLのスキーマは別名・別フォルダで共有されることもある。
    if path.suffix.lower() in {".gml", ".xml"}:
        result.extend(
            name
            for name in names
            if name.lower().endswith(".xsd") and name not in result
        )
    if path.suffix.lower() == ".shp":
        available = {PurePosixPath(name).suffix.lower() for name in result}
        if not {".shp", ".shx", ".dbf"}.issubset(available):
            raise DownloadError(
                "シェイプファイルの .shp・.shx・.dbf が揃っていません。"
            )
    return result


def ensure_member(url, member, directory, is_canceled=None, progress=None):
    """選択した一式をステージングで検証してから確定する。失敗時は再利用しない。"""
    is_canceled = is_canceled or (lambda: False)
    progress = progress or (lambda value: None)
    _check_canceled(is_canceled)
    existing = saved_member(url, member, directory)
    if existing:
        return existing
    original = local_storage._destination(url, directory)
    target = original.parent / "selected" / local_storage.url_key(member)
    lock = QLockFile(str(target) + ".lock")
    lock.setStaleLockTime(0)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + local_storage.LOCK_WAIT_SECONDS
        while not lock.tryLock(local_storage.POLL_INTERVAL_MS):
            _check_canceled(is_canceled)
            if lock.error() != QLockFile.LockError.LockFailedError:
                raise DownloadError(f"保存先に書き込めません: {target.parent}")
            if time.monotonic() >= deadline:
                raise DownloadError(
                    f"同じレイヤーの取得完了を待てませんでした: {target}.lock"
                )
        existing = saved_member(url, member, directory)
        if existing:
            return existing
        with tempfile.TemporaryDirectory(dir=target.parent, suffix=".part") as staging:
            root = Path(staging) / "files"
            root.mkdir()
            with (
                RangeReader(url, is_canceled) as reader,
                zipfile.ZipFile(reader) as archive,
            ):
                entries = _entries(archive)
                selected = related_members(member, entries)
                total = sum(entries[name].file_size for name in selected)
                completed = 0
                for name in selected:
                    _check_canceled(is_canceled)
                    destination = root / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(entries[name]) as source,
                        destination.open("xb") as output,
                    ):
                        while chunk := source.read(CHUNK_SIZE):
                            _check_canceled(is_canceled)
                            output.write(chunk)
                            completed += len(chunk)
                            progress(completed * 100 / max(total, 1))
                (root / MANIFEST).write_text(
                    json.dumps(list(entries), ensure_ascii=False), encoding="utf-8"
                )
            _check_canceled(is_canceled)
            os.replace(root, target)
        return str(target / member)
    except (
        OSError,
        zipfile.BadZipFile,
        zlib.error,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise DownloadError(f"ZIP内のファイルを取得できません: {exc}") from exc
    finally:
        lock.unlock()
