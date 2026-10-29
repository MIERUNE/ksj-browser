"""Mapsuke からの目次取得・部分取得・バックグラウンド読み込み。"""

import json
from pathlib import Path

import pytest
from qgis.core import (
    QgsApplication,
    QgsProcessingAlgRunnerTask,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
)

from ksj import catalog, local_storage
from tests.helpers import (
    make_raster,
    make_shapefile,
    make_vector,
    point_geojson,
    pump_until,
    shapefile_entries,
    zip_bytes,
)
from tests.test_processing import run


@pytest.fixture
def remote_resource(processing_provider, sample_catalog, http_data, monkeypatch):
    dataset = catalog.load_dataset("dams")
    dataset["resources"][0]["url"] = http_data["url"]
    monkeypatch.setattr(catalog, "load_dataset", lambda dataset_id: dataset)
    monkeypatch.setattr(local_storage, "download_directory", lambda: "")
    http_data.update(
        range_support=True,
        body=zip_bytes(
            [
                ("points/point.geojson", point_geojson()),
                ("unselected.bin", b"z" * 2_000_000),
                ("other.geojson", point_geojson("other")),
                ("KS-META-test.xml", "<metadata/>"),
            ]
        ),
    )
    return {
        "DATASET_ID": "dams",
        "RESOURCE_ID": local_storage.url_key(http_data["url"]),
    }


def background(qgis_app, name, parameters, context=None, feedback=None):
    context = context or QgsProcessingContext()
    feedback = feedback or QgsProcessingFeedback()
    algorithm = QgsApplication.processingRegistry().algorithmById("ksj:" + name)
    assert algorithm is not None, f"{name} が登録されていません"
    task = QgsProcessingAlgRunnerTask(algorithm, parameters, context, feedback)
    completed = []
    task.executed.connect(lambda ok, result: completed.append((ok, result)))
    QgsApplication.taskManager().addTask(task)
    pump_until(qgis_app, lambda: bool(completed), 90)
    assert completed[0][0], feedback.textLog()
    return completed[0][1], context


def test_list_files_only_reads_directory_and_paginates(
    remote_resource, http_data, qgis_app
):
    result, _ = background(
        qgis_app, "list_resource_files", {**remote_resource, "LIMIT": 1}
    )
    data = json.loads(result["RESULTS"])
    assert result["TOTAL"] == 2
    assert data["next_offset"] == 1
    assert data["items"][0]["member"] == "points/point.geojson"
    assert data["items"][0]["partial_available"] is True
    assert data["items"][0]["provider"] == "ogr"
    assert data["dataset"]["license"] == "非商用"
    assert http_data["bytes_sent"] < 70_000
    assert all(http_data["ranges"])
    data = json.loads(
        run("list_resource_files", {**remote_resource, "QUERY": "other"})["RESULTS"]
    )
    assert [item["member"] for item in data["items"]] == ["other.geojson"]


def test_member_download_skips_other_data_and_reuses_saved_files(
    remote_resource, http_data, qgis_app, tmp_path
):
    parameters = {
        **remote_resource,
        "DIRECTORY": str(tmp_path),
        "MEMBER": "points/point.geojson",
    }
    result, _ = background(qgis_app, "download_resource", parameters)
    path = Path(result["LOCAL_PATH"])
    assert path.is_file()
    assert json.loads(path.read_text())["features"]
    data = json.loads(result["RESULTS"])
    assert len(data["layers"]) == 1
    assert data["member"] == parameters["MEMBER"]
    assert data["resource"]["source_url"] == "https://example.org/2024"
    assert not list(tmp_path.rglob("other.geojson"))
    assert http_data["bytes_sent"] < 150_000
    assert all(http_data["ranges"])
    count = len(http_data["requests"])
    assert run("download_resource", parameters)["LOCAL_PATH"] == str(path)
    listed = run("list_resource_files", {**remote_resource, "DIRECTORY": str(tmp_path)})
    assert listed["TOTAL"] == 2
    assert len(http_data["requests"]) == count


