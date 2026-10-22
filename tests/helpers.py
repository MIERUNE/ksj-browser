"""テスト間で共有する補助関数。"""

import io
import json
import time
import zipfile

from osgeo import gdal, ogr, osr
from qgis.core import QgsApplication, QgsTask

from ksj import layer_loading, local_storage


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
