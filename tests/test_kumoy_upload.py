"""kumoy プラグインの確認・インストール支援と、取得したレイヤーのアップロード。"""

import sys
import types
from types import SimpleNamespace

import pytest
from qgis import utils
from qgis.core import QgsApplication, QgsProcessingProvider, QgsSettings
from qgis.PyQt.QtCore import QSettings

from ksj import kumoy_upload


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
