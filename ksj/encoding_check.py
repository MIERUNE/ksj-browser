"""Shapefile の文字コードを取得済みファイルから判定し、レイヤーへ適用する。

国土数値情報の Shapefile は古い配布が cp932、近年は UTF-8 で、両版を
``UTF-8`` / ``Shift_JIS`` フォルダに同梱する配布もある。`.cpg` が無いと QGIS は
UTF-8 で読むため cp932 の属性が文字化けする。ローカルの `.dbf` だけを読み、通信しない。
"""

import struct
from collections import namedtuple
from pathlib import Path

from .messages import log_message

UTF8 = "UTF-8"
SHIFT_JIS = "Shift_JIS"
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

# encoding は UTF8 / SHIFT_JIS / None。reason は利用者向けの根拠。
# confident は属性値のバイト列で判定したか（補助判定なら False）。
Detection = namedtuple("Detection", "encoding reason confident")


def sidecar(shp_path, suffix):
    """同名の付属ファイル。大文字拡張子の配布にも対応する。"""
    path = Path(shp_path)
    for candidate in (path.with_suffix(suffix), path.with_suffix(suffix.upper())):
        if candidate.is_file():
            return candidate
    return path.with_suffix(suffix)


def dbf_text_samples(dbf_path):
    """先頭レコードの文字列フィールド（型 C）の生バイト列。"""
    with open(dbf_path, "rb") as source:
        header = source.read(32)
        if len(header) < 32:
            return []
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
    return samples


def has_non_ascii(samples):
    return any(byte > 0x7F for sample in samples for byte in sample)


def decodes(samples, codec):
    try:
        for sample in samples:
            sample.decode(codec)
    except UnicodeDecodeError:
        return False
    return True


def hint(shp_path):
    """属性値で決まらないときの補助判定。.cpg → 言語ID → フォルダ名の順。"""
    cpg = sidecar(shp_path, ".cpg")
    if cpg.is_file():
        try:
            name = cpg.read_text(encoding="ascii", errors="ignore").strip().upper()
        except OSError:
            name = ""
        if name in CPG_NAMES:
            return CPG_NAMES[name], REASON_CPG
    try:
        with open(sidecar(shp_path, ".dbf"), "rb") as source:
            header = source.read(32)
    except OSError:
        header = b""
    if len(header) >= 32 and header[29] in SHIFT_JIS_LDIDS:
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
        samples = dbf_text_samples(sidecar(shp_path, ".dbf"))
    except OSError:
        samples = []
    if has_non_ascii(samples):
        # 両方で復号できる値もあるが、仕様に従い UTF-8 を優先する。
        if decodes(samples, "utf-8"):
            return Detection(UTF8, REASON_BYTES, True)
        if decodes(samples, "cp932"):
            return Detection(SHIFT_JIS, REASON_BYTES, True)
    encoding, reason = hint(shp_path)
    return Detection(encoding, reason, False)


def source_path(layer):
    """レイヤーの参照先ファイル。サブレイヤーの "パス|layername=名前" からもパスだけ取り出す。"""
    return Path(layer.source().split("|", 1)[0])


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
