"""ブラウザの追加操作をタスク化し、記憶した保存方式でレイヤーを追加する。"""

import json
import tempfile
from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsFeatureRequest,
    QgsFeedback,
    QgsProcessingContext,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsTask,
    QgsVectorLayer,
)
from qgis.gui import QgsCustomDropHandler

from . import local_storage, remote_zip, zip_scanner
from .mesh_index import notify

DROP_KEY = "ksj-layer"
pending = {}


def prepare(task, url, member, name, mode, directory):
    """ワーカーで必要なファイルのみ取得。QGISプロジェクトには触れない。"""
    temporary = (
        tempfile.TemporaryDirectory(prefix="ksj-layer-")
        if mode == "temporary"
        else None
    )
    context = QgsProcessingContext()
    try:
        destination = temporary.name if temporary else directory
        existing = remote_zip.saved_member(url, member, directory) if member else None
        if existing:
            path = existing
        elif member:
            path = remote_zip.ensure_member(
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
                ("ogr", layer.uri(), layer.name())
                for layer in provider.querySublayers(path)
            ]
        else:
            layers = [("ogr", path, name)]
        if not layers:
            raise local_storage.DownloadError("追加可能なレイヤーがありません。")
        if mode == "temporary":
            prepared = []
            for provider, path, name in layers:
                local_storage._check_canceled(task.isCanceled)
                if provider == "ogr":
                    source = QgsVectorLayer(path, name, provider)
                    if not source.isValid():
                        raise local_storage.DownloadError(
                            f"レイヤーを読み込めません: {name}"
                        )
                    layer = source.materialize(QgsFeatureRequest(), task.feedback)
                    source = None
                    local_storage._check_canceled(task.isCanceled)
                    if layer is None or not layer.isValid():
                        raise local_storage.DownloadError(
                            f"一時レイヤーを作成できません: {name}"
                        )
                    layer.setName(name)
                    context.temporaryLayerStore().addMapLayer(layer)
                    path = layer.id()
                prepared.append((provider, path, name))
            layers = prepared
        local_storage._check_canceled(task.isCanceled)
        # ワーカー内で生成したメモリレイヤーの所有権を、まとめてGUIへ移す。
        context.pushToThread(QgsApplication.instance().thread())
        return {
            "layers": layers,
            "temporary": temporary,
            "mode": mode,
            "context": context,
        }
    except Exception:
        if temporary:
            temporary.cleanup()
        raise


def _finish(task, key, error, result):
    temporary = result["temporary"] if result else None
    try:
        if pending.get(key) is not task:
            return
        pending.pop(key)
        if task.isCanceled():
            return
        if error is not None:
            notify(f"レイヤーを追加できません: {error}", warning=True)
            return
        if result is None:
            return
        added, failed = [], []
        for provider, path, name in result["layers"]:
            if provider == "ogr" and result["mode"] == "temporary":
                layer = result["context"].takeResultLayer(path)
            else:
                layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
                layer = layer_type(path, name, provider)
            if layer is None or not layer.isValid():
                failed.append(name)
                continue
            added.append(layer)
        for layer in added:
            if layer.providerType() == "gdal" and temporary:
                # ラスタはメモリベクタ化できない。レイヤーが閉じるまで作業領域を保つ。
                layer.destroyed.connect(
                    lambda obj=None, workspace=temporary: workspace.cleanup()
                )
                temporary = None
            QgsProject.instance().addMapLayer(layer)
        if failed:
            notify(f"読み込めないレイヤー: {', '.join(failed)}", warning=True)
    finally:
        if result:
            result["context"].temporaryLayerStore().removeAllMapLayers()
        if temporary:
            temporary.cleanup()


class LayerLoadTask(QgsTask):
    """取得とメモリ化を同じ取消可能なタスクで実行する。"""

    def __init__(self, key, name):
        super().__init__(f"国土数値情報: {name}", QgsTask.Flag.CanCancel)
        self.key, self.name = key, name
        self.feedback = QgsFeedback()
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

    def cancel(self):
        self.feedback.cancel()
        super().cancel()

    def finished(self, success):
        _finish(self, self.key, self.error, self.result)
        self.result = None


def start(url, member, name):
    """GUIスレッドのダブルクリック／ドロップから開始。設定変更を即時反映する。"""
    mode = local_storage.loading_mode()
    directory = local_storage.download_directory()
    if mode == "save" and not directory:
        if not local_storage.configure_loading():
            return True
        mode, directory = (
            local_storage.loading_mode(),
            local_storage.download_directory(),
        )
    key = (url, member, mode, directory)
    if key in pending:
        notify("このレイヤーは読み込み中です。")
        return True
    task = LayerLoadTask(key, name)
    pending[key] = task
    QgsApplication.taskManager().addTask(task)
    return True


def cancel_pending():
    tasks = list(pending.values())
    pending.clear()
    for task in tasks:
        task.cancel()


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
