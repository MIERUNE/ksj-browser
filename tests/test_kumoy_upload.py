"""kumoy プラグインの確認・インストール支援と、取得したレイヤーのアップロード。"""

from pathlib import Path

import sys
import types
from types import SimpleNamespace

import pytest
from qgis import utils
from qgis.core import (
    QgsApplication,
    QgsProcessingProvider,
    QgsSettings,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QSettings

from ksj import kumoy_upload, encoding_check, temporary_files
from tests.helpers import make_raster, make_shapefile, point_file


class FakeKumoyProvider(QgsProcessingProvider):
    """kumoy の Processing プロバイダが登録されている状態を作る。"""

    def id(self):
        return "kumoy"

    def name(self):
        return "Kumoy"

    def loadAlgorithms(self):
        pass


@pytest.fixture
def kumoy_provider(qgis_app):
    provider = FakeKumoyProvider()
    registry = QgsApplication.processingRegistry()
    assert registry.addProvider(provider)
    yield provider
    registry.removeProvider(provider)


@pytest.fixture
def token_key(monkeypatch):
    """kumoy の実設定に触れないよう、トークンの保存先を試験用キーにする。"""
    key = "ksj-tests/kumoy-token"
    monkeypatch.setattr(kumoy_upload, "TOKEN_KEY", key)
    QSettings().remove(key)
    yield key
    QSettings().remove(key)


@pytest.fixture
def notifications(monkeypatch):
    messages = []
    monkeypatch.setattr(
        kumoy_upload, "notify", lambda message, warning=False: messages.append(message)
    )
    return messages


def availability(monkeypatch, *answers):
    """is_available の戻り値を呼び出し順に差し替える。"""
    remaining = list(answers)
    monkeypatch.setattr(kumoy_upload, "is_available", lambda: remaining.pop(0))


def test_unavailable_without_kumoy_provider(qgis_app):
    assert not kumoy_upload.is_available()


def test_available_when_kumoy_provider_is_registered(kumoy_provider):
    assert kumoy_upload.is_available()
    assert kumoy_upload.ensure_available() is True


def test_ready_requires_login_token(kumoy_provider, token_key, notifications):
    assert kumoy_upload.ready() is False
    assert notifications == [kumoy_upload.LOGIN_MESSAGE]
    QSettings().setValue(token_key, "session")
    assert kumoy_upload.ready() is True


def test_ready_is_false_when_plugin_stays_unavailable(monkeypatch, notifications):
    monkeypatch.setattr(kumoy_upload, "ensure_available", lambda parent=None: False)
    assert kumoy_upload.ready() is False
    assert notifications == []


def test_disabled_plugin_is_enabled_after_confirmation(monkeypatch):
    availability(monkeypatch, False, True)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: "kumoy_qgis_plugin")
    asked, enabled = [], []
    monkeypatch.setattr(
        kumoy_upload, "confirm", lambda parent, title, text: asked.append(text) or True
    )
    monkeypatch.setattr(kumoy_upload, "enable", enabled.append)
    monkeypatch.setattr(
        kumoy_upload, "install", lambda: pytest.fail("インストール済みなら取得しない")
    )
    assert kumoy_upload.ensure_available() is True
    assert asked == [kumoy_upload.ENABLE_PROMPT]
    assert enabled == ["kumoy_qgis_plugin"]


def test_missing_plugin_is_installed_after_confirmation(monkeypatch):
    availability(monkeypatch, False, True)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: None)
    asked, installed = [], []
    monkeypatch.setattr(
        kumoy_upload, "confirm", lambda parent, title, text: asked.append(text) or True
    )
    monkeypatch.setattr(kumoy_upload, "install", lambda: installed.append(True))
    assert kumoy_upload.ensure_available() is True
    assert asked == [kumoy_upload.INSTALL_PROMPT]
    assert installed == [True]
    assert kumoy_upload.KUMOY_URL in kumoy_upload.INSTALL_PROMPT


def test_declined_installation_leaves_plugin_unavailable(monkeypatch):
    availability(monkeypatch, False, False)
    monkeypatch.setattr(kumoy_upload, "installed_package", lambda: None)
    monkeypatch.setattr(kumoy_upload, "confirm", lambda parent, title, text: False)
    monkeypatch.setattr(
        kumoy_upload, "install", lambda: pytest.fail("断られたら取得しない")
    )
    assert kumoy_upload.ensure_available() is False


