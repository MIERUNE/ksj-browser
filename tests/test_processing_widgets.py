"""通常のProcessing画面で選択した表示名が正しい処理入力になること。"""

from qgis.core import QgsApplication, QgsProcessingContext
from qgis.PyQt.QtWidgets import QComboBox

from tests.helpers import make_gpkg, make_raster, point_file


def set_value(wrapper, value):
    wrapper.setParameterValue(value, QgsProcessingContext())


def test_dataset_names_and_dependent_choices(dialogs, sample_catalog):
    dialog = dialogs("list_resources")
    wrappers = dialog.mainWidget().wrappers
    dataset = wrappers["DATASET_ID"].widget
    assert isinstance(dataset, QComboBox)
    assert "ダム" in dataset.itemText(dataset.findData("dams"))
    set_value(wrappers["DATASET_ID"], "dams")
    year = wrappers["YEAR"].widget
    region = wrappers["REGION"].widget
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
    category = wrappers["CATEGORY"].widget
    edition = wrappers["EDITION"].widget
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
    chooser = wrappers["RESOURCE_ID"].widget
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
    path = point_file(tmp_path)
    dialog = dialogs("load_layer")
    wrappers = dialog.mainWidget().wrappers
    chooser = wrappers["SOURCE"].widget
    chooser.file.setFilePath(str(path))
    assert chooser.layers.count() == 1
    parameters = dialog.createProcessingParameters()
    assert parameters["SOURCE"].startswith(str(path))
    assert parameters["PROVIDER"] == "ogr"
    set_value(wrappers["SOURCE"], parameters["SOURCE"])
    assert wrappers["SOURCE"].parameterValue() == parameters["SOURCE"]


def test_empty_or_invalid_file_clears_source(dialogs, tmp_path):
    path = point_file(tmp_path)
    dialog = dialogs("load_layer")
    wrapper = dialog.mainWidget().wrappers["SOURCE"]
    chooser = wrapper.widget
    chooser.file.setFilePath(str(path))
    chooser.file.setFilePath(str(tmp_path / "missing.geojson"))
    assert not wrapper.parameterValue()
    assert chooser.layers.count() == 0
    assert "確認" in chooser.status.text()
    chooser.file.setFilePath("")
    assert chooser.status.text() == chooser.HINT


def test_missing_saved_sublayer_does_not_select_another_layer(dialogs, tmp_path):
    path = point_file(tmp_path)
    dialog = dialogs("load_layer")
    wrapper = dialog.mainWidget().wrappers["SOURCE"]
    set_value(wrapper, str(path) + "|layername=deleted-layer")
    assert not wrapper.parameterValue()
    assert "選び直し" in wrapper.widget.status.text()
    wrapper.widget.layers.setCurrentIndex(0)
    assert wrapper.parameterValue() == str(path)
    assert "選び直し" not in wrapper.widget.status.text()
    set_value(wrapper, str(path))
    assert wrapper.parameterValue() == str(path)


def test_gui_load_schedules_layer_for_map(dialogs, tmp_path, monkeypatch):
    from processing.gui.AlgorithmDialog import AlgorithmDialog
    from qgis.core import QgsProcessingFeedback, QgsProject, QgsVectorLayer

    dialog = dialogs("load_layer")
    path = point_file(tmp_path)
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
    combo = wrappers["DATASET_ID"].widget
    combo.setCurrentIndex(combo.findData("dams"))
    assert wrappers["YEAR"].widget.findData("2024年") >= 0
    combo.setCurrentIndex(combo.findData("old-dams"))
    assert wrappers["YEAR"].widget.findData("2024年") < 0


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
    wrappers["RESOURCE_ID"].widget.files.setCurrentIndex(1)
    wrappers["DATASET_ID"].widget.setEditText("ダ")
    assert not wrappers["DATASET_ID"].parameterValue()
    assert not wrappers["RESOURCE_ID"].parameterValue()


def test_missing_year_can_be_selected_separately_from_all(dialogs, sample_catalog):
    from ksj.local_storage import url_key

    dialog = dialogs("download_resource")
    wrappers = dialog.mainWidget().wrappers
    set_value(wrappers["DATASET_ID"], "dams")
    chooser = wrappers["RESOURCE_ID"].widget
    chooser.year.select("")
    assert chooser.files.count() == 2
    chooser.files.setCurrentIndex(1)
    assert chooser.value() == url_key("https://example.org/old.lzh")


def test_sublayer_restore_and_raster_provider(dialogs, tmp_path):
    package = make_gpkg(tmp_path / "source.gpkg", ("dams", "stations"))
    raster = make_raster(tmp_path / "height.tif")
    dialog = dialogs("load_layer")
    wrappers = dialog.mainWidget().wrappers
    chooser = wrappers["SOURCE"].widget
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
