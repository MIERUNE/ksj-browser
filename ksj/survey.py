"""GUIからの初回ダウンロード時に、任意のアンケートを一度だけ案内する。"""

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMessageBox

from . import local_storage, remote_zip
from .messages import main_window

PROMPTED_KEY = "ksj/survey_prompted"
SURVEY_URL = (
    "https://docs.google.com/forms/d/"
    "1-J1_3_NPwYy8cpH7yfwRlKa5iYaN9zw6S4ng4e0PuEs/viewform?usp=sf_link"
)


def prompt_once():
    """GUIスレッド専用。回答や閉じ方にかかわらず、同じプロファイルでは再表示しない。"""
    settings = QgsSettings()
    if settings.value(PROMPTED_KEY, False, type=bool):
        return
    # モーダル表示中に別の処理が入っても、二重に案内しない。
    settings.setValue(PROMPTED_KEY, True)
    dialog = QMessageBox(main_window())
    dialog.setWindowTitle("国土数値情報ブラウザ")
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setText("ユーザーアンケートに回答しますか？")
    dialog.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    dialog.button(QMessageBox.StandardButton.Yes).setText("はい")
    dialog.button(QMessageBox.StandardButton.No).setText("いいえ")
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    dialog.setEscapeButton(QMessageBox.StandardButton.No)
    answer = dialog.exec()
    dialog.deleteLater()
    if answer == QMessageBox.StandardButton.Yes:
        QDesktopServices.openUrl(QUrl(SURVEY_URL))


def prompt_for_download(url, directory, member=""):
    """保存済みデータの再利用では案内しない。取得開始前にGUIから呼ぶ。"""
    if QgsSettings().value(PROMPTED_KEY, False, type=bool):
        return
    try:
        saved = (
            remote_zip.saved_member(url, member, directory)
            if member
            else local_storage.saved_local_data(url, directory)
        )
    except (local_storage.DownloadError, OSError, ValueError):
        # 保存先などのエラーは既存のダウンロード処理で通知する。
        return
    if not saved:
        prompt_once()


def open_download(url):
    """ブラウザに配布ファイルを渡す場合も同じ初回判定を使う。"""
    prompt_once()
    return QDesktopServices.openUrl(QUrl(url))
