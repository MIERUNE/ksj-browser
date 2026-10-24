"""配布データを取得・展開して永続保存。レイヤーは通常のファイルを参照する。"""

import hashlib
import os
import re
import shutil
import stat
import tempfile
import time
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

from qgis import utils
from qgis.core import QgsFileDownloader, QgsSettings
from qgis.PyQt.QtCore import QObject, QEventLoop, QLockFile, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from .zip_scanner import STORAGE_METADATA

DIRECTORY_KEY = "ksj/download_directory"
MODE_KEY = "ksj/loading_mode"
POLL_INTERVAL_MS = 100
# 保存フォルダ名に付ける識別子の長さ。配布ファイル名だけでは同名の別配布を区別できない。
FOLDER_ID_LENGTH = 12
# 同じデータを別の処理が取得中なら完了を待つ。他ホストで中断されたロックで固まらない。
LOCK_WAIT_SECONDS = 5 * 60
VALIDATION_CHUNK_SIZE = 1024 * 1024
MAX_ARCHIVE_DEPTH = 8
# 進捗のうち取得に割り当てる割合。残りは展開と確定に充てる。
DOWNLOAD_PROGRESS_SHARE = 0.8
COMPLETE_MARKER = "complete"


class LoadingSettingsSignals(QObject):
    changed = pyqtSignal()


loading_settings_signals = LoadingSettingsSignals()


class DownloadError(Exception):
    """保存・取得失敗の利用者向け説明。"""


class DownloadCanceled(DownloadError):
    """途中ファイルを破棄して取得を中止した。"""


def download_directory() -> str:
    """利用者が指定した保存先。未設定なら空文字列。"""
    return QgsSettings().value(DIRECTORY_KEY, "", type=str)


def loading_mode() -> str:
    """既存利用者は保存方式を引き継ぐ。設定は追加操作のたびに参照する。"""
    value = QgsSettings().value(MODE_KEY, "save", type=str)
    return value if value in {"save", "temporary"} else "save"


class LoadingSettingsDialog(QDialog):
    """追加方法と保存先を一度に設定し、取消時はどちらも変更しない。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("国土数値情報の追加方法・保存先")
        layout = QVBoxLayout(self)
        self.save = QRadioButton("フォルダに保存して追加")
        self.temporary = QRadioButton("一時レイヤーとして追加")
        layout.addWidget(self.save)
        row = QHBoxLayout()
        self.directory = QLineEdit(download_directory())
        self.directory.setPlaceholderText("保存先フォルダ")
        self.directory.setAccessibleName("保存先フォルダ")
        browse = QPushButton("参照…")
        row.addWidget(self.directory)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(self.temporary)
        note = QLabel(
            "ダブルクリックやドラッグで追加するときに、この設定を使います。\n"
            "一時レイヤーは一時ファイルを参照し、レイヤーを閉じると削除します。"
            "残す場合は別途保存してください。"
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        def choose():
            selected = QFileDialog.getExistingDirectory(
                self, "国土数値情報の保存先", self.directory.text()
            )
            if selected:
                self.directory.setText(selected)

        def sync_directory_inputs(enabled):
            self.directory.setEnabled(enabled)
            browse.setEnabled(enabled)

        browse.clicked.connect(choose)
        self.save.toggled.connect(sync_directory_inputs)
        mode = loading_mode()
        self.save.setChecked(mode == "save")
        self.temporary.setChecked(mode == "temporary")
        sync_directory_inputs(self.save.isChecked())

    def accept(self):
        if self.save.isChecked():
            if not self.directory.text().strip():
                QMessageBox.warning(
                    self, "保存先が未設定です", "保存先フォルダを選択してください。"
                )
                return
            if _remember_directory(self.directory.text(), self) is None:
                return
        QgsSettings().setValue(
            MODE_KEY, "save" if self.save.isChecked() else "temporary"
        )
        loading_settings_signals.changed.emit()
        super().accept()


def configure_loading(parent=None) -> bool:
    dialog = LoadingSettingsDialog(parent if parent is not None else main_window())
    return dialog.exec() == QDialog.DialogCode.Accepted


def main_window():
    """ダイアログの親。ヘッドレス環境やテストではNone。"""
    return utils.iface.mainWindow() if utils.iface is not None else None


def choose_download_directory(parent=None) -> str:
    """GUIスレッドで保存先を一度選ぶ。取消・失敗時は設定を変更しない。"""
    if parent is None:
        parent = main_window()
    selected = QFileDialog.getExistingDirectory(
        parent, "国土数値情報の保存先（次回からは自動で再利用）", download_directory()
    )
    if not selected:
        return ""
    directory = _remember_directory(selected, parent)
    if directory is None:
        return ""
    loading_settings_signals.changed.emit()
    return directory


def _remember_directory(text, parent):
    """書き込めることを確かめてから保存先を記憶する。失敗時は警告して None。"""
    try:
        directory = Path(text).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        QMessageBox.warning(parent, "保存先を設定できません", str(exc))
        return None
    QgsSettings().setValue(DIRECTORY_KEY, str(directory))
    return str(directory)


def url_key(url, length=16):
    """URLから安定した短い識別子を作る。保存フォルダ名やブラウザのパスに使う。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:length]


