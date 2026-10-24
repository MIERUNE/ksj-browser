"""ブラウザの追加操作をタスク化し、記憶した保存方式でレイヤーを追加する。"""

import json
import tempfile
from collections import namedtuple
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsMessageLog,
    QgsMimeDataUtils,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer,
)
from qgis.gui import QgsCustomDropHandler
from qgis.PyQt.QtCore import QObject, pyqtSignal

from . import local_storage, remote_zip, zip_scanner
from .local_storage import DownloadError
from .mesh_index import notify

DROP_KEY = "ksj-layer"
# 同じファイルでも追加方法・保存先が違えば別のタスクとして並行させる。
LoadKey = namedtuple("LoadKey", "url member mode directory")
pending = {}


class LoadingSignals(QObject):
    """ブラウザ項目を保持せず、GUIへ読み込み状態の変化を伝える。"""

    changed = pyqtSignal()


loading_signals = LoadingSignals()


def is_loading(url, member):
    """設定を変えて並行追加した場合は、最後のタスクまで待機表示を保つ。"""
    return any(key.url == url and key.member == member for key in pending)


def _is_current(task):
    """取消や再開始で置き換えられたタスクは、結果も待機表示も対象外にする。"""
    return pending.get(task.key) is task


def _register(task):
    pending[task.key] = task
    loading_signals.changed.emit()


def _unregister(task):
    if _is_current(task):
        del pending[task.key]
        loading_signals.changed.emit()


def drop_uri(url, member, name):
    """ドラッグ中は通信せず、ドロップ後に start() へ渡す値だけを運ぶ。"""
    uri = QgsMimeDataUtils.Uri()
    uri.layerType = "custom"
    uri.providerKey = DROP_KEY
    uri.name = name
    uri.uri = json.dumps({"url": url, "member": member, "name": name})
    return uri


def prepare(task, url, member, name, mode, directory):
    """ワーカーで必要なファイルのみ取得。QGISプロジェクトには触れない。"""
    temporary = (
        tempfile.TemporaryDirectory(prefix="ksj-layer-")
        if mode == "temporary"
        else None
    )
    try:
        destination = temporary.name if temporary else directory
        if member:
            # 一時レイヤーでも、保存済みの選択データがあれば通信せず再利用する。
            saved = (
                remote_zip.saved_member(url, member, directory) if temporary else None
            )
            path = saved or remote_zip.ensure_member(
                url, member, destination, task.isCanceled, task.setProgress
            )
        else:
            path = local_storage.ensure_local_data(
                url, destination, task.isCanceled, task.setProgress
            )
        local_storage._check_canceled(task.isCanceled)
        if zip_scanner.provider_key(path) == "gdal":
            layers = [("gdal", path, name)]
        elif Path(path).suffix.lower() in zip_scanner.MULTILAYER_EXTENSIONS:
            provider = QgsProviderRegistry.instance().providerMetadata("ogr")
            layers = [
                ("ogr", sublayer.uri(), sublayer.name())
                for sublayer in provider.querySublayers(path)
            ]
        else:
            layers = [("ogr", path, name)]
        if not layers:
            raise DownloadError("追加可能なレイヤーがありません。")
        return {"layers": layers, "temporary": temporary}
    except Exception:
        if temporary:
            temporary.cleanup()
        raise


def _cleanup(workspace):
    """レイヤー破棄のスロット内で例外を出さない。失敗分はOSの一時領域掃除に任せる。"""
    try:
        workspace.cleanup()
    except OSError as exc:
        QgsMessageLog.logMessage(
            f"一時ファイルを削除できません: {workspace.name} ({exc})",
            "KSJ",
            Qgis.MessageLevel.Warning,
        )


def _release_when_closed(workspace, layers):
    """一時ディレクトリを、そこから生成したレイヤーがすべて閉じられるまで保つ。"""
    remaining = [len(layers)]

    def release(obj=None):
        remaining[0] -= 1
        if remaining[0] == 0:
            _cleanup(workspace)

    if not layers:
        _cleanup(workspace)
    for layer in layers:
        layer.destroyed.connect(release)


def _finish(task):
    """GUIスレッドでレイヤーを追加する。取消済み・置き換えられたタスクの結果は捨てる。"""
    result = task.result
    workspace = result["temporary"] if result else None
    try:
        if not _is_current(task):
            return
        if task.isCanceled():
            return
        if task.error is not None:
            notify(f"レイヤーを追加できません: {task.error}", warning=True)
            return
        if result is None:
            return
        added, failed = [], []
        for provider, source, title in result["layers"]:
            layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
            layer = layer_type(source, title, provider)
            if not layer.isValid():
                failed.append(title)
                continue
            QgsProject.instance().addMapLayer(layer)
            added.append(layer)
        if failed:
            notify(f"読み込めないレイヤー: {', '.join(failed)}", warning=True)
        if workspace:
            # 一時ファイルは、参照するレイヤーがすべて閉じられるまで保つ。
            _release_when_closed(workspace, added)
            workspace = None
    finally:
        if workspace:
            _cleanup(workspace)
        _unregister(task)


class LayerLoadTask(QgsTask):
    """取得を取消可能なタスクで実行し、完了時にGUIでレイヤーを追加する。"""

    def __init__(self, key, name):
        super().__init__(f"国土数値情報: {name}", QgsTask.Flag.CanCancel)
        self.key, self.name = key, name
        self.result, self.error = None, None

    def run(self):
        url, member, mode, directory = self.key
        try:
            self.result = prepare(self, url, member, self.name, mode, directory)
            return True
        except Exception as exc:
            # ワーカーのQtオブジェクトを例外のtraceback経由でGUIへ持ち込まない。
            self.error = str(exc)
            return False

    def finished(self, success):
        _finish(self)
        self.result = None


def start(url, member, name):
    """GUIスレッドのダブルクリック／ドロップから開始。設定変更を即時反映する。"""
    mode = local_storage.loading_mode()
    directory = local_storage.download_directory()
    if mode == "save" and not directory:
        if not local_storage.configure_loading():
            return
        mode, directory = (
            local_storage.loading_mode(),
            local_storage.download_directory(),
        )
    key = LoadKey(url, member, mode, directory)
    if key in pending:
        notify("このレイヤーは読み込み中です。")
        return
    task = LayerLoadTask(key, name)
    _register(task)
    QgsApplication.taskManager().addTask(task)


def cancel_pending():
    tasks = list(pending.values())
    pending.clear()
    for task in tasks:
        task.cancel()
    loading_signals.changed.emit()


class KsjDropHandler(QgsCustomDropHandler):
    """ドラッグ中は通信せず、ドロップ後にダブルクリックと同じ処理を使う。"""

    def customUriProviderKey(self):
        return DROP_KEY

    def handleCustomUriDrop(self, uri):
        try:
            source = json.loads(uri.uri)
            url, member, name = (source[key] for key in ("url", "member", "name"))
            if not all(isinstance(value, str) for value in (url, member, name)):
                raise ValueError("レイヤーの指定が不正です。")
            start(url, member, name)
        except (ValueError, KeyError, TypeError) as exc:
            notify(f"レイヤーを追加できません: {exc}", warning=True)

    def canHandleCustomUriCanvasDrop(self, uri):
        return True

    def handleCustomUriCanvasDrop(self, uri, canvas):
        self.handleCustomUriDrop(uri)
        return True
