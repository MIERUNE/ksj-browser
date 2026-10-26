"""metadata.txt が QGIS 3.44 から 4.x までの読み込み条件を満たし、pyproject.toml と版が揃っていること。"""

import configparser
import re
import struct
from pathlib import Path

METADATA = Path(__file__).resolve().parents[1] / "metadata.txt"
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


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


def test_version_matches_pyproject():
    # リリース時は metadata.txt と pyproject.toml の両方を手で更新する。
    # Python 3.9 には tomllib がないため version 行を正規表現で読む。
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    assert match is not None
    assert load_metadata()["version"] == match.group(1)


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