def test_listing_recommends_complete_shapefiles_before_pagination(
    remote_resource, http_data
):
    http_data["body"] = zip_bytes(
        [
            ("city.geojson", point_geojson()),
            ("broken/city.shp", b""),
            ("broken/city.shx", b""),
            ("complete/CITY.SHP", b""),
            ("complete/city.shx", b""),
            ("complete/City.DBF", b""),
            ("other.geojson", point_geojson()),
            ("other.shp", b""),
            ("other.shx", b""),
            ("other.dbf", b""),
        ]
    )
    first = json.loads(
        run("list_resource_files", {**remote_resource, "LIMIT": 1})["RESULTS"]
    )
    assert first["items"][0]["member"] == "complete/CITY.SHP"
    assert first["items"][0]["recommended"] is True
    assert first["items"][0]["recommendation_reason"]
    assert first["total"] == 5
    assert first["next_offset"] == 1
    rest = json.loads(
        run("list_resource_files", {**remote_resource, "OFFSET": 1})["RESULTS"]
    )["items"]
    assert [item["member"] for item in rest] == [
        "other.shp",
        "city.geojson",
        "broken/city.shp",
        "other.geojson",
    ]
    assert rest[0]["recommended"] is True
    assert all(item["recommended"] is False for item in rest[1:])
    assert all(item["recommendation_reason"] == "" for item in rest[1:])
    assert rest[2]["partial_available"] is False
    assert ".dbf" in rest[2]["reason"]
    filtered = json.loads(
        run("list_resource_files", {**remote_resource, "QUERY": ".geojson"})["RESULTS"]
    )
    assert [item["member"] for item in filtered["items"]] == [
        "city.geojson",
        "other.geojson",
    ]


def test_explicit_geojson_member_is_preserved_with_shapefile_alternative(
    remote_resource, http_data, tmp_path
):
    source = make_shapefile(tmp_path / "city.shp", ["札幌市"], "utf-8")
    http_data["body"] = zip_bytes(
        [("city.geojson", point_geojson())] + shapefile_entries(source)
    )
    result = run("load_resource", {**remote_resource, "MEMBER": "city.geojson"})
    assert Path(result["LOCAL_PATH"]).suffix == ".geojson"
    assert json.loads(result["RESULTS"])["member"] == "city.geojson"
    assert result["LAYERS"][0].featureCount() == 1


def test_member_download_includes_shapefile_companions(
    remote_resource, http_data, qgis_app, tmp_path
):
    source = make_shapefile(tmp_path / "city.shp", ["札幌市"], "cp932", cpg="CP932")
    http_data["body"] = zip_bytes(
        shapefile_entries(source) + [("unused.bin", b"z" * 2_000_000)]
    )
    result, _ = background(
        qgis_app,
        "download_resource",
        {
            **remote_resource,
            "DIRECTORY": str(tmp_path),
            "MEMBER": "city.shp",
        },
    )
    path = Path(result["LOCAL_PATH"])
    for suffix in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        assert path.with_suffix(suffix).is_file()
    assert not list(path.parent.rglob("unused.bin"))


def test_temporary_download_needs_no_setting_and_survives_context(
    remote_resource, qgis_app, tmp_path
):
    context = QgsProcessingContext()
    context.setTemporaryFolder(str(tmp_path))
    result, context = background(
        qgis_app,
        "download_resource",
        {
            **remote_resource,
            "MEMBER": "points/point.geojson",
            "TEMPORARY": True,
        },
        context,
    )
    path = Path(result["LOCAL_PATH"])
    assert tmp_path in path.parents
    del context
    layer = run("load_layer", {"SOURCE": str(path)})["OUTPUT"]
    assert layer.featureCount() == 1


@pytest.mark.parametrize("name", ["list_resource_files", "download_resource"])
def test_partial_operations_do_not_fallback_to_full_download(
    remote_resource, http_data, tmp_path, name
):
    http_data["range_support"] = False
    with pytest.raises(QgsProcessingException, match="部分取得"):
        run(
            name,
            {
                **remote_resource,
                "DIRECTORY": str(tmp_path),
                "MEMBER": "points/point.geojson",
            },
        )
    assert all(http_data["ranges"])
    assert not list(tmp_path.rglob("*.geojson"))


@pytest.mark.parametrize(
    "member", ["../point.geojson", "missing.geojson", "nested.zip", "external.vrt"]
)
def test_bad_or_full_download_only_members_are_rejected(
    remote_resource, http_data, tmp_path, member
):
    http_data["body"] = zip_bytes(
        [("nested.zip", b"zip"), ("external.vrt", "<VRTDataset/>")]
    )
    with pytest.raises(QgsProcessingException):
        run(
            "download_resource",
            {**remote_resource, "DIRECTORY": str(tmp_path), "MEMBER": member},
        )
    assert not list(tmp_path.rglob("*.vrt"))
    assert not list(tmp_path.rglob("*.zip"))
    assert all(http_data["ranges"])


def test_listing_explains_members_requiring_full_download(remote_resource, http_data):
    http_data["body"] = zip_bytes(
        [("nested.zip", b"zip"), ("external.vrt", "<VRTDataset/>")]
    )
    data = json.loads(run("list_resource_files", remote_resource)["RESULTS"])
    assert len(data["items"]) == 2
    assert all(
        not item["partial_available"] and item["reason"] for item in data["items"]
    )


