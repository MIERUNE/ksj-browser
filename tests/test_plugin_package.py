"""配布 ZIP が追跡ファイルだけを ksj_browser/ 配下に含み、plugins.qgis.org の要件を満たすこと。"""

import configparser
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-plugin-zip.sh"
# plugins.qgis.org は ZIP 直下のフォルダ名でプラグインを識別する。
PACKAGE = "ksj_browser"
# scripts/build-plugin-zip.sh の paths と同じ。同梱するパスを変えるときは両方を直す。
PATHS = ["ksj", "__init__.py", "plugin.py", "metadata.txt", "LICENSE"]
# plugins.qgis.org の上限（validator.py の PLUGIN_MAX_UPLOAD_SIZE）。
MAX_SIZE = 25_000_000

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git がない環境（QGIS 3.44 の Docker イメージなど）では配布 ZIP を作れない",
)


def git_env():
    """CI の Docker ではマウントした作業ツリーの所有者が違い、git が dubious ownership で拒否する。"""
    return {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": os.fspath(ROOT),
    }


@pytest.fixture(scope="module")
def package_zip(tmp_path_factory):
    """スクリプトを 1 回だけ実行し、作られた ZIP のパスを返す。"""
    out_dir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        ["bash", os.fspath(SCRIPT), "HEAD", os.fspath(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return Path(result.stdout.strip())


def tracked_files():
    """HEAD で追跡している同梱対象のパスに、ZIP 直下のフォルダ名を付けた集合。"""
    # quotePath が既定のままだと非 ASCII なファイル名をエスケープし、ZipFile.namelist() との比較が崩れる。
    output = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(ROOT),
            "-c",
            "core.quotePath=false",
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
        ]
        + PATHS,
        check=True,
        capture_output=True,
        text=True,
        env=git_env(),
    ).stdout
    return {f"{PACKAGE}/{line}" for line in output.splitlines()}


def zip_metadata(archive):
    parser = configparser.ConfigParser()
    parser.read_string(archive.read(f"{PACKAGE}/metadata.txt").decode("utf-8"))
    return parser["general"]


def test_zip_contains_exactly_the_tracked_files(package_zip):
    # 同梱漏れと混入（tests/、__pycache__/ など）を 1 つの比較で捉える。
    with zipfile.ZipFile(package_zip) as archive:
        assert archive.testzip() is None
        names = {name for name in archive.namelist() if not name.endswith("/")}
    assert names == tracked_files()


def test_zip_name_matches_metadata_version(package_zip):
    with zipfile.ZipFile(package_zip) as archive:
        version = zip_metadata(archive)["version"]
    assert package_zip.name == f"{PACKAGE}-{version}.zip"


def test_icon_is_included(package_zip):
    # icon はプラグインディレクトリからの相対パス。
    with zipfile.ZipFile(package_zip) as archive:
        icon = zip_metadata(archive)["icon"]
        assert f"{PACKAGE}/{icon}" in archive.namelist()


def test_zip_is_under_site_limit(package_zip):
    assert package_zip.stat().st_size < MAX_SIZE