def test_installed_package_is_found_by_metadata_name(monkeypatch):
    monkeypatch.setattr(utils, "updateAvailablePlugins", lambda: None)
    monkeypatch.setattr(utils, "available_plugins", ["other", "kumoy_dev"])
    monkeypatch.setattr(
        utils,
        "pluginMetadata",
        lambda package, key: {"kumoy_dev": "Kumoy"}.get(package, "Other"),
    )
    assert kumoy_upload.installed_package() == "kumoy_dev"
    monkeypatch.setattr(utils, "available_plugins", ["other"])
    assert kumoy_upload.installed_package() is None


def test_enable_loads_starts_and_remembers_plugin(monkeypatch):
    calls = []
    monkeypatch.setattr(
        utils, "loadPlugin", lambda package: calls.append(("load", package)) or True
    )
    monkeypatch.setattr(
        utils, "startPlugin", lambda package: calls.append(("start", package)) or True
    )
    key = "PythonPlugins/kumoy_test"
    QgsSettings().remove(key)
    try:
        kumoy_upload.enable("kumoy_test")
        assert calls == [("load", "kumoy_test"), ("start", "kumoy_test")]
        assert QgsSettings().value(key, False, type=bool) is True
    finally:
        QgsSettings().remove(key)


def fake_installer(monkeypatch, available, broken=False):
    """QGIS 同梱のプラグインインストーラを差し替え、呼び出しを記録する。"""
    calls = []
    installer = SimpleNamespace(
        fetchAvailablePlugins=lambda reloadMode: calls.append(("fetch", reloadMode)),
        installPlugin=lambda key: calls.append(("install", key)),
        showPluginManagerWhenReady=lambda: calls.append(("manager",)),
    )

    def instance():
        if broken:
            raise RuntimeError("壊れたインストーラ")
        return installer

    package = types.ModuleType("pyplugin_installer")
    package.instance = instance
    data = types.ModuleType("pyplugin_installer.installer_data")
    data.plugins = SimpleNamespace(all=lambda: available)
    monkeypatch.setitem(sys.modules, "pyplugin_installer", package)
    monkeypatch.setitem(sys.modules, "pyplugin_installer.installer_data", data)
    return calls


def test_install_uses_official_repository_when_listed(monkeypatch, notifications):
    monkeypatch.setattr(kumoy_upload, "is_available", lambda: True)
    calls = fake_installer(monkeypatch, {"kumoy_qgis_plugin": {}})
    kumoy_upload.install()
    assert calls == [("fetch", False), ("install", "kumoy_qgis_plugin")]
    assert notifications == []


def test_install_opens_plugin_manager_when_not_listed(monkeypatch, notifications):
    calls = fake_installer(monkeypatch, {})
    kumoy_upload.install()
    assert calls == [("fetch", False), ("manager",)]
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]


def test_install_failure_is_logged_and_guides_manual_install(
    monkeypatch, notifications
):
    logged = []
    monkeypatch.setattr(
        kumoy_upload,
        "log_message",
        lambda message, warning=False: logged.append(message),
    )
    fake_installer(monkeypatch, {}, broken=True)
    kumoy_upload.install()
    assert any("壊れたインストーラ" in message for message in logged)
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]


@pytest.fixture
def fake_processing(monkeypatch):
    """kumoy のダイアログと地図追加を差し替え、渡されたレイヤーの状態を記録する。"""
    calls = SimpleNamespace(
        dialogs=[], loads=[], results={"VECTOR_ID": "vec-1"}, load_error=None
    )

    def exec_dialog(algorithm, parameters):
        layer = parameters["INPUT"]
        project = QgsProject.instance()
        calls.dialogs.append(
            (
                algorithm,
                layer.name(),
                project.mapLayer(layer.id()) is not None,
                project.layerTreeRoot().findLayer(layer.id()) is None,
                layer.dataProvider().encoding()
                if isinstance(layer, QgsVectorLayer)
                else None,
            )
        )
        return dict(calls.results)

    def run_and_load(algorithm, parameters):
        calls.loads.append((algorithm, parameters))
        if calls.load_error is not None:
            raise calls.load_error

    monkeypatch.setattr(
        kumoy_upload,
        "processing_module",
        lambda: SimpleNamespace(
            execAlgorithmDialog=exec_dialog, runAndLoadResults=run_and_load
        ),
    )
    return calls


@pytest.fixture
def confirmed_encoding(monkeypatch):
    """文字コード確認ダイアログを差し替え、呼ばれたレイヤー名を記録する。"""
    confirmed = []
    monkeypatch.setattr(
        encoding_check,
        "confirm_encoding",
        lambda layer, parent=None: confirmed.append(layer.name()) or True,
    )
    return confirmed


