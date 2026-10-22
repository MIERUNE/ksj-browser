"""配布データを取得・展開して永続保存。レイヤーは通常のファイルを参照する。"""

import hashlib
import os
import re
import stat
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
MAX_ARCHIVE_DEPTH = 8


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


def _validate_response(path):
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


def _entry_parts(entry):
    name = entry.orig_filename
    if not entry.flag_bits & 0x800:
        # 日本の旧ZIPはUTF-8フラグなしでCP932名を保存することがある。
        try:
            name = name.encode("cp437").decode("cp932")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    name = name.replace("\\", "/")
    parts = name.split("/")
    mode = stat.S_IFMT(entry.external_attr >> 16)
    if (
        name.startswith("/")
        or ":" in name
        or "\x00" in name
        or ".." in parts
        or mode not in {0, stat.S_IFREG, stat.S_IFDIR}
    ):
        raise DownloadError(f"ZIPに安全に展開できない項目があります: {name}")
    return [part for part in parts if part not in {"", "."}]


def _extract_zip(archive_path, destination, is_canceled, depth=0):
    if depth > MAX_ARCHIVE_DEPTH:
        raise DownloadError(
            "ZIPの入れ子が深すぎます。公式の配布内容を確認してください。"
        )
    destination.mkdir()
    nested = []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                _check_canceled(is_canceled)
                parts = _entry_parts(entry)
                if not parts:
                    continue
                target = destination.joinpath(*parts)
                if entry.is_dir() or entry.filename.endswith("\\"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                # CRCを読み取り中に検証。重複名・ファイル/フォルダ衝突は上書きしない。
                with archive.open(entry) as source, target.open("xb") as output:
                    while chunk := source.read(VALIDATION_CHUNK_SIZE):
                        _check_canceled(is_canceled)
                        output.write(chunk)
                if target.suffix.lower() == ".zip":
                    nested.append(target)
        for path in nested:
            _check_canceled(is_canceled)
            _extract_zip(
                path, path.with_name(path.name + ".files"), is_canceled, depth + 1
            )
            path.unlink()
    except (
        zipfile.BadZipFile,
        zlib.error,
        EOFError,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise DownloadError(f"ZIPを正常に展開できません: {exc}") from exc


def ensure_local_data(url, directory, is_canceled=None, progress=None) -> str:
    """ZIPは展開済みフォルダ、それ以外はファイルを返す。ワーカーから使用する。"""
    _check_canceled(is_canceled)
    lock = None
    try:
        original = _destination(url, directory)
        zipped = original.suffix.lower() == ".zip"
        target = original.with_suffix("") if zipped else original

        def ready():
            return (
                target.is_dir()
                if zipped
                else target.is_file() and target.stat().st_size > 0
            )

        # 読み取り専用の共有フォルダでも完成済みデータを再利用する。
        if ready():
            return str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(original) + ".lock")
        # 大容量取得の途中でロックが期限切れにならない。終了したプロセスのロックはQtが回収する。
        lock.setStaleLockTime(0)
        while not lock.tryLock(POLL_INTERVAL_MS):
            _check_canceled(is_canceled)
            if lock.error() != QLockFile.LockError.LockFailedError:
                raise DownloadError(f"保存先に書き込めません: {target.parent}")
        _check_canceled(is_canceled)
        if ready():
            return str(target)
        with tempfile.TemporaryDirectory(
            dir=target.parent, prefix="download-", suffix=".part"
        ) as staging:
            temporary = Path(staging) / "download"
            if zipped and original.is_file() and original.stat().st_size:
                # 旧プロジェクトが参照する保存済みZIPは削除せずに再利用する。
                temporary = original
            else:
                _download(
                    url,
                    temporary,
                    is_canceled,
                    (lambda value: progress(value * 0.8))
                    if progress is not None
                    else None,
                )
            _validate_response(temporary)
            if zipped:
                extracted = Path(staging) / "files"
                _extract_zip(temporary, extracted, is_canceled)
                temporary = extracted
            _check_canceled(is_canceled)
            os.replace(temporary, target)
        if progress is not None:
            progress(100)
        return str(target)
    except OSError as exc:
        raise DownloadError(f"データを保存できません: {exc}") from exc
    finally:
        if lock is not None:
            lock.unlock()
