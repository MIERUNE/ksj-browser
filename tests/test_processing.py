"""エージェントが検索・取得・レイヤー出力を順に利用する契約。"""

import importlib.util
import json
from pathlib import Path
import sys

import pytest
from qgis.core import (
    QgsApplication,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsVectorLayer,
)

from ksj import catalog, local_storage
from tests.helpers import (
    make_vector,
    make_raster,
    mock_download,
    point_file,
    point_geojson,
    pump_until,
    zip_bytes,
)


def run(name, parameters=None, context=None, feedback=None):
    import processing

    return processing.run(
        "ksj:" + name, parameters or {}, context=context, feedback=feedback
    )


def test_provider_is_discoverable():
    assert importlib.util.find_spec("ksj.processing_provider") is not None


def test_search_filters_and_paginates(processing_provider, sample_catalog):
    first = run("search_datasets", {"QUERY": "ダム", "LIMIT": 1})
    data = json.loads(first["RESULTS"])
    assert first["TOTAL"] == 2
    assert data["next_offset"] == 1
    assert data["items"][0]["id"] == "dams"
    second = json.loads(
        run("search_datasets", {"QUERY": "ダム", "LIMIT": 1, "OFFSET": 1})["RESULTS"]
    )
    assert second["items"][0]["id"] == "old-dams"
    assert second["next_offset"] is None
    filtered = json.loads(
        run("search_datasets", {"QUERY": "ダム 水域", "EDITION": "現行形式"})["RESULTS"]
    )
    assert [item["id"] for item in filtered["items"]] == ["dams"]
    assert run("search_datasets", {"CATEGORY": "交通"})["TOTAL"] == 0


def test_resource_filters_preserve_provenance(processing_provider, sample_catalog):
    result = run(
        "list_resources",
        {
            "DATASET_ID": "dams",
            "YEAR": "2024",
            "REGION": "東京",
            "FORMAT": "shp",
            "QUERY": "世界測地系",
        },
    )
    data = json.loads(result["RESULTS"])
    assert result["TOTAL"] == 1
    item = data["items"][0]
    assert item["url"] == "https://example.org/dams.zip"
    assert item["source_url"] == "https://example.org/2024"
    assert item["resource_id"]
    assert data["dataset"]["license"] == "非商用"
    all_resources = json.loads(run("list_resources", {"DATASET_ID": "dams"})["RESULTS"])
    assert len(all_resources["items"]) == 3
    assert all_resources["items"][0]["resource_id"] == item["resource_id"]


@pytest.mark.parametrize("dataset_id", ["missing", "../index"])
def test_invalid_dataset_is_processing_error(
    processing_provider, sample_catalog, dataset_id
):
    with pytest.raises(QgsProcessingException):
        run("list_resources", {"DATASET_ID": dataset_id})


def download_parameters(tmp_path, resource_index=0):
    items = json.loads(run("list_resources", {"DATASET_ID": "dams"})["RESULTS"])[
        "items"
    ]
    return {
        "DATASET_ID": "dams",
        "RESOURCE_ID": items[resource_index]["resource_id"],
        "DIRECTORY": str(tmp_path),
    }


