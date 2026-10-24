"""配布メッシュの索引と、地物アクションからのデータ読み込み。"""

import json
from os.path import commonpath
from pathlib import Path

from osgeo import gdal
from qgis import utils
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFillSymbol,
    QgsMessageLog,
    QgsPalLayerSettings,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsTask,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsGui, QgsMapLayerAction, QgsMapLayerActionContext
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from . import catalog, local_storage, zip_scanner

INDEX_PROPERTY = "ksj/mesh_index"
RESOURCE_PROPERTY = "ksj/resource_url"
_pending = {}
ALREADY_ADDED_MESSAGE = "この配布ファイルは追加済みです。"
MESH_ACTION_NAME = "このメッシュのデータを追加"


class MeshIndexAction(QgsMapLayerAction):
    """プラグインの有効期間だけ登録し、索引にスクリプトを埋め込まずに実行する。"""

    def __init__(self):
        super().__init__(
            MESH_ACTION_NAME, None, targets=Qgis.MapLayerActionTarget.SingleFeature
        )
        self.triggeredForFeatureV2.connect(self._load_mesh)
        QgsGui.mapLayerActionRegistry().addMapLayerAction(self)
        project = QgsProject.instance()
        project.layersAdded.connect(self._set_default_actions)
        project.layersWillBeRemoved.connect(self._clear_default_actions)
        self._set_default_actions(project.mapLayers().values())

    def canRunUsingLayer(self, layer, context=None):
        # QGISは旧シグネチャとcontext付きの両方を呼ぶ。処理は後者だけで許可する。
        return (
            context is not None
            and isinstance(layer, QgsVectorLayer)
            and bool(layer.customProperty(INDEX_PROPERTY, False))
        )

    def _set_default_actions(self, layers):
        registry = QgsGui.mapLayerActionRegistry()
        context = QgsMapLayerActionContext()
        for layer in layers:
            if not self.canRunUsingLayer(layer, context):
                continue
            registry.setDefaultActionForLayer(layer, self)

    def _clear_default_actions(self, layer_ids):
        # レジストリは削除されたレイヤーの既定アクションを自動で解除しない。
        registry = QgsGui.mapLayerActionRegistry()
        for layer_id in layer_ids:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is not None and registry.defaultActionForLayer(layer) is self:
                registry.setDefaultActionForLayer(layer, None)

    def _load_mesh(self, layer, feature, context):
        if self.canRunUsingLayer(layer, context) and feature.isValid():
            load_mesh(layer.id(), feature.id())

    def unregister(self):
        QgsProject.instance().layersAdded.disconnect(self._set_default_actions)
        QgsProject.instance().layersWillBeRemoved.disconnect(
            self._clear_default_actions
        )
        QgsGui.mapLayerActionRegistry().removeMapLayerAction(self)
        self.triggeredForFeatureV2.disconnect(self._load_mesh)
        self.deleteLater()


def mesh_groups(resources):
    groups = {}
    for resource in resources:
        code = catalog.mesh_code(resource)
        if code:
            group = groups.setdefault(code, [])
            if not any(r["url"] == resource["url"] for r in group):
                group.append(resource)
    return groups


def notify(message, warning=False):
    level = Qgis.MessageLevel.Warning if warning else Qgis.MessageLevel.Info
    QgsMessageLog.logMessage(message, "KSJ", level)
    if utils.iface is not None:
        utils.iface.messageBar().pushMessage("KSJ", message, level=level, duration=8)


