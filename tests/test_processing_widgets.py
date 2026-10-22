"""通常のProcessing画面で選択した表示名が正しい処理入力になること。"""

import importlib
import pytest
from qgis.core import QgsApplication, QgsProcessingContext
from qgis.PyQt.QtWidgets import QComboBox

from tests import test_processing

processing_provider = test_processing.processing_provider
sample_catalog = test_processing.sample_catalog


@pytest.fixture
def dialogs(processing_provider, monkeypatch):
    # pytest-qgisのifaceスタブにはbrowserModelがない。標準パネルをヘッドレスで作る。
    monkeypatch.setattr(
        importlib.import_module("processing.gui.ParametersPanel"), "iface", None
    )
    opened = []

    def create(name):
        algorithm = (
            QgsApplication.processingRegistry().algorithmById("ksj:" + name).create()
        )
        dialog = algorithm.createCustomParametersWidget(None)
        assert dialog is not None, "選択式のProcessing画面が必要"
        opened.append(dialog)
        return dialog

    yield create
    for dialog in opened:
        dialog.close()
        dialog.deleteLater()


def set_value(wrapper, value):
    wrapper.setParameterValue(value, QgsProcessingContext())


def test_dataset_names_and_dependent_choices(dialogs, sample_catalog):
    dialog = dialogs("list_resources")
    wrappers = dialog.mainWidget().wrappers
    dataset = wrappers["DATASET_ID"].control
    assert isinstance(dataset, QComboBox)
    assert "ダム" in dataset.itemText(dataset.findData("dams"))
    set_value(wrappers["DATASET_ID"], "dams")
    year = wrappers["YEAR"].control
    region = wrappers["REGION"].control
    assert year.findData("2024年") >= 0
    assert region.findData("東京都") >= 0
    year.setCurrentIndex(year.findData("2024年"))
    region.setCurrentIndex(region.findData("東京都"))
    parameters = dialog.createProcessingParameters()
    assert parameters["DATASET_ID"] == "dams"
    assert parameters["YEAR"] == "2024年"
    assert parameters["REGION"] == "東京都"
    set_value(wrappers["DATASET_ID"], "old-dams")
    assert wrappers["YEAR"].parameterValue() == ""
    assert wrappers["REGION"].parameterValue() == ""


def test_search_category_and_edition_choices(dialogs, sample_catalog):
    dialog = dialogs("search_datasets")
    wrappers = dialog.mainWidget().wrappers
    category = wrappers["CATEGORY"].control
    edition = wrappers["EDITION"].control
    assert category.findData("水域") >= 0
    edition.setCurrentIndex(edition.findData("現行形式"))
    assert dialog.createProcessingParameters()["EDITION"] == "現行形式"


def test_resource_filters_choose_stable_id_and_restore(
    dialogs, sample_catalog, tmp_path
):
    from ksj.local_storage import url_key

    dialog = dialogs("download_resource")
    wrappers = dialog.mainWidget().wrappers
    set_value(wrappers["DATASET_ID"], "dams")
    set_value(wrappers["DIRECTORY"], str(tmp_path))
    chooser = wrappers["RESOURCE_ID"].control
    assert wrappers["RESOURCE_ID"].parameterValue() == ""
    chooser.year.setCurrentIndex(chooser.year.findData("2024年"))
    assert chooser.region.findData("全国") == -1
    assert chooser.files.count() == 2  # 未選択 + 一致する1配布
    chooser.files.setCurrentIndex(1)
    parameters = dialog.createProcessingParameters()
    assert parameters["RESOURCE_ID"] == url_key("https://example.org/dams.zip")
    assert "dams.zip" in chooser.files.currentText()
    assert "世界測地系" in chooser.files.currentText()
    set_value(wrappers["RESOURCE_ID"], url_key("https://example.org/old.zip"))
    assert wrappers["RESOURCE_ID"].parameterValue() == url_key(
        "https://example.org/old.zip"
    )
    set_value(wrappers["DATASET_ID"], "old-dams")
    assert wrappers["RESOURCE_ID"].parameterValue() == ""
    assert not chooser.files.isEnabled()


def test_file_picker_discovers_layer_and_sets_provider(dialogs, tmp_path):
    path = tmp_path / "dams.geojson"
    path.write_text(test_processing.POINT, encoding="utf-8")
    dialog = dialogs("load_layer")
    wrappers = dialog.mainWidget().wrappers
    chooser = wrappers["SOURCE"].control
    chooser.file.setFilePath(str(path))
    assert chooser.layers.count() == 1
    parameters = dialog.createProcessingParameters()
    assert parameters["SOURCE"].startswith(str(path))
    assert parameters["PROVIDER"] == "ogr"
    set_value(wrappers["SOURCE"], parameters["SOURCE"])
    assert wrappers["SOURCE"].parameterValue() == parameters["SOURCE"]


def test_empty_or_invalid_file_clears_source(dialogs, tmp_path):
    path = tmp_path / "dams.geojson"
    path.write_text(test_processing.POINT, encoding="utf-8")
    dialog = dialogs("load_layer")
    wrapper = dialog.mainWidget().wrappers["SOURCE"]
    chooser = wrapper.control
    chooser.file.setFilePath(str(path))
    chooser.file.setFilePath(str(tmp_path / "missing.geojson"))
    assert not wrapper.parameterValue()
    assert chooser.layers.count() == 0


