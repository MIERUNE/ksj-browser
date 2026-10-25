"""kumoy プラグインの Processing アルゴリズムで、取得したレイヤーを kumoy にアップロードする。

kumoy 側への依存はこのモジュールの定数に限る。プロバイダ ID、アルゴリズム ID と
出力名、QSettings のセッショントークン、公式リポジトリのパッケージ名。
kumoy の内部モジュールは import しない。
"""

from qgis import utils
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProject,
    QgsRasterLayer,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgsProjectionSelectionDialog
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QDialog, QMessageBox

from . import encoding_check, temporary_files
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
    installer = None
    try:
        from pyplugin_installer import instance
        from pyplugin_installer.installer_data import plugins

        installer = instance()
        installer.fetchAvailablePlugins(reloadMode=False)
        if PACKAGE_NAME in plugins.all():
            installer.installPlugin(PACKAGE_NAME)
            if is_available():
                return
    except Exception as exc:
        # QGIS 内部のインストーラ API に頼るため、失敗は手動インストールへ切り替える。
        log_message(
            f"kumoy プラグインのインストールを開始できません: {exc}", warning=True
        )
    if installer is not None:
        try:
            installer.showPluginManagerWhenReady()
        except Exception as exc:
            log_message(f"プラグインマネージャを開けません: {exc}", warning=True)
    notify(MANUAL_INSTALL_MESSAGE, warning=True)


def processing_module():
    """QGIS 同梱の processing。GUI 起動後に import できるため関数内で読み込む。"""
    import processing

    return processing


def confirm_crs(layer, parent=None):
    """未定義の座標系を利用者が指定する。座標値と元ファイルは変更しない。"""
    if layer.crs().isValid():
        return True
    dialog = QgsProjectionSelectionDialog(parent)
    dialog.setWindowTitle(f"アップロード前に座標系を設定: {layer.name()}")
    dialog.setMessage(
        "このデータには座標系が定義されていません。"
        "配布元の説明を確認し、元データの座標系を選んでください。"
        "選択した座標系を設定してから kumoy にアップロードします。"
        "座標値の変換は行いません。"
    )
    dialog.setShowNoProjection(False)
    dialog.setCrs(QgsCoordinateReferenceSystem())
    dialog.setRequireValidSelection()
    accepted = dialog.exec() == QDialog.DialogCode.Accepted and dialog.crs().isValid()
    if accepted:
        layer.setCrs(dialog.crs())
    dialog.deleteLater()
    return accepted


def upload_layers(layers, workspace, parent=None, is_current=lambda: True):
    """各レイヤーを kumoy のダイアログでアップロードし、終了後に一時ディレクトリを削除する。

    layers は prepare() と同じ (provider, source, title) の列。GUI スレッドで呼ぶ。
    """
    if parent is None:
        parent = main_window()
    unreadable = []
    try:
        for provider, source, title in layers:
            if not is_current():
                break
            layer_type = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
            options = layer_type.LayerOptions()
            # QGIS の既定 CRS で補完せず、元データが未定義なら明示選択してもらう。
            options.skipCrsValidation = True
            layer = layer_type(source, title, provider, options)
            try:
                if not layer.isValid():
                    unreadable.append(title)
                    continue
                shapefile = encoding_check.is_shapefile_layer(layer)
                if shapefile and not encoding_check.confirm_encoding(layer, parent):
                    continue
                if not is_current():
                    break
                if not confirm_crs(layer, parent):
                    continue
                if not is_current():
                    break
                if not upload(layer, provider, is_current):
                    break
            except Exception as exc:
                # kumoy 側の例外で残りのレイヤーと後片付けを止めない。
                notify(
                    f"kumoy へのアップロードに失敗しました: {title} ({exc})",
                    warning=True,
                )
            finally:
                # 取消・無効レイヤーもファイルを閉じてから一時ディレクトリを削除する。
                if not sip.isdeleted(layer):
                    sip.delete(layer)
    finally:
        if workspace is not None:
            temporary_files.cleanup(workspace)
    if unreadable:
        notify(f"読み込めないレイヤー: {', '.join(unreadable)}", warning=True)


def upload(layer, provider, is_current=lambda: True):
    """kumoy のダイアログで 1 レイヤーをアップロードし、完了したら地図へ追加する。

    ダイアログは QgsProject に登録されたレイヤーしか INPUT に受け付けないため、
    レイヤーツリーに出さずに登録し、終了後に外す。操作が無効になれば False を返す。
    """
    upload_id, result_key, add_id = ALGORITHMS[provider]
    processing = processing_module()
    project = QgsProject.instance()
    name = layer.name()
    layer_id = layer.id()
    project.addMapLayer(layer, False)
    try:
        results = processing.execAlgorithmDialog(upload_id, {"INPUT": layer}) or {}
        # ダイアログ中のプロジェクト clear は呼び出し元の判定に現れないため、登録も確かめる。
        current = is_current() and project.mapLayer(layer_id) is not None
    finally:
        # removeMapLayer はレイヤーを破棄する。以降 layer に触れない。
        project.removeMapLayer(layer_id)
    if not current:
        return False
    uploaded = results.get(result_key)
    if not uploaded:
        return True
    try:
        processing.runAndLoadResults(add_id, {result_key: uploaded})
    except Exception as exc:
        # kumoy ブラウザで選択中のプロジェクトと違う先へ送った場合など。
        log_message(f"kumoy レイヤーを地図に追加できません: {exc}", warning=True)
        notify(ADDED_ELSEWHERE_MESSAGE, warning=True)
        return True
    notify(f"kumoy にアップロードしました: {name}")
    return True
