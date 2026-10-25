"""テスト間で共有する補助関数。"""

import io
import json
import time
import zipfile
from pathlib import Path

from osgeo import gdal, ogr, osr
from qgis.core import QgsApplication, QgsTask
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QApplication

from ksj import layer_loading, local_storage, temporary_files
from ksj.encoding_check import source_path

# CP932 を設定したプロバイダーは、Qt の環境により Shift_JIS と名乗ることがある。
SHIFT_JIS_NAMES = {"Shift_JIS", "CP932"}


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


def message_log_signal(app):
    """メッセージログの受信シグナル。QGIS 4 は形式付きシグナルを送出し、旧シグナルには本文を送らない。"""
    log = app.messageLog()
    return getattr(log, "messageReceivedWithFormat", log.messageReceived)


def interact_with_modal(matches, action):
    """次のイベント処理でモーダルが開いていれば、matches(dialog) が真のものに action(dialog) を実行する。"""

    def attempt():
        dialog = QApplication.activeModalWidget()
        if dialog is not None and matches(dialog):
            action(dialog)

    QTimer.singleShot(0, attempt)


def pump_until(app, predicate, timeout, interval=0.01):
    """イベントを処理しながら条件が成り立つまで待つ。"""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(interval)
    assert predicate(), "時間内に条件を満たしませんでした"


def run_workers(app, functions):
    """各関数をQGISのワーカータスクで実行し、同じ順序で戻り値を返す。"""
    results, errors, done = {}, [], set()

    def finish(index, error, result=None):
        done.add(index)
        results[index] = result
        if error is not None:
            errors.append(error)

    tasks = []
    for index, function in enumerate(functions):
        task = QgsTask.fromFunction(
            "保存テスト",
            lambda task, function=function: function(),
            on_finished=lambda error, result=None, index=index: finish(
                index, error, result
            ),
        )
        tasks.append(task)
        QgsApplication.taskManager().addTask(task)
    # QGISのネットワーク初期化・標準タイムアウトを含めて待つ。
    pump_until(app, lambda: len(done) == len(tasks), timeout=90, interval=0.005)
    if errors:
        raise errors[0]
    return [results[index] for index in range(len(tasks))]


def wait_for_layer_loading(app, timeout=15):
    """ブラウザから開始したレイヤー追加タスクがすべて終わるまで待つ。"""
    pump_until(app, lambda: not layer_loading.pending, timeout=timeout)


def termination_of(task):
    """タスクの終了（完了・中断のどちらでも）を待つ述語を返す。cancel() より前に呼ぶ。"""
    ended = []
    task.taskCompleted.connect(lambda: ended.append(True))
    task.taskTerminated.connect(lambda: ended.append(True))
    return lambda: bool(ended)


def icon_image(item):
    """ブラウザ項目のアイコンを比較可能な画像にする。"""
    return item.icon().pixmap(24, 24).toImage()


def point_geojson(name="試験ダム", x=139.7, y=35.6):
    """1点だけを持つGeoJSON文字列。"""
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"name": name},
                    "geometry": {"type": "Point", "coordinates": [x, y]},
                }
            ],
        },
        ensure_ascii=False,
    )


def point_file(directory, name="dams.geojson"):
    """1点のGeoJSONファイルを書き、そのパスを返す。"""
    path = directory / name
    path.write_text(point_geojson(), encoding="utf-8")
    return path


def make_vector(path, names, driver="GPKG", epsg=4326):
    """各レイヤーに1点を持つベクタファイルを作り、そのパスを返す。"""
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(epsg)
    dataset = ogr.GetDriverByName(driver).CreateDataSource(str(path))
    for name in names:
        layer = dataset.CreateLayer(name, srs=crs, geom_type=ogr.wkbPoint)
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (139.7 35.6)"))
        assert layer.CreateFeature(feature) == 0
        feature = layer = None
    dataset = None
    return path


def make_raster(path, epsg=4326):
    """2x2・1バンドのGeoTIFFを作り、そのパスを返す。"""
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(epsg)
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 2, 2, 1, gdal.GDT_Byte)
    dataset.SetGeoTransform((139, 0.5, 0, 36, 0, -0.5))
    dataset.SetProjection(crs.ExportToWkt())
    dataset.GetRasterBand(1).Fill(7)
    dataset = None
    return path


def workspaces(temp_root):
    """temp_root 配下に残っている一時ディレクトリ。"""
    return sorted(temp_root.glob(temporary_files.PREFIX + "*"))


def stored_in(layer, directory):
    """レイヤーの参照先が、指定したフォルダの配下にあるか。"""
    return directory in source_path(layer).parents


def make_shapefile(path, texts, encoding, cpg=None, ldid=0, field="name"):
    """texts を属性に持つ点の Shapefile を書く。.dbf の文字列は指定の文字コードで保存する。

    texts の要素が bytes ならそのまま書く（どの文字コードでも復号できない列の試験用）。
    cpg は .cpg の内容（None なら作らない）、ldid は .dbf ヘッダ 30 バイト目の言語ID。
    """
    path = Path(path)
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(4326)
    # ISO-8859-1 は 1 バイトを 1 文字に写すため、どの文字コードのバイト列もそのまま .dbf に入る。
    # QGIS は Shapefile を開くと SHAPE_ENCODING="" を残し GDAL の再符号化を止めるため、書く間だけ上書きする。
    previous = gdal.GetConfigOption("SHAPE_ENCODING")
    gdal.SetConfigOption("SHAPE_ENCODING", "ISO-8859-1")
    try:
        dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(path))
        layer = dataset.CreateLayer(path.stem, srs=crs, geom_type=ogr.wkbPoint)
        layer.CreateField(ogr.FieldDefn(field, ogr.OFTString))
        for text in texts:
            raw = text if isinstance(text, bytes) else text.encode(encoding)
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetField(field, raw.decode("latin-1"))
            feature.SetGeometry(ogr.CreateGeometryFromWkt("POINT (139.7 35.6)"))
            assert layer.CreateFeature(feature) == 0
            feature = None
        layer = dataset = None
    finally:
        gdal.SetConfigOption("SHAPE_ENCODING", previous)
    dbf = path.with_suffix(".dbf")
    contents = bytearray(dbf.read_bytes())
    contents[29] = ldid
    dbf.write_bytes(bytes(contents))
    cpg_path = path.with_suffix(".cpg")
    if cpg is None:
        cpg_path.unlink(missing_ok=True)
    else:
        cpg_path.write_text(cpg, encoding="ascii")
    return path


def shapefile_entries(path):
    """Shapefile 一式を ZIP 用の (名前, 内容) にする。"""
    path = Path(path)
    return [
        (sidecar.name, sidecar.read_bytes())
        for sidecar in sorted(path.parent.glob(path.stem + ".*"))
    ]