@pytest.mark.parametrize("name", ["list_resource_files", "download_resource"])
def test_partial_cancellation_stops_before_http(
    remote_resource, http_data, tmp_path, name
):
    feedback = QgsProcessingFeedback()
    feedback.cancel()
    with pytest.raises(QgsProcessingException):
        run(
            name,
            {
                **remote_resource,
                "DIRECTORY": str(tmp_path),
                "MEMBER": "points/point.geojson",
            },
            feedback=feedback,
        )
    assert not http_data["requests"]


def test_load_resource_background_returns_layers_for_mapsuke(
    remote_resource, qgis_app, http_data, tmp_path
):
    context = QgsProcessingContext()
    context.setTemporaryFolder(str(tmp_path))
    before = set(QgsProject.instance().mapLayers())
    result, context = background(
        qgis_app,
        "load_resource",
        {
            **remote_resource,
            "MEMBER": "points/point.geojson",
        },
        context,
    )
    assert set(QgsProject.instance().mapLayers()) == before
    assert len(result["LAYERS"]) == 1
    project = QgsProject()
    layer = context.takeResultLayer(result["LAYERS"][0])
    project.addMapLayer(layer)
    del context
    assert layer.featureCount() == 1
    assert next(layer.getFeatures())["name"] == "試験ダム"
    assert layer.crs().authid() == "EPSG:4326"
    assert http_data["bytes_sent"] < 150_000


@pytest.mark.parametrize(
    "sublayer,expected", [("", ["dams", "stations"]), ("stations", ["stations"])]
)
def test_load_resource_selects_sublayers(
    remote_resource, http_data, tmp_path, sublayer, expected
):
    path = make_vector(tmp_path / "source.gpkg", ("dams", "stations"))
    http_data["body"] = zip_bytes([(path.name, path.read_bytes())])
    result = run(
        "load_resource", {**remote_resource, "MEMBER": path.name, "SUBLAYER": sublayer}
    )
    assert sorted(layer.name() for layer in result["LAYERS"]) == expected
    assert all(layer.featureCount() == 1 for layer in result["LAYERS"])


def test_load_resource_rejects_unknown_sublayer_without_publishing(remote_resource):
    context = QgsProcessingContext()
    with pytest.raises(QgsProcessingException, match="SUBLAYER"):
        run(
            "load_resource",
            {
                **remote_resource,
                "MEMBER": "points/point.geojson",
                "SUBLAYER": "missing",
            },
            context,
        )
    assert not context.temporaryLayerStore().mapLayers()


@pytest.mark.parametrize("encoding", [0, 2])
def test_load_resource_preserves_japanese_attributes(
    remote_resource, http_data, tmp_path, encoding
):
    source = make_shapefile(tmp_path / "city.shp", ["札幌市①髙﨑"], "cp932")
    http_data["body"] = zip_bytes(shapefile_entries(source))
    result = run(
        "load_resource", {**remote_resource, "MEMBER": "city.shp", "ENCODING": encoding}
    )
    assert next(result["LAYERS"][0].getFeatures())["name"] == "札幌市①髙﨑"


def test_load_resource_reads_raster(remote_resource, http_data, tmp_path):
    path = make_raster(tmp_path / "height.tif")
    http_data["body"] = zip_bytes([(path.name, path.read_bytes())])
    layer = run("load_resource", {**remote_resource, "MEMBER": path.name})["LAYERS"][0]
    assert isinstance(layer, QgsRasterLayer)
    assert layer.dataProvider().sample(layer.extent().center(), 1)[0] == 7


def test_load_resource_requires_member_before_any_zip_download(
    remote_resource, http_data
):
    with pytest.raises(QgsProcessingException, match="MEMBER"):
        run("load_resource", remote_resource)
    assert not http_data["requests"]


def test_temporary_load_reuses_persisted_member(
    remote_resource, http_data, tmp_path, monkeypatch
):
    parameters = {
        **remote_resource,
        "MEMBER": "points/point.geojson",
        "DIRECTORY": str(tmp_path),
    }
    stored = run("download_resource", parameters)["LOCAL_PATH"]
    monkeypatch.setattr(local_storage, "download_directory", lambda: str(tmp_path))
    count = len(http_data["requests"])
    result = run("load_resource", {**remote_resource, "MEMBER": "points/point.geojson"})
    assert result["LOCAL_PATH"] == stored
    assert result["LAYERS"][0].featureCount() == 1
    assert len(http_data["requests"]) == count


