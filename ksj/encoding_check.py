"""Shapefile の文字コードを取得済みファイルから判定し、レイヤーへ適用する。

国土数値情報の Shapefile は古い配布が cp932、近年は UTF-8 で、両版を
``UTF-8`` / ``Shift_JIS`` フォルダに同梱する配布もある。`.cpg` が無いと QGIS は
UTF-8 で読むため cp932 の属性が文字化けする。ローカルの `.dbf` だけを読み、通信しない。
"""

import struct
from collections import namedtuple
from pathlib import Path

from qgis.core import Qgis, QgsFeatureRequest, QgsProviderRegistry
from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .messages import log_message

UTF8 = "UTF-8"
SHIFT_JIS = "Shift_JIS"
EUC_JP = "EUC-JP"
# 利用者が明示指定できる文字コード。Processing と確認ダイアログの選択肢に使う。
# EUC-JP は国土数値情報に無いため自動判定しない。
ENCODINGS = (UTF8, SHIFT_JIS, EUC_JP)
# 判定に使う先頭レコード数。大きな .dbf でも読み込みを軽く保つ。
SAMPLE_RECORDS = 20
# .dbf ヘッダ 30 バイト目の言語ドライバID。日本語 (cp932) を示す値。
SHIFT_JIS_LDIDS = {0x13, 0x7B}
CPG_NAMES = {
    "UTF-8": UTF8,
    "UTF8": UTF8,
    "CP932": SHIFT_JIS,
    "SHIFT_JIS": SHIFT_JIS,
    "SHIFT-JIS": SHIFT_JIS,
    "SJIS": SHIFT_JIS,
    "932": SHIFT_JIS,
}
# フォルダ名に含まれていれば手がかりにする語（小文字）。
PATH_HINTS = (
    ("utf-8", UTF8),
    ("utf8", UTF8),
    ("shift_jis", SHIFT_JIS),
    ("shift-jis", SHIFT_JIS),
    ("sjis", SHIFT_JIS),
    ("cp932", SHIFT_JIS),
)
REASON_BYTES = "属性値から判定"
REASON_CPG = ".cpg から判定"
REASON_LDID = ".dbf の言語IDから判定"
REASON_FOLDER = "フォルダ名から判定"
UNDETERMINED = "文字コードを判定できませんでした"

# 確認ダイアログのプレビュー行数と題名。
PREVIEW_ROWS = 5
DIALOG_TITLE = "kumoy へアップロードする前に文字コードを確認"

# encoding は UTF8 / SHIFT_JIS / None。reason は利用者向けの根拠。
# confident は属性値のバイト列で判定したか（補助判定なら False）。
Detection = namedtuple("Detection", "encoding reason confident")


def sidecar(shp_path, suffix):
    """同名の付属ファイル。小文字拡張子が無ければ大文字拡張子の配布とみなす。"""
    path = Path(shp_path).with_suffix(suffix)
    return path if path.is_file() else path.with_suffix(suffix.upper())


def read_dbf(dbf_path):
    """ヘッダの言語ドライバIDと、先頭レコードの文字列フィールド（型 C）の生バイト列。"""
    with open(dbf_path, "rb") as source:
        header = source.read(32)
        if len(header) < 32:
            return 0, []
        record_count, header_length, record_length = struct.unpack("<IHH", header[4:12])
        fields = []
        while source.tell() + 32 <= header_length:
            descriptor = source.read(32)
            if len(descriptor) < 32 or descriptor[0] == 0x0D:
                break
            fields.append((chr(descriptor[11]), descriptor[16]))
        source.seek(header_length)
        samples = []
        for _ in range(min(record_count, SAMPLE_RECORDS)):
            record = source.read(record_length)
            if len(record) < record_length:
                break
            position = 1  # 先頭バイトは削除フラグ
            for field_type, length in fields:
                if field_type == "C":
                    samples.append(record[position : position + length].strip(b"\x00 "))
                position += length
    return header[29], samples


def decodes(samples, codec):
    try:
        for sample in samples:
            sample.decode(codec)
    except UnicodeDecodeError:
        return False
    return True


def hint(shp_path, ldid):
    """属性値で決まらないときの補助判定。.cpg → 言語ID → フォルダ名の順。"""
    try:
        name = sidecar(shp_path, ".cpg").read_text(encoding="ascii", errors="ignore")
    except OSError:
        name = ""
    name = name.strip().upper()
    if name in CPG_NAMES:
        return CPG_NAMES[name], REASON_CPG
    if ldid in SHIFT_JIS_LDIDS:
        return SHIFT_JIS, REASON_LDID
    # 国土数値情報は UTF-8 版と Shift_JIS 版を同名のフォルダで同梱することがある。
    for folder in reversed(Path(shp_path).parent.parts):
        lowered = folder.lower()
        for token, encoding in PATH_HINTS:
            if token in lowered:
                return encoding, REASON_FOLDER
    return None, UNDETERMINED


