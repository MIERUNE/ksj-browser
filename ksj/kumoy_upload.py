"""kumoy プラグインの Processing アルゴリズムで、取得したレイヤーを kumoy にアップロードする。

kumoy 側への依存はこのモジュールの定数に限る。プロバイダ ID、アルゴリズム ID と
出力名、QSettings のセッショントークン、公式リポジトリのパッケージ名。
kumoy の内部モジュールは import しない。
"""

from qgis import utils
from qgis.core import (
    QgsApplication,
    QgsSettings,
)
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QMessageBox

from .messages import log_message, main_window, notify

KUMOY_URL = "https://www.kumoy.io/"
PROVIDER_ID = "kumoy"
# 公式プラグインリポジトリ（plugins.qgis.org）での名前と、metadata.txt の name。
PACKAGE_NAME = "kumoy_qgis_plugin"
PLUGIN_NAME = "Kumoy"
# kumoy プラグインがログイン時に保存するセッショントークン。空ならログイン前。
TOKEN_KEY = "Kumoy/session_token"
# provider → (アップロード, 結果の ID 名, 地図への追加)
ALGORITHMS = {
    "ogr": ("kumoy:uploadvector", "VECTOR_ID", "kumoy:addvectortomap"),
    "gdal": ("kumoy:uploadraster", "RASTER_ID", "kumoy:addrastertomap"),
}
LOGIN_MESSAGE = "kumoy ブラウザパネルの Kumoy 項目からログインしてください。"
INSTALL_PROMPT = (
    f'kumoy へのアップロードには <a href="{KUMOY_URL}">kumoy</a> プラグインが必要です。'
    "インストールしますか？"
)
ENABLE_PROMPT = "kumoy プラグインはインストール済みですが無効です。有効化しますか？"
MANUAL_INSTALL_MESSAGE = (
    f"プラグインマネージャで「{PLUGIN_NAME}」を検索してインストールしてください。"
)
ADDED_ELSEWHERE_MESSAGE = (
    "アップロードは完了しました。"
    "kumoy ブラウザでプロジェクトを切り替えてから追加してください。"
)


def is_available():
    """kumoy の Processing プロバイダが登録済みか。インストール先フォルダ名に依存しない。"""
    return QgsApplication.processingRegistry().providerById(PROVIDER_ID) is not None


def is_logged_in():
    return bool(QSettings().value(TOKEN_KEY, ""))


def ready(parent=None):
    """追加操作の開始前に、プラグインとログインを確かめる。"""
    if not ensure_available(parent):
        return False
    if not is_logged_in():
        notify(LOGIN_MESSAGE, warning=True)
        return False
    return True


def ensure_available(parent=None):
    """未インストール・無効なら利用者の了承を得て整える。整った場合だけ True。"""
    if is_available():
        return True
    if parent is None:
        parent = main_window()
    package = installed_package()
    if package:
        if confirm(parent, "kumoy プラグインの有効化", ENABLE_PROMPT):
            enable(package)
    elif confirm(parent, "kumoy プラグインのインストール", INSTALL_PROMPT):
        install()
    return is_available()


def installed_package():
    """インストール済みだが読み込まれていない kumoy のパッケージ名。なければ None。"""
    utils.updateAvailablePlugins()
    for package in utils.available_plugins:
        if utils.pluginMetadata(package, "name") == PLUGIN_NAME:
            return package
    return None


def confirm(parent, title, text):
    # QMessageBox はリッチテキストのリンクを既定で外部ブラウザで開く。
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def enable(package):
    if utils.loadPlugin(package) and utils.startPlugin(package):
        QgsSettings().setValue(f"PythonPlugins/{package}", True)


def install():
    """公式リポジトリから取得する。一覧に無い・失敗した場合は手動インストールを案内する。"""
    try:
        from pyplugin_installer import instance
        from pyplugin_installer.installer_data import plugins

        installer = instance()
        installer.fetchAvailablePlugins(reloadMode=False)
        if PACKAGE_NAME in plugins.all():
            installer.installPlugin(PACKAGE_NAME)
            return
        installer.showPluginManagerWhenReady()
    except Exception as exc:
        # QGIS 内部のインストーラ API に頼るため、失敗は手動インストールへ切り替える。
        log_message(
            f"kumoy プラグインのインストールを開始できません: {exc}", warning=True
        )
    notify(MANUAL_INSTALL_MESSAGE, warning=True)