def mesh_feature(code, records):
    """1次メッシュ番号から世界測地系の概略範囲を求める。"""
    west, south = 100 + int(code[2:]), int(code[:2]) * 2 / 3
    east, north = west + 1, south + 2 / 3
    return {
        "type": "Feature",
        "properties": {
            "mesh_code": code,
            "file_count": len(records),
            "resources": json.dumps(records, ensure_ascii=False),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
    }


def style_index_layer(layer):
    """枠線とメッシュ番号だけを描いて背景地図を隠さず、索引である旨を説明に残す。"""
    layer.renderer().setSymbol(
        QgsFillSymbol.createSimple(
            {
                "color": "0,0,0,0",
                "outline_color": "36,122,175,255",
                "outline_width": "0.4",
            }
        )
    )
    label = QgsPalLayerSettings()
    label.fieldName = "mesh_code"
    text_format = QgsTextFormat()
    text_format.setSize(10)
    text_format.setColor(QColor("#154c70"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    text_format.setBuffer(buffer)
    label.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(label))
    layer.setLabelsEnabled(True)
    layer.setDisplayExpression('"mesh_code"')
    metadata = layer.metadata()
    metadata.setAbstract(
        "配布がある1次メッシュの位置を示す索引です。地物アクションでクリックしてデータを追加できます。"
        "範囲は世界測地系の概略位置です。旧日本測地系の配布データの厳密な境界とは異なります。"
    )
    layer.setMetadata(metadata)


def add_mesh_index(title, resources):
    """GeoJSONをデータソースに内包し、別ファイルなしでプロジェクトに保存する。"""
    features = [
        mesh_feature(code, records) for code, records in mesh_groups(resources).items()
    ]
    if not features:
        notify("メッシュ番号を持つ配布ファイルがありません。", warning=True)
        return None
    source = json.dumps(
        {"type": "FeatureCollection", "features": features}, ensure_ascii=False
    )
    options = QgsVectorLayer.LayerOptions()
    options.forceReadOnly = True
    layer = QgsVectorLayer(source, f"{title} — メッシュ索引", "ogr", options)
    if not layer.isValid():
        notify("メッシュ索引を作成できませんでした。", warning=True)
        return None
    layer.setCustomProperty(INDEX_PROPERTY, True)
    style_index_layer(layer)
    QgsProject.instance().addMapLayer(layer)
    if utils.iface is not None:
        utils.iface.setActiveLayer(layer)
        utils.iface.actionFeatureAction().trigger()
    notify(
        "メッシュ索引を追加しました。地物アクションで欲しいメッシュをクリックしてください。"
    )
    return layer


def choose_resource(resources, code):
    if len(resources) == 1:
        return resources[0]
    # 同じ形式でも測地系・河川などが違う配布を省略しない。
    labels = [f"{i + 1}. {catalog.resource_label(r)}" for i, r in enumerate(resources)]
    parent = local_storage.main_window()
    choice, accepted = QInputDialog.getItem(
        parent,
        f"メッシュ {code} のデータ",
        "追加する配布ファイルを選択",
        labels,
        0,
        False,
    )
    return resources[labels.index(choice)] if accepted else None


def scan_resource(task, url, directory):
    """ワーカーで取得・展開し、通常ファイルのパスをGUIへ戻す。"""
    suffix = zip_scanner.download_suffix(url)
    if suffix not in zip_scanner.SUPPORTED_EXTENSIONS:
        raise ValueError(
            "この形式は直接読み込めません。ブラウザから原本をダウンロードしてください。"
        )
    local_path = local_storage.ensure_local_data(
        url, directory, is_canceled=task.isCanceled, progress=task.setProgress
    )
    if suffix == ".zip":
        root = Path(local_path)
        paths = [
            str(root / entry) for entry in zip_scanner.supported_entries(local_path)
        ]
    else:
        paths = [local_path]
    result, failed = [], []
    for path in paths:
        if task.isCanceled():
            return None
        entry = Path(path)
        if zip_scanner.provider_key(entry) == "gdal":
            result.append(("gdal", path, entry.name))
            continue
        try:
            dataset = gdal.OpenEx(path, gdal.OF_VECTOR)
        except RuntimeError:
            # 他プラグインの gdal.UseExceptions() に動作を左右されないようにする。
            dataset = None
        if dataset is None:
            failed.append(entry.name)
            continue
        for index in range(dataset.GetLayerCount()):
            result.append(("ogr", path, dataset.GetLayerByIndex(index).GetName()))
        dataset = None  # GDALデータセットを即時解放する。
    if task.isCanceled():
        return None
    if not result:
        raise ValueError(
            "直接読み込めるレイヤーがありません。ブラウザから配布ファイルを確認してください。"
        )
    return {"layers": result, "failed": failed}


def loaded_sources(url):
    """この配布ファイルから追加済みで、まだ有効なレイヤーのデータソース。"""
    return {
        layer.source()
        for layer in QgsProject.instance().mapLayers().values()
        if layer.isValid() and layer.customProperty(RESOURCE_PROPERTY) == url
    }


def choose_layers(layers):
    """ファイル形式と同名ファイルの場所を示し、チェックしたレイヤーだけを返す。"""
    dialog = QDialog(local_storage.main_window())
    dialog.setObjectName("ksj-mesh-layers")
    dialog.setWindowTitle("追加するレイヤーを選択")
    layout = QVBoxLayout(dialog)
    layout.addWidget(
        QLabel("追加するレイヤーにチェックを入れてください（複数選択可）。")
    )
    listing = QListWidget(dialog)
    root = commonpath([Path(path).parent for _, path, _, _ in layers])
    for _, path, name, _ in layers:
        relative = Path(path).relative_to(root).as_posix()
        item = QListWidgetItem(f"{name} ｜ {relative}", listing)
        item.setToolTip(path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
    layout.addWidget(listing)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    add_button.setText("選択したレイヤーを追加")
    add_button.setEnabled(False)
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    def checked_layers():
        return [
            layer
            for row, layer in enumerate(layers)
            if listing.item(row).checkState() == Qt.CheckState.Checked
        ]

    listing.itemChanged.connect(lambda: add_button.setEnabled(bool(checked_layers())))
    dialog.resize(680, 360)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    selected = checked_layers() if accepted else []
    dialog.deleteLater()
    return selected


def _is_current(task, layer_id, url):
    """この結果を反映してよいか。取り消し・索引の削除・アンロードの後は捨てる。"""
    return (
        _pending.get(url) is task
        and not task.isCanceled()
        and QgsProject.instance().mapLayer(layer_id) is not None
    )


def finish_loading(task, layer_id, url, exception, result=None):
    try:
        _finish_loading(task, layer_id, url, exception, result)
    finally:
        if _pending.get(url) is task:
            _pending.pop(url)


def _finish_loading(task, layer_id, url, exception, result):
    if not _is_current(task, layer_id, url):
        return
    if exception is not None:
        notify(f"データを取得できません: {exception}", warning=True)
        return
    if result is None:
        return
    ogr = QgsProviderRegistry.instance().providerMetadata("ogr")
    present = loaded_sources(url)
    candidates, sources = [], []
    for provider, path, name in result["layers"]:
        if provider == "ogr":
            uri = ogr.encodeUri({"path": path, "layerName": name})
        else:
            uri = path
        sources.append(uri)
        if uri not in present:
            candidates.append((provider, path, name, uri))
    if not candidates:
        if result["failed"]:
            notify(f"読み込み失敗: {', '.join(result['failed'])}", warning=True)
        else:
            notify(ALREADY_ADDED_MESSAGE)
        return
    # 複数レイヤーの配布なら、残りが1件でも利用者に確認してから追加する。
    selected = choose_layers(candidates) if len(result["layers"]) > 1 else candidates
    # モーダル画面の表示中もイベントが処理されるため、状態を再確認する。
    if not selected or not _is_current(task, layer_id, url):
        return
    project = QgsProject.instance()
    index_layer = project.mapLayer(layer_id)
    added, failed = 0, list(result["failed"])
    # 同じ配布の二重起動は _pending が防ぐため、候補はモーダル後も未追加のままである。
    for provider, path, name, uri in selected:
        layer_class = QgsVectorLayer if provider == "ogr" else QgsRasterLayer
        layer = layer_class(uri, name, provider)
        if not layer.isValid():
            failed.append(name)
            continue
        layer.setCustomProperty(RESOURCE_PROPERTY, url)
        project.addMapLayer(layer)
        added += 1
    if utils.iface is not None:
        utils.iface.setActiveLayer(index_layer)
    if failed:
        notify(
            f"{added}レイヤーを追加。読み込み失敗: {', '.join(failed)}", warning=True
        )
    else:
        # 選んだ分ではなく配布の全レイヤーを記録し、load_mesh が全件追加済みの判定に使う。
        index_layer.setCustomProperty(f"ksj/loaded/{url}", sources)
        notify(f"{added}レイヤーを追加しました。続けて別のメッシュを選べます。")


def load_mesh(layer_id, feature_id):
    layer = QgsProject.instance().mapLayer(layer_id)
    if layer is None or not layer.customProperty(INDEX_PROPERTY, False):
        return
    feature = layer.getFeature(feature_id)
    if not feature.isValid():
        return
    resource = choose_resource(json.loads(feature["resources"]), feature["mesh_code"])
    if resource is None:
        return
    url = resource["url"]
    if url in _pending:
        notify("この配布ファイルは読み込み中です。")
        return
    expected = layer.customProperty(f"ksj/loaded/{url}", [])
    if expected and set(expected).issubset(loaded_sources(url)):
        notify(ALREADY_ADDED_MESSAGE)
        return
    directory = (
        local_storage.download_directory() or local_storage.choose_download_directory()
    )
    if not directory:
        return
    task = QgsTask.fromFunction(
        f"KSJ: {resource['filename']}",
        scan_resource,
        url,
        directory,
        on_finished=lambda exception, result=None: finish_loading(
            task, layer_id, url, exception, result
        ),
    )
    task.setDependentLayers([layer])
    _pending[url] = task
    QgsApplication.taskManager().addTask(task)
    notify(f"読み込み中: {resource['filename']}")


def cancel_pending():
    """アンロード後のコールバックがレイヤーを追加しないようにする。"""
    tasks = list(_pending.values())
    _pending.clear()
    for task in tasks:
        task.cancel()