def test_mesh_index_filters_and_returns_all_matches_in_background(
    processing_provider, sample_catalog, monkeypatch, qgis_app
):
    dataset = catalog.load_dataset("dams")
    # ページサイズ 20 を超え、全件が索引に含まれることも確認する。
    dataset["resources"] = [
        {
            **sample_catalog[0],
            "region": str(5300 + code),
            "url": f"https://example.org/{code}.zip",
        }
        for code in range(21)
    ] + [{**sample_catalog[1], "region": "5339"}]
    monkeypatch.setattr(catalog, "load_dataset", lambda dataset_id: dataset)
    before = set(QgsProject.instance().mapLayers())
    result, context = background(
        qgis_app, "create_mesh_index", {"DATASET_ID": "dams", "YEAR": "2024"}
    )
    layer = context.takeResultLayer(result["OUTPUT"])
    assert layer.featureCount() == 21
    assert layer.crs().authid() == "EPSG:4326"
    assert layer.customProperty("ksj/mesh_index")
    feature = next(f for f in layer.getFeatures() if f["mesh_code"] == "5300")
    assert feature.geometry().boundingBox().xMinimum() == 100
    assert feature.geometry().boundingBox().yMinimum() == pytest.approx(35 + 1 / 3)
    assert json.loads(feature["resources"])[0]["resource_id"]
    assert set(QgsProject.instance().mapLayers()) == before


def test_mesh_index_without_mesh_resources_is_clear_error(
    processing_provider, sample_catalog
):
    with pytest.raises(QgsProcessingException, match="メッシュ"):
        run("create_mesh_index", {"DATASET_ID": "dams"})


def test_large_file_listing_scans_directory_linearly(remote_resource, monkeypatch):
    from ksj import remote_zip

    class CountedEntries(list):
        visits = 0

        def __iter__(self):
            for entry in super().__iter__():
                self.visits += 1
                yield entry

    names = CountedEntries(
        f"folder/layer{index:05d}{suffix}"
        for index in range(50)
        for suffix in (".shp", ".shx", ".dbf", ".prj")
    )
    monkeypatch.setattr(remote_zip, "list_members", lambda *args: names)
    data = json.loads(
        run(
            "list_resource_files",
            {
                **remote_resource,
                "QUERY": "layer00049",
                "LIMIT": 1,
            },
        )["RESULTS"]
    )
    assert data["total"] == 1
    assert data["items"][0]["partial_available"]
    # 数量に比例する走査回数で、ページ1件のために全目次を何十回も走査しない。
    assert names.visits <= 10 * len(names)


def test_listing_detects_missing_case_insensitive_shapefile_companions(
    remote_resource, http_data
):
    http_data["body"] = zip_bytes(
        [
            ("a/CITY.SHP", b""),
            ("a/city.shx", b""),
            ("a/City.DBF", b""),
            ("b/city.shp", b""),
            ("b/city.shx", b""),
        ]
    )
    data = json.loads(run("list_resource_files", remote_resource)["RESULTS"])
    assert data["items"][0]["partial_available"]
    assert not data["items"][1]["partial_available"]
    assert ".dbf" in data["items"][1]["reason"]


def test_single_file_lists_offline_and_loads_without_member(remote_resource, http_data):
    dataset = catalog.load_dataset("dams")
    url = http_data["url"].replace("data.zip", "point.geojson")
    dataset["resources"][0].update(url=url, filename="point.geojson")
    parameters = {**remote_resource, "RESOURCE_ID": local_storage.url_key(url)}
    http_data["body"] = point_geojson().encode()
    listed = json.loads(run("list_resource_files", parameters)["RESULTS"])
    assert listed["items"][0]["member"] == ""
    assert listed["items"][0]["provider"] == "ogr"
    assert listed["items"][0]["recommended"] is False
    assert listed["items"][0]["recommendation_reason"] == ""
    assert not http_data["requests"]
    result = run("load_resource", parameters)
    assert result["LAYERS"][0].featureCount() == 1
    assert http_data["requests"] == ["/point.geojson"]
    # 後続の例外の traceback がこのフレームを保持しうるため、テストが所有する
    # レイヤーは QGIS の終了処理より先に解放する。
    del result
    with pytest.raises(QgsProcessingException, match="ZIP 以外"):
        run("load_resource", {**parameters, "MEMBER": "point.geojson"})
    assert len(http_data["requests"]) == 1


def test_cancel_during_transfer_does_not_publish_layer_or_partial_file(
    remote_resource, tmp_path
):
    class CancelOnProgress(QgsProcessingFeedback):
        def setProgress(self, value):
            super().setProgress(value)
            if value > 0:
                self.cancel()

    context, feedback = QgsProcessingContext(), CancelOnProgress()
    with pytest.raises(QgsProcessingException, match="中止"):
        run(
            "load_resource",
            {
                **remote_resource,
                "MEMBER": "points/point.geojson",
                "TEMPORARY": False,
                "DIRECTORY": str(tmp_path),
            },
            context,
            feedback,
        )
    assert not context.temporaryLayerStore().mapLayers()
    assert not list(tmp_path.rglob("*.geojson"))
    assert not list(tmp_path.rglob("*.part"))