def _destination(url, directory):
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise DownloadError("配布URLはHTTPまたはHTTPSで指定してください。")
    if not directory:
        raise DownloadError("国土数値情報の保存先を選択してください。")
    base = Path(directory).expanduser().resolve()
    if not base.is_dir():
        # 取り外した外部ドライブなどの保存先を内蔵ディスク側に作り直さない。
        raise DownloadError(
            f"保存先フォルダが見つかりません: {base} — "
            "右クリックから保存先を設定し直してください。"
        )
    # URLの区切りやOSの予約文字を持ち込まない。
    filename = re.sub(r"[^\w.\-]", "_", unquote(parts.path.rsplit("/", 1)[-1]))
    filename = filename.strip(". ") or "download"
    # 利用者が配布ファイル名で見分けられるフォルダにし、同名の別配布・クエリ違いは
    # URLの短い識別子で区別する。
    identifier = url_key(url, FOLDER_ID_LENGTH)
    return base / f"{Path(filename).stem}-{identifier}" / filename


def _check_canceled(is_canceled):
    if is_canceled():
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
        if total > 0:
            progress(current * 100 / total)

    downloader.downloadProgress.connect(report)
    timer = QTimer()

    def cancel_if_requested():
        if is_canceled():
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
        # UTF-8フラグなしの名前はcp437で読まれる（可逆）。macOS等のUTF-8名、
        # 日本の旧ZIPのCP932名の順に復元する。UTF-8は厳密なので誤判定しにくい。
        raw = name.encode("cp437")
        for encoding in ("utf-8", "cp932"):
            try:
                name = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
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
    parts = [part for part in parts if part not in {"", "."}]
    if parts and parts[0].casefold() == STORAGE_METADATA:
        raise DownloadError(f"ZIPに保存管理用の予約名が含まれています: {name}")
    return parts


def _metadata(root):
    return root / STORAGE_METADATA


def is_complete(root) -> bool:
    """配布ファイル全体を展開済みか。"""
    return (_metadata(root) / COMPLETE_MARKER).is_file()


@contextmanager
def _distribution_lock(root, is_canceled):
    """配布単位のロックを保持する。保持中は同じURLの取得が他にない。"""
    metadata = _metadata(root)
    metadata.mkdir(parents=True, exist_ok=True)
    lock_path = metadata / "download.lock"
    lock = QLockFile(str(lock_path))
    # 大容量取得の途中でロックが期限切れにならない。同一ホストで終了したプロセスの
    # ロックはQtが回収するが、他ホストや取り外した共有先のロックは残るため上限を設ける。
    lock.setStaleLockTime(0)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    try:
        while not lock.tryLock(POLL_INTERVAL_MS):
            _check_canceled(is_canceled)
            if lock.error() != QLockFile.LockError.LockFailedError:
                raise DownloadError(f"保存先に書き込めません: {root}")
            if time.monotonic() >= deadline:
                raise DownloadError(
                    "同じデータを別の処理が取得中か、中断された取得のロックが残っています。"
                    "完了を待って再読み込みするか、次のファイルを削除してください: "
                    f"{lock_path}"
                )
        _check_canceled(is_canceled)
        yield
    finally:
        lock.unlock()