def test_upload_registers_hidden_layer_then_adds_kumoy_layer_and_cleans_workspace(
    qgis_app,
    qgis_new_project,
    tmp_path,
    temp_root,
    fake_processing,
    confirmed_encoding,
    notifications,
):
    workspace = temporary_files.workspace()
    # .cpg を付けて QGIS の既定に依存せず UTF-8 で読ませる（確認ダイアログは差し替え済み）。
    path = make_shapefile(
        Path(workspace.name) / "city.shp", ["札幌市"], "utf-8", cpg="UTF-8"
    )
    kumoy_upload.upload_layers([("ogr", str(path), "city")], workspace)
    assert fake_processing.dialogs == [
        ("kumoy:uploadvector", "city", True, True, "UTF-8")
    ]
    assert fake_processing.loads == [("kumoy:addvectortomap", {"VECTOR_ID": "vec-1"})]
    assert confirmed_encoding == ["city"]
    assert notifications == ["kumoy にアップロードしました: city"]
    assert not QgsProject.instance().mapLayers()
    assert not Path(workspace.name).exists()


def test_upload_raster_uses_raster_algorithms(
    qgis_app,
    qgis_new_project,
    tmp_path,
    fake_processing,
    confirmed_encoding,
    notifications,
):
    fake_processing.results = {"RASTER_ID": "ras-1"}
    path = make_raster(tmp_path / "height.tif")
    kumoy_upload.upload_layers([("gdal", str(path), "height")], None)
    assert [call[:2] for call in fake_processing.dialogs] == [
        ("kumoy:uploadraster", "height")
    ]
    assert fake_processing.loads == [("kumoy:addrastertomap", {"RASTER_ID": "ras-1"})]
    assert confirmed_encoding == []
    assert notifications == ["kumoy にアップロードしました: height"]


def test_geojson_is_uploaded_without_encoding_dialog(
    qgis_app, qgis_new_project, tmp_path, fake_processing, confirmed_encoding
):
    kumoy_upload.upload_layers([("ogr", str(point_file(tmp_path)), "dams")], None)
    assert confirmed_encoding == []
    assert len(fake_processing.dialogs) == 1


def test_canceled_dialog_uploads_nothing_and_still_cleans_workspace(
    qgis_app,
    qgis_new_project,
    temp_root,
    fake_processing,
    confirmed_encoding,
    notifications,
):
    fake_processing.results = {}
    workspace = temporary_files.workspace()
    path = point_file(Path(workspace.name))
    kumoy_upload.upload_layers([("ogr", str(path), "dams")], workspace)
    assert fake_processing.loads == [] and notifications == []
    assert not QgsProject.instance().mapLayers()
    assert not Path(workspace.name).exists()


def test_canceled_encoding_dialog_skips_the_layer(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, fake_processing
):
    monkeypatch.setattr(
        encoding_check, "confirm_encoding", lambda layer, parent=None: False
    )
    path = make_shapefile(tmp_path / "city.shp", ["札幌市"], "utf-8")
    kumoy_upload.upload_layers([("ogr", str(path), "city")], None)
    assert fake_processing.dialogs == []


def test_failed_map_addition_is_reported_after_upload(
    qgis_app,
    qgis_new_project,
    tmp_path,
    fake_processing,
    confirmed_encoding,
    notifications,
):
    fake_processing.load_error = RuntimeError("選択中のプロジェクトではありません")
    kumoy_upload.upload_layers([("ogr", str(point_file(tmp_path)), "dams")], None)
    assert notifications == [kumoy_upload.ADDED_ELSEWHERE_MESSAGE]


def test_invalid_and_failing_layers_are_reported_and_do_not_stop_others(
    qgis_app, qgis_new_project, tmp_path, monkeypatch, fake_processing, notifications
):
    def exploding_dialog(algorithm, parameters):
        raise RuntimeError("kumoy 側の例外")

    good = point_file(tmp_path, "good.geojson")
    bad = point_file(tmp_path, "bad.geojson")
    original = kumoy_upload.processing_module
    requests = []

    def module():
        # 最初のアップロード（bad）だけ kumoy 側の例外にし、次（good）は通常どおり。
        requests.append(True)
        if len(requests) == 1:
            return SimpleNamespace(
                execAlgorithmDialog=exploding_dialog, runAndLoadResults=lambda *a: None
            )
        return original()

    monkeypatch.setattr(kumoy_upload, "processing_module", module)
    kumoy_upload.upload_layers(
        [
            ("ogr", "/missing.geojson", "missing"),
            ("ogr", str(bad), "bad"),
            ("ogr", str(good), "good"),
        ],
        None,
    )
    assert [call[1] for call in fake_processing.dialogs] == ["good"]
    assert "kumoy へのアップロードに失敗しました: bad (kumoy 側の例外)" in notifications
    assert "読み込めないレイヤー: missing" in notifications
    assert not QgsProject.instance().mapLayers()