def test_download_load_and_analyze_real_layer(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    import processing

    calls = mock_download(
        monkeypatch,
        zip_bytes(
            [
                ("nested/dams.geojson", point_geojson()),
                ("KS-META-test.xml", "<metadata/>"),
                ("invalid.xml", "<unsupported/>"),
            ]
        ),
    )
    parameters = download_parameters(tmp_path)
    downloaded = run("download_resource", parameters)
    manifest = json.loads(downloaded["RESULTS"])
    assert Path(downloaded["LOCAL_PATH"]).is_dir()
    assert manifest["resource"]["url"] == "https://example.org/dams.zip"
    assert manifest["dataset"]["license"] == "非商用"
    assert len(manifest["layers"]) == 1
    assert len(manifest["unreadable_files"]) == 1
    item = manifest["layers"][0]
    loaded = run(
        "load_layer",
        {"SOURCE": item["source"], "PROVIDER": item["provider"], "NAME": "ダム"},
    )["OUTPUT"]
    assert isinstance(loaded, QgsVectorLayer) and loaded.isValid()
    assert loaded.featureCount() == 1 and loaded.crs().authid() == "EPSG:4326"
    assert loaded.name() == "ダム"
    assert next(loaded.getFeatures())["name"] == "試験ダム"
    output = processing.run(
        "native:reprojectlayer",
        {"INPUT": loaded, "TARGET_CRS": "EPSG:6677", "OUTPUT": "memory:"},
    )["OUTPUT"]
    assert output.isValid() and output.crs().authid() == "EPSG:6677"
    run("download_resource", parameters)
    assert calls == ["https://example.org/dams.zip"]


def test_download_rejects_invalid_id_and_missing_directory(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    parameters = download_parameters(tmp_path)
    with pytest.raises(QgsProcessingException, match="配布"):
        run("download_resource", {**parameters, "RESOURCE_ID": "not-in-catalog"})
    monkeypatch.setattr(local_storage, "download_directory", lambda: "")
    with pytest.raises(QgsProcessingException, match="DIRECTORY"):
        run("download_resource", {**parameters, "DIRECTORY": ""})
    with pytest.raises(QgsProcessingException, match="形式"):
        run("download_resource", download_parameters(tmp_path, 2))


def test_download_uses_existing_directory_setting(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    mock_download(monkeypatch, zip_bytes([("dams.geojson", point_geojson())]))
    monkeypatch.setattr(local_storage, "download_directory", lambda: str(tmp_path))
    parameters = download_parameters(tmp_path)
    parameters.pop("DIRECTORY")
    assert Path(run("download_resource", parameters)["LOCAL_PATH"]).is_dir()


def test_canceled_download_does_not_publish_layers(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    feedback = QgsProcessingFeedback()

    def cancel_download(url, destination, is_canceled, progress):
        destination.write_bytes(zip_bytes([("dams.geojson", point_geojson())]))
        feedback.cancel()

    monkeypatch.setattr(local_storage, "_download", cancel_download)
    context = QgsProcessingContext()
    with pytest.raises(QgsProcessingException):
        run("download_resource", download_parameters(tmp_path), context, feedback)
    assert not context.temporaryLayerStore().mapLayers()
    assert not list(tmp_path.rglob("*.geojson"))


def test_load_layer_background_result_can_be_taken_by_qtaro(
    processing_provider, qgis_app, tmp_path
):
    from qgis.core import QgsProcessingAlgRunnerTask

    path = point_file(tmp_path)
    context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
    algorithm = QgsApplication.processingRegistry().algorithmById("ksj:load_layer")
    task = QgsProcessingAlgRunnerTask(
        algorithm, {"SOURCE": str(path), "PROVIDER": "ogr"}, context, feedback
    )
    results = []
    task.executed.connect(lambda ok, result: results.append((ok, result)))
    QgsApplication.taskManager().addTask(task)
    pump_until(qgis_app, lambda: bool(results), 10)
    assert results[0][0]
    layer = context.takeResultLayer(results[0][1]["OUTPUT"])
    project = QgsProject()
    project.addMapLayer(layer)
    assert project.mapLayer(layer.id()).featureCount() == 1


@pytest.mark.parametrize(
    "parameters",
    [
        {"SOURCE": "/missing.geojson", "PROVIDER": "ogr"},
        {"SOURCE": "/missing.geojson", "PROVIDER": "invalid"},
    ],
)
def test_load_invalid_layer_fails(processing_provider, parameters):
    with pytest.raises(QgsProcessingException):
        run("load_layer", parameters)


def test_multilayer_and_raster_are_individually_loadable(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    from qgis.core import QgsRasterLayer

    package = make_vector(tmp_path / "source.gpkg", ("dams", "stations"))
    raster = make_raster(tmp_path / "height.tif")
    mock_download(
        monkeypatch,
        zip_bytes(
            [(package.name, package.read_bytes()), (raster.name, raster.read_bytes())]
        ),
    )
    manifest = json.loads(
        run("download_resource", download_parameters(tmp_path))["RESULTS"]
    )
    assert len(manifest["layers"]) == 3
    assert not manifest["unreadable_files"]
    vectors = []
    for item in manifest["layers"]:
        # NAME省略時はサブレイヤー名（なければファイル名）をレイヤー名にする。
        output = run(
            "load_layer", {"SOURCE": item["source"], "PROVIDER": item["provider"]}
        )["OUTPUT"]
        assert output.isValid() and output.crs().authid() == "EPSG:4326"
        assert output.name() == item["name"]
        if item["provider"] == "gdal":
            assert isinstance(output, QgsRasterLayer)
            assert output.width() == 2 and output.bandCount() == 1
        else:
            vectors.append(output.name())
            assert output.featureCount() == 1
    assert sorted(vectors) == ["dams", "stations"]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("/data/dams.geojson", "dams"),
        ("/data/source.gpkg|layername=stations", "stations"),
        ("/data/source.gpkg|layername=stations|geometrytype=Point", "stations"),
        ("/data/source.gpkg|layerid=0", "source"),
    ],
)
def test_default_layer_name_prefers_sublayer(qgis_app, source, expected):
    from ksj.processing_algorithms import default_layer_name

    assert default_layer_name(source, "ogr") == expected


def test_plugin_lifecycle_registers_once_and_unloads(qgis_app, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    name = "ksj_processing_lifecycle_test"
    spec = importlib.util.spec_from_file_location(
        name, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    package = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, package)
    spec.loader.exec_module(package)
    plugin = package.classFactory(None)
    registry = QgsApplication.processingRegistry()
    try:
        plugin.initProcessing()
        first = registry.providerById("ksj")
        assert first is not None
        plugin.initProcessing()
        plugin.initGui()
        plugin.initGui()
        assert registry.providerById("ksj") is first
        assert {algorithm.id() for algorithm in first.algorithms()} == {
            "ksj:search_datasets",
            "ksj:list_resources",
            "ksj:download_resource",
            "ksj:load_layer",
        }
    finally:
        plugin.unload()
    assert registry.providerById("ksj") is None
    plugin.unload()
    plugin.initProcessing()
    assert registry.algorithmById("ksj:load_layer") is not None
    plugin.unload()


@pytest.mark.parametrize("limits", [{"LIMIT": 0}, {"OFFSET": -1}, {"LIMIT": 101}])
def test_invalid_pagination_is_rejected(processing_provider, sample_catalog, limits):
    with pytest.raises(QgsProcessingException):
        run("search_datasets", limits)


def test_unreadable_archive_keeps_download_without_claiming_layers(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    mock_download(
        monkeypatch,
        zip_bytes([("unsupported.xml", "<old-format/>"), ("readme.txt", "説明")]),
    )
    result = run("download_resource", download_parameters(tmp_path))
    manifest = json.loads(result["RESULTS"])
    assert not manifest["layers"]
    assert manifest["unreadable_files"]
    assert Path(result["LOCAL_PATH"]).is_dir()


def test_download_failure_is_processing_error(
    processing_provider, sample_catalog, tmp_path, monkeypatch
):
    mock_download(monkeypatch, b"<html>not data</html>")
    with pytest.raises(QgsProcessingException):
        run("download_resource", download_parameters(tmp_path))
    assert not list(tmp_path.rglob("*.part"))


def test_canceled_algorithms_stop_before_work(processing_provider, sample_catalog):
    context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
    feedback.cancel()
    for name, parameters in (
        ("search_datasets", {}),
        ("list_resources", {"DATASET_ID": "dams"}),
        ("load_layer", {"SOURCE": "/missing.geojson"}),
    ):
        with pytest.raises(QgsProcessingException):
            run(name, parameters, context, feedback)
    assert not context.temporaryLayerStore().mapLayers()


def test_bundled_catalog_search_leads_to_resources(processing_provider):
    found = json.loads(
        run("search_datasets", {"QUERY": "ダム", "EDITION": "現行形式"})["RESULTS"]
    )
    assert found["items"]
    resources = json.loads(
        run("list_resources", {"DATASET_ID": found["items"][0]["id"]})["RESULTS"]
    )
    assert resources["items"]
    assert all(
        item["resource_id"] and item["url"].startswith("https://")
        for item in resources["items"]
    )


def test_background_download_over_http(
    processing_provider, sample_catalog, tmp_path, monkeypatch, http_data, qgis_app
):
    from qgis.core import QgsProcessingAlgRunnerTask

    original = catalog.load_dataset("dams")
    original["resources"][0]["url"] = http_data["url"]
    monkeypatch.setattr(catalog, "load_dataset", lambda dataset_id: original)
    parameters = download_parameters(tmp_path)
    context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
    algorithm = QgsApplication.processingRegistry().algorithmById(
        "ksj:download_resource"
    )
    task = QgsProcessingAlgRunnerTask(algorithm, parameters, context, feedback)
    results = []
    task.executed.connect(lambda ok, result: results.append((ok, result)))
    QgsApplication.taskManager().addTask(task)
    pump_until(qgis_app, lambda: bool(results), 90)
    assert results[0][0], feedback.textLog()
    manifest = json.loads(results[0][1]["RESULTS"])
    assert len(manifest["layers"]) == 1
    assert Path(manifest["layers"][0]["file"]).is_file()
    assert http_data["requests"] == ["/data.zip"]
