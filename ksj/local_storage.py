"""配布原本の永続保存。通信は未取得時だけ、レイヤーはローカルファイルだけを参照する。"""

import hashlib
import os
import re
import tempfile
import zipfile
import zlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

from qgis.core import QgsFileDownloader, QgsSettings
from qgis.PyQt.QtCore import QEventLoop, QLockFile, QTimer, QUrl
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

DIRECTORY_KEY = "ksj/download_directory"
POLL_INTERVAL_MS = 100
VALIDATION_CHUNK_SIZE = 1024 * 1024


class DownloadError(Exception):
    """保存・取得失敗の利用者向け説明。"""


class DownloadCanceled(DownloadError):
    """途中ファイルを破棄して取得を中止した。"""


def download_directory() -> str:
    """利用者が指定した保存先。未設定なら空文字列。"""
    return QgsSettings().value(DIRECTORY_KEY, "", type=str)


def choose_download_directory(parent=None) -> str:
    """GUIスレッドで保存先を一度選ぶ。取消・失敗時は設定を変更しない。"""
    selected = QFileDialog.getExistingDirectory(
        parent, "国土数値情報の保存先（次回からは自動で再利用）", download_directory()
    )
    if not selected:
        return ""
    try:
        directory = Path(selected).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        QMessageBox.warning(parent, "保存先を設定できません", str(exc))
        return ""
    QgsSettings().setValue(DIRECTORY_KEY, str(directory))
    return str(directory)


def _destination(url, directory):
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise DownloadError("配布URLはHTTPまたはHTTPSで指定してください。")
    if not directory:
        raise DownloadError("国土数値情報の保存先を選択してください。")
    # 同名配布・クエリ違いを混同しない。URLの区切りやOSの予約文字を持ち込まない。
    filename = re.sub(r"[^\w.\-]", "_", unquote(parts.path.rsplit("/", 1)[-1]))
    filename = filename.strip(". ") or "download"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path(directory).expanduser().resolve() / digest / filename


def _check_canceled(is_canceled):
    if is_canceled is not None and is_canceled():
        raise DownloadCanceled("ダウンロードを中止しました。")


def _download(url, destination, is_canceled, progress):
    """ワーカーのイベントループで逐次保存。QGISのプロキシ・TLS設定を利用する。"""
    loop = QEventLoop()
    completed, errors, received = [], [], []
    downloader = QgsFileDownloader(QUrl(url), str(destination), delayStart=True)
    downloader.downloadCompleted.connect(lambda: completed.append(True))
    downloader.downloadError.connect(errors.extend)
    downloader.downloadExited.connect(loop.quit)

    def report(current, total):
        received[:] = [current, total]
        if progress is not None and total > 0:
            progress(current * 100 / total)

    downloader.downloadProgress.connect(report)
    timer = QTimer()

    def cancel_if_requested():
        if is_canceled is not None and is_canceled():
            timer.stop()
            downloader.cancelDownload()

    timer.timeout.connect(cancel_if_requested)
    timer.start(POLL_INTERVAL_MS)
    # PythonワーカーではsingleShotにC++のメソッドを渡さず、そのスレッドで開始する。
    downloader.startDownload()
    loop.exec()
    timer.stop()
    _check_canceled(is_canceled)
    if not completed or errors:
        raise DownloadError("ダウンロードに失敗しました: " + " / ".join(errors))
    if received and received[1] >= 0 and received[0] != received[1]:
        raise DownloadError("ダウンロードが途中で終了しました。再試行してください。")


def _validate(path, suffix, is_canceled):
    if path.stat().st_size == 0:
        raise DownloadError(
            "空のファイルが返されました。公式の配布状況を確認してください。"
        )
    with path.open("rb") as source:
        prefix = source.read(1024).removeprefix(b"\xef\xbb\xbf").lstrip().lower()
    # ZIP内の説明書や属性値にHTMLが含まれていても、応答そのものと混同しない。
    if prefix.startswith((b"<html", b"<!doctype html")):
        raise DownloadError(
            "データの代わりにHTMLが返されました。公式ページを確認してください。"
        )
    if suffix == ".zip":
        try:
            # CRCも確認する。解凍した内容は保存せず、メモリ使用量を制限する。
            with zipfile.ZipFile(path) as archive:
                for entry in archive.infolist():
                    _check_canceled(is_canceled)
                    if entry.is_dir():
                        continue
                    with archive.open(entry) as source:
                        while source.read(VALIDATION_CHUNK_SIZE):
                            _check_canceled(is_canceled)
        except (
            zipfile.BadZipFile,
            zlib.error,
            EOFError,
            RuntimeError,
            NotImplementedError,
        ) as exc:
            raise DownloadError(f"ZIPを正常に読み取れません: {exc}") from exc


def ensure_local_file(url, directory, is_canceled=None, progress=None) -> str:
    """完成済み原本を再利用し、なければ取得する。UIを呼ばずワーカーから使用する。"""
    _check_canceled(is_canceled)
    lock = None
    temporary = None
    try:
        target = _destination(url, directory)
        # 読み取り専用の共有フォルダでも、取得済みの原本を利用できる。
        if target.is_file() and target.stat().st_size:
            return str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(target) + ".lock")
        # 大容量取得の途中でロックが期限切れにならない。終了したプロセスのロックはQtが回収する。
        lock.setStaleLockTime(0)
        while not lock.tryLock(POLL_INTERVAL_MS):
            _check_canceled(is_canceled)
            if lock.error() != QLockFile.LockError.LockFailedError:
                raise DownloadError(f"保存先に書き込めません: {target.parent}")
        _check_canceled(is_canceled)
        if target.is_file() and target.stat().st_size:
            return str(target)
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix="download-", suffix=".part", delete=False
        ) as output:
            temporary = Path(output.name)
        _download(url, temporary, is_canceled, progress)
        _validate(temporary, target.suffix.lower(), is_canceled)
        _check_canceled(is_canceled)
        os.replace(temporary, target)
        return str(target)
    except OSError as exc:
        raise DownloadError(f"データを保存できません: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if lock is not None:
            lock.unlock()