def test_installer_fetch_error_opens_manual_installation(monkeypatch, notifications):
    calls = fake_installer(monkeypatch, {})
    installer = sys.modules["pyplugin_installer"].instance()

    def fail_fetch(reloadMode):
        raise RuntimeError("リポジトリ取得失敗")

    installer.fetchAvailablePlugins = fail_fetch
    kumoy_upload.install()
    assert calls == [("manager",)]
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]


def test_canceled_shapefile_is_closed_before_workspace_cleanup(
    qgis_app, temp_root, monkeypatch, fake_processing
):
    from qgis.PyQt import sip

    workspace = temporary_files.workspace()
    path = make_shapefile(Path(workspace.name) / "city.shp", ["札幌市"], "cp932")
    layers = []

    def cancel(layer, parent=None):
        layers.append(layer)
        return False

    cleanup = temporary_files.cleanup

    def check_closed(directory):
        assert all(sip.isdeleted(layer) for layer in layers)
        cleanup(directory)

    monkeypatch.setattr(encoding_check, "confirm_encoding", cancel)
    monkeypatch.setattr(temporary_files, "cleanup", check_closed)
    kumoy_upload.upload_layers([("ogr", str(path), "city")], workspace)
    assert not Path(workspace.name).exists()


def test_installer_silent_failure_opens_manual_installation(monkeypatch, notifications):
    calls = fake_installer(monkeypatch, {"kumoy_qgis_plugin": {}})
    monkeypatch.setattr(kumoy_upload, "is_available", lambda: False)
    kumoy_upload.install()
    assert calls == [("fetch", False), ("install", "kumoy_qgis_plugin"), ("manager",)]
    assert notifications == [kumoy_upload.MANUAL_INSTALL_MESSAGE]


def test_browser_cancel_during_encoding_stops_all_uploads(
    qgis_app, qgis_new_project, temp_root, monkeypatch, fake_processing
):
    from ksj import layer_loading

    workspace = temporary_files.workspace()
    path = make_shapefile(Path(workspace.name) / "city.shp", ["札幌市"], "cp932")
    key = layer_loading.LoadKey("https://example.org/data.zip", "city.shp", "kumoy", "")
    task = layer_loading.LayerLoadTask(key, "city")
    task.result = {"temporary": workspace, "layers": [("ogr", str(path), "city")] * 2}
    layer_loading._register(task)
    confirmed = []

    def cancel(layer, parent=None):
        confirmed.append(layer.name())
        task.cancel()
        return True

    monkeypatch.setattr(encoding_check, "confirm_encoding", cancel)
    layer_loading._finish(task)
    assert confirmed == ["city"]
    assert fake_processing.dialogs == []
    assert not Path(workspace.name).exists()
    assert not layer_loading.pending


def test_mesh_index_removed_during_upload_stops_remaining_layers(
    qgis_app, qgis_new_project, temp_root, monkeypatch, notifications
):
    from ksj import mesh_index

    project = QgsProject.instance()
    index = QgsVectorLayer("Point?crs=EPSG:4326", "index", "memory")
    project.addMapLayer(index)
    index_id = index.id()
    workspace = temporary_files.workspace()
    path = str(point_file(Path(workspace.name)))
    task = SimpleNamespace(isCanceled=lambda: False)
    url = "https://example.org/data.zip"
    mesh_index._pending[url] = task
    dialogs, loads = [], []

    def clear_project(algorithm, parameters):
        dialogs.append(algorithm)
        project.clear()
        return {"VECTOR_ID": "uploaded"}

    monkeypatch.setattr(mesh_index, "choose_layers", lambda choices: choices)
    monkeypatch.setattr(
        kumoy_upload,
        "processing_module",
        lambda: SimpleNamespace(
            execAlgorithmDialog=clear_project,
            runAndLoadResults=lambda *args: loads.append(args),
        ),
    )
    result = {"layers": [("ogr", path, "dams")] * 2, "failed": []}
    mesh_index.finish_loading(task, index_id, url, None, result, "kumoy", workspace)
    assert dialogs == ["kumoy:uploadvector"]
    assert loads == []
    assert not notifications
    assert not Path(workspace.name).exists()
    assert not mesh_index._pending