def test_missing_saved_sublayer_does_not_select_another_layer(dialogs, tmp_path):
    path = tmp_path / "dams.geojson"
    path.write_text(test_processing.POINT, encoding="utf-8")
    dialog = dialogs("load_layer")
    wrapper = dialog.mainWidget().wrappers["SOURCE"]
    set_value(wrapper, str(path) + "|layername=deleted-layer")
    assert not wrapper.parameterValue()
    assert "選び直し" in wrapper.control.status.text()
    wrapper.control.layers.setCurrentIndex(0)
    assert wrapper.parameterValue() == str(path)
    assert "選び直し" not in wrapper.control.status.text()
    set_value(wrapper, str(path))
    assert wrapper.parameterValue() == str(path)


def test_gui_load_schedules_layer_for_map(dialogs, tmp_path, monkeypatch):
    from processing.gui.AlgorithmDialog import AlgorithmDialog
    from qgis.core import QgsProcessingFeedback, QgsProject, QgsVectorLayer

    dialog = dialogs("load_layer")
    path = tmp_path / "dams.geojson"
    path.write_text(test_processing.POINT, encoding="utf-8")
    layer = QgsVectorLayer(str(path), "ダム", "ogr")
    context = QgsProcessingContext()
    project = QgsProject()
    context.setProject(project)
    context.temporaryLayerStore().addMapLayer(layer)
    # 標準QGISの結果処理に渡す直前の契約を確認する。
    monkeypatch.setattr(AlgorithmDialog, "finish", lambda *args, **kwargs: None)
    dialog.finish(True, {"OUTPUT": layer.id()}, context, QgsProcessingFeedback())
    assert context.willLoadLayerOnCompletion(layer.id())
    assert context.layerToLoadOnCompletionDetails(layer.id()).project is project


def test_same_display_name_keeps_selected_value(processing_provider):
    from ksj.processing_widgets import ChoiceBox

    combo = ChoiceBox(strict=True)
    combo.replace([("同じ名称", "first"), ("同じ名称", "second")])
    combo.select("second")
    assert combo.value() == "second"


def test_same_dataset_label_still_refreshes_dependents(
    dialogs, sample_catalog, monkeypatch
):
    from ksj import catalog

    original = catalog.load_index()
    original["datasets"][1] = {**original["datasets"][0], "id": "old-dams"}
    monkeypatch.setattr(catalog, "load_index", lambda: original)
    dialog = dialogs("list_resources")
    wrappers = dialog.mainWidget().wrappers
    combo = wrappers["DATASET_ID"].control
    combo.setCurrentIndex(combo.findData("dams"))
    assert wrappers["YEAR"].control.findData("2024年") >= 0
    combo.setCurrentIndex(combo.findData("old-dams"))
    assert wrappers["YEAR"].control.findData("2024年") < 0


def test_gui_configuration_does_not_change_registry_or_batch(dialogs):
    dialog = dialogs("download_resource")
    original = QgsApplication.processingRegistry().algorithmById(
        "ksj:download_resource"
    )
    assert not original.parameterDefinition("DATASET_ID").metadata()
    batch_algorithm = dialog.algorithm().create()
    assert not batch_algorithm.parameterDefinition("DATASET_ID").metadata()


def test_partial_dataset_text_clears_previous_resource(dialogs, sample_catalog):
    dialog = dialogs("download_resource")
    wrappers = dialog.mainWidget().wrappers
    set_value(wrappers["DATASET_ID"], "dams")
    wrappers["RESOURCE_ID"].control.files.setCurrentIndex(1)
    wrappers["DATASET_ID"].control.setEditText("ダ")
    assert not wrappers["DATASET_ID"].parameterValue()
    assert not wrappers["RESOURCE_ID"].parameterValue()


def test_missing_year_can_be_selected_separately_from_all(dialogs, sample_catalog):
    from ksj.local_storage import url_key

    dialog = dialogs("download_resource")
    wrappers = dialog.mainWidget().wrappers
    set_value(wrappers["DATASET_ID"], "dams")
    chooser = wrappers["RESOURCE_ID"].control
    chooser.year.select("")
    assert chooser.files.count() == 2
    chooser.files.setCurrentIndex(1)
    assert chooser.value() == url_key("https://example.org/old.lzh")


def test_sublayer_restore_and_raster_provider(dialogs, tmp_path):
    from osgeo import gdal, ogr, osr

    crs = osr.SpatialReference()
    crs.ImportFromEPSG(4326)
    package = tmp_path / "source.gpkg"
    data = ogr.GetDriverByName("GPKG").CreateDataSource(str(package))
    for name in ("dams", "stations"):
        data.CreateLayer(name, srs=crs, geom_type=ogr.wkbPoint)
    data = None
    raster = tmp_path / "height.tif"
    data = gdal.GetDriverByName("GTiff").Create(str(raster), 2, 2, 1, gdal.GDT_Byte)
    data.SetGeoTransform((139, 0.5, 0, 36, 0, -0.5))
    data.SetProjection(crs.ExportToWkt())
    data = None

    dialog = dialogs("load_layer")
    wrappers = dialog.mainWidget().wrappers
    chooser = wrappers["SOURCE"].control
    chooser.file.setFilePath(str(package))
    assert chooser.layers.count() == 2
    chooser.layers.setCurrentIndex(1)
    source = wrappers["SOURCE"].parameterValue()
    chooser.layers.setCurrentIndex(0)
    set_value(wrappers["SOURCE"], source)
    assert chooser.layers.currentIndex() == 1
    assert wrappers["SOURCE"].parameterValue() == source
    chooser.file.setFilePath(str(raster))
    assert chooser.layers.count() == 1
    assert dialog.createProcessingParameters()["PROVIDER"] == "gdal"