def detect_shapefile_encoding(shp_path):
    """取得済み Shapefile の文字コードを判定する。通信しない。"""
    try:
        ldid, samples = read_dbf(sidecar(shp_path, ".dbf"))
    except OSError:
        ldid, samples = 0, []
    if any(not sample.isascii() for sample in samples):
        # 両方で復号できる値もあるが、仕様に従い UTF-8 を優先する。
        if decodes(samples, "utf-8"):
            return Detection(UTF8, REASON_BYTES, True)
        if decodes(samples, "cp932"):
            return Detection(SHIFT_JIS, REASON_BYTES, True)
    encoding, reason = hint(shp_path, ldid)
    return Detection(encoding, reason, False)


def source_path(layer):
    """レイヤーの参照先ファイル。"パス|layername=名前" のようなサブレイヤー URI からもパスだけ取り出す。"""
    registry = QgsProviderRegistry.instance()
    decoded = registry.decodeUri(layer.providerType(), layer.source())
    return Path(decoded.get("path") or layer.source())


def is_shapefile_layer(layer):
    return layer.providerType() == "ogr" and source_path(layer).suffix.lower() == ".shp"


def provider_encoding(encoding):
    """日本語の Shift_JIS は、拡張漢字を保持する CP932 としてプロバイダーに渡す。"""
    return "CP932" if encoding == SHIFT_JIS else encoding


def apply_detected_encoding(layer):
    """判定した文字コードをレイヤーに設定する。判定不能なら QGIS の既定に任せる。

    Shapefile 以外は None を返す。GeoJSON などは GDAL が UTF-8 固定で、
    QGIS は setProviderEncoding() を無視する。
    """
    if not is_shapefile_layer(layer):
        return None
    path = source_path(layer)
    detection = detect_shapefile_encoding(path)
    if detection.encoding is None:
        return detection
    before = layer.dataProvider().encoding()
    layer.setProviderEncoding(provider_encoding(detection.encoding))
    # Qt の環境によって CP932 の名称が Shift_JIS に正規化される。
    if layer.dataProvider().encoding() != before:
        log_message(f"文字コードを {detection.encoding} と判定して適用: {path.name}")
    return detection


def string_fields(layer):
    return [field for field in layer.fields() if field.type() == QMetaType.Type.QString]


def preview_rows(layer, fields):
    """先頭地物の文字列属性。ジオメトリは読まない。"""
    names = [field.name() for field in fields]
    request = (
        QgsFeatureRequest()
        .setFlags(Qgis.FeatureRequestFlag.NoGeometry)
        .setLimit(PREVIEW_ROWS)
        .setSubsetOfAttributes(names, layer.fields())
    )
    rows = []
    for feature in layer.getFeatures(request):
        values = [feature.attribute(name) for name in names]
        rows.append([value if isinstance(value, str) else "" for value in values])
    return rows


class EncodingDialog(QDialog):
    """文字コードを切り替えながら属性を確かめ、アップロードする文字コードを決める。"""

    def __init__(self, layer, detection, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.setObjectName("ksj-encoding")
        self.setWindowTitle(DIALOG_TITLE)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(source_path(layer).name))
        reason = QLabel(detection.reason)
        reason.setObjectName("ksj-encoding-reason")
        if detection.encoding is None:
            reason.setText(f"{UNDETERMINED}。プレビューで確認してください。")
            reason.setStyleSheet("color: #b00020;")
        layout.addWidget(reason)
        row = QHBoxLayout()
        row.addWidget(QLabel("文字コード"))
        self.encoding = QComboBox()
        self.encoding.addItems(list(ENCODINGS))
        self.encoding.setCurrentText(detection.encoding or UTF8)
        row.addWidget(self.encoding)
        row.addStretch()
        layout.addLayout(row)
        self.preview = QTableWidget()
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.preview)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "この内容でアップロード"
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.encoding.currentTextChanged.connect(self.apply_encoding)
        self.apply_encoding(self.encoding.currentText())
        self.resize(640, 360)

    def apply_encoding(self, encoding):
        """レイヤーの文字コードを切り替えてプレビューを引き直す。ローカルファイルなので即時。"""
        self.layer.setProviderEncoding(provider_encoding(encoding))
        # 列名自体も文字コード変更で再デコードされるため、毎回取り直す。
        fields = string_fields(self.layer)
        rows = preview_rows(self.layer, fields)
        self.preview.clear()
        self.preview.setColumnCount(len(fields))
        self.preview.setHorizontalHeaderLabels([field.name() for field in fields])
        self.preview.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for column, value in enumerate(values):
                self.preview.setItem(row_index, column, QTableWidgetItem(value))


def confirm_encoding(layer, parent=None):
    """kumoy へ送る前に文字コードを利用者に確かめてもらう。OK なら True、キャンセルは False。

    文字列フィールドが無ければ文字コードは無関係なのでダイアログを出さない。
    """
    if not string_fields(layer):
        return True
    dialog = EncodingDialog(
        layer, detect_shapefile_encoding(source_path(layer)), parent
    )
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    dialog.deleteLater()
    return accepted
