"""metadata.txt が QGIS 3.44 から 4.x までの読み込み条件を満たし、版がリリースのタグで決まるプレースホルダーで、英語と日本語を併記していること。"""

import configparser
import re
import struct
from pathlib import Path

METADATA = Path(__file__).resolve().parents[1] / "metadata.txt"
JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
# 日本語の文にも QGIS・Processing などの英単語は混ざるため、英単語が 5 つ続く並びを英語の文とみなす。
ENGLISH_SENTENCE = re.compile(r"(?:[A-Za-z][A-Za-z0-9',.()/-]* ){5}")


def load_metadata():
    parser = configparser.ConfigParser()
    parser.read(METADATA, encoding="utf-8")
    return parser["general"]


def test_version_range_covers_qgis_3_and_4():
    general = load_metadata()
    assert general["qgisMinimumVersion"] == "3.44"
    # qgisMaximumVersion が無いと QGIS 4 は上限を 3.99 とみなして読み込まない。
    assert general["qgisMaximumVersion"] == "4.99"


def test_deprecated_qt6_flag_is_absent():
    # supportsQt6 は QGIS 4.0 正式版で無効化された。qgisMaximumVersion で代替する。
    assert "supportsQt6" not in load_metadata()


def test_name_is_english_only():
    # 日本語の名前は description と about に併記する。
    name = load_metadata()["name"]
    assert name.strip()
    assert name.isascii()


def test_no_locale_specific_fields():
    # name[ja] のような QGIS の表示言語別の項目は使わず、同じ項目に英語と日本語を併記する。
    assert [key for key in load_metadata() if "[" in key] == []


def test_description_and_about_have_english_and_japanese():
    general = load_metadata()
    for key in ("description", "about"):
        assert ENGLISH_SENTENCE.search(general[key]), key
        assert JAPANESE.search(general[key]), key


def test_version_is_the_placeholder_filled_from_the_release_tag():
    # 版はリリースのタグ v<version> で決まる。scripts/build-plugin-zip.sh が配布 ZIP の
    # metadata.txt にだけ書き込むので、リポジトリには固定の版を書かない。
    assert load_metadata()["version"] == "{{PLUGIN_VERSION}}"


def test_icon_file_exists():
    # icon はプラグインディレクトリからの相対パス。
    assert (METADATA.parent / load_metadata()["icon"]).is_file()


def test_icon_is_square_and_large_enough():
    # QGIS のプラグイン管理は配布アイコンを 64px 前後まで拡大して表示する。
    # Pillow は QGIS 同梱 Python にあるとは限らないので、PNG の IHDR を直接読む。
    data = (METADATA.parent / load_metadata()["icon"]).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert width == height
    assert width >= 64