def _staging(root):
    """ロック保持中に使う作業フォルダ。強制終了で残った作業フォルダは先に回収する。"""
    metadata = _metadata(root)
    for stale in metadata.glob("download-*.part"):
        shutil.rmtree(stale, ignore_errors=True)
    return tempfile.TemporaryDirectory(dir=metadata, prefix="download-", suffix=".part")


def _write_entry(archive, entry, target, is_canceled, report=None):
    """ZIPの1項目を書き出す。CRCを読み取り中に検証し、既存ファイルは上書きしない。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(entry) as source, target.open("xb") as output:
        while chunk := source.read(VALIDATION_CHUNK_SIZE):
            _check_canceled(is_canceled)
            output.write(chunk)
            if report is not None:
                report(len(chunk))


def _publish_files(source, target, marker, contents, is_canceled):
    """検証済みファイルを統合し、完了情報を最後に確定する。配布単位のロック下で使用。"""
    added, directories = [], []
    try:
        for path in sorted(source.rglob("*")):
            _check_canceled(is_canceled)
            destination = target / path.relative_to(source)
            # 保存済みフォルダに利用者が置いたリンクも辿らない。
            if destination.is_symlink():
                raise DownloadError(
                    f"保存先にシンボリックリンクがあります: {destination}"
                )
            if path.is_dir():
                if not destination.exists():
                    destination.mkdir()
                    directories.append(destination)
                elif not destination.is_dir():
                    raise DownloadError(
                        f"保存先のファイルとフォルダが衝突しています: {destination}"
                    )
            elif destination.exists():
                if not destination.is_file():
                    raise DownloadError(
                        f"保存先のファイルとフォルダが衝突しています: {destination}"
                    )
                # 他レイヤーの共有スキーマやQGISが使用中のファイルを置き換えない。
            else:
                os.replace(path, destination)
                added.append(destination)
        _check_canceled(is_canceled)
        pending = source.parent / "state.json"
        pending.write_text(contents, encoding="utf-8")
        os.replace(pending, marker)
    except Exception:
        for path in reversed(added):
            path.unlink()
        for path in reversed(directories):
            path.rmdir()
        raise


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
                _write_entry(archive, entry, target, is_canceled)
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
    is_canceled = is_canceled or (lambda: False)
    progress = progress or (lambda value: None)
    _check_canceled(is_canceled)
    try:
        original = _destination(url, directory)
        zipped = original.suffix.lower() == ".zip"
        root = original.parent
        target = root if zipped else original

        def ready():
            return (
                is_complete(root)
                if zipped
                else target.is_file() and target.stat().st_size > 0
            )

        # 読み取り専用の共有フォルダでも完成済みデータを再利用する。
        if ready():
            return str(target)
        with _distribution_lock(root, is_canceled):
            if ready():
                return str(target)
            with _staging(root) as staging:
                temporary = Path(staging) / "download"
                _download(
                    url,
                    temporary,
                    is_canceled,
                    lambda value: progress(value * DOWNLOAD_PROGRESS_SHARE),
                )
                _validate_response(temporary)
                if zipped:
                    extracted = Path(staging) / "files"
                    _extract_zip(temporary, extracted, is_canceled)
                    _publish_files(
                        extracted,
                        target,
                        _metadata(root) / COMPLETE_MARKER,
                        "",
                        is_canceled,
                    )
                else:
                    _check_canceled(is_canceled)
                    os.replace(temporary, target)
        progress(100)
        return str(target)
    except OSError as exc:
        raise DownloadError(f"データを保存できません: {exc}") from exc
