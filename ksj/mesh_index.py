"""配布メッシュの索引と、地物アクションからのデータ読み込み。"""

import json
from pathlib import PurePosixPath

from osgeo import gdal
from qgis import utils
from qgis.core import (
    Qgis,
    QgsAction,
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
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QInputDialog

from . import catalog, local_storage, zip_scanner

INDEX_PROPERTY = "ksj/mesh_index"
RESOURCE_PROPERTY = "ksj/resource_url"
_pending = {}


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
    action = QgsAction(
        QgsAction.GenericPython,
        "このメッシュのデータを追加",
        "import importlib\n"
        f"importlib.import_module({__name__!r}).load_mesh('[% @layer_id %]', [% $id %])",
        "",
        False,
        "データを追加",
        {"Canvas", "Feature"},
    )
    layer.actions().addAction(action)
    layer.actions().setDefaultAction("Canvas", action.id())
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
    parent = utils.iface.mainWindow() if utils.iface is not None else None
    choice, accepted = QInputDialog.getItem(
        parent,
        f"メッシュ {code} のデータ",
        "追加する配布ファイルを選択",
        labels,
        0,
        False,
    )
    return resources[labels.index(choice)] if accepted else None


def scan_resource(task, url, directory=None):
    """ワーカー内ではVSI/GDALと値だけを扱い、レイヤー作成はGUIへ戻す。"""
    paths = []

    def scan_zip(root, depth=0):
        if depth > 8:
            raise ValueError(
                "ZIPの入れ子が深すぎます。ブラウザから個別に選択してください。"
            )
        for entry in zip_scanner.filter_supported(
            zip_scanner.list_entries_recursive(root)
        ):
            if task.isCanceled():
                return
            if PurePosixPath(entry).suffix.lower() == ".zip":
                scan_zip(zip_scanner.nested_zip_root(root, entry), depth + 1)
            else:
                paths.append(f"{root}/{entry}")

    suffix = zip_scanner.download_suffix(url)
    if suffix not in zip_scanner.SUPPORTED_EXTENSIONS:
        raise ValueError(
            "この形式は直接読み込めません。ブラウザから原本をダウンロードしてください。"
        )
    local_path = local_storage.ensure_local_file(
        url,
        directory if directory is not None else local_storage.download_directory(),
        is_canceled=task.isCanceled,
        progress=task.setProgress,
    )
    if suffix == ".zip":
        scan_zip(zip_scanner.vsi_zip_root(local_path))
    else:
        paths.append(local_path)
    result, failed = [], []
    for path in paths:
        if task.isCanceled():
            return None
        entry = PurePosixPath(path)
        if entry.suffix.lower() in zip_scanner.RASTER_EXTENSIONS:
            result.append(("gdal", path, entry.name))
            continue
        # 国土数値情報の配布XMLメタデータは空間レイヤーではない。
        upper = entry.name.upper()
        if upper.startswith("KS-META-") and upper.endswith(".XML"):
            continue
        try:
            dataset = gdal.OpenEx(path, gdal.OF_VECTOR)
        except RuntimeError:
            # 他プラグインの gdal.UseExceptions() に動作を左右されないようにする。
            dataset = None
        if dataset is None:
            failed.append(zip_scanner.decode_entry_name(entry.name))
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


def finish_loading(task, layer_id, url, exception, result=None):
    if _pending.get(url) is not task:
        return
    _pending.pop(url)
    if task.isCanceled():
        return
    project = QgsProject.instance()
    index_layer = project.mapLayer(layer_id)
    if index_layer is None:
        return
    if exception is not None:
        notify(f"データを取得できません: {exception}", warning=True)
        return
    if result is None:
        return
    ogr = QgsProviderRegistry.instance().providerMetadata("ogr")
    present = loaded_sources(url)
    added, failed, sources = 0, list(result["failed"]), []
    for provider, path, name in result["layers"]:
        if provider == "ogr":
            uri = ogr.encodeUri({"path": path, "layerName": name})
            layer_class = QgsVectorLayer
        else:
            uri, layer_class = path, QgsRasterLayer
        sources.append(uri)
        if uri in present:
            continue
        layer = layer_class(uri, name, provider)
        if not layer.isValid():
            failed.append(name)
            continue
        layer.setCustomProperty(RESOURCE_PROPERTY, url)
        project.addMapLayer(layer)
        present.add(uri)
        added += 1
    if utils.iface is not None:
        utils.iface.setActiveLayer(index_layer)
    if failed:
        notify(
            f"{added}レイヤーを追加。読み込み失敗: {', '.join(failed)}", warning=True
        )
    else:
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
        notify("この配布ファイルは追加済みです。")
        return
    directory = local_storage.download_directory()
    if not directory:
        parent = utils.iface.mainWindow() if utils.iface is not None else None
        directory = local_storage.choose_download_directory(parent)
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
