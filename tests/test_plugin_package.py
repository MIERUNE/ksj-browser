"""配布 ZIP が追跡ファイルだけを ksj_browser/ 配下に含み、plugins.qgis.org の要件を満たすこと。"""

import configparser
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-plugin-zip.sh"
# plugins.qgis.org は ZIP 直下のフォルダ名でプラグインを識別する。
PACKAGE = "ksj_browser"
# build-plugin-zip.sh に渡す版。リリースではタグ v<version> から v を除いた値が入る。
VERSION = "1.2.3"
# scripts/build-plugin-zip.sh の paths と同じ。同梱するパスを変えるときは両方を直す。
PATHS = ["ksj", "__init__.py", "plugin.py", "metadata.txt", "LICENSE"]
# plugins.qgis.org の上限（validator.py の PLUGIN_MAX_UPLOAD_SIZE）。
MAX_SIZE = 25_000_000
# ksj/ は丸ごと入るため、コミットされた不要物（.DS_Store・*.pyc・メモなど）を拾えるよう、ZIP に入るファイルを許可リストで縛る。
# .github/workflows/release.yaml の allowed と同じにする。
ALLOWED = re.compile(
    rf"{PACKAGE}/(LICENSE|metadata\.txt|__init__\.py|plugin\.py"
    r"|ksj/[a-z_]+\.py|ksj/catalog/[A-Za-z0-9_.-]+\.json|ksj/icons/[a-z-]+\.(svg|png))"
)

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
        ["bash", os.fspath(SCRIPT), VERSION, "HEAD", os.fspath(out_dir)],
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


def test_zip_name_and_metadata_use_the_given_version(package_zip):
    assert package_zip.name == f"{PACKAGE}-{VERSION}.zip"
    with zipfile.ZipFile(package_zip) as archive:
        assert zip_metadata(archive)["version"] == VERSION


def test_only_the_version_line_is_rewritten(package_zip):
    # 版のプレースホルダー以外は、HEAD の metadata.txt をそのまま ZIP に入れる。
    head = subprocess.run(
        ["git", "-C", os.fspath(ROOT), "show", "HEAD:metadata.txt"],
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=git_env(),
    ).stdout
    with zipfile.ZipFile(package_zip) as archive:
        packaged = archive.read(f"{PACKAGE}/metadata.txt").decode("utf-8")
    assert packaged == head.replace("version={{PLUGIN_VERSION}}", f"version={VERSION}")
    assert "{{" not in packaged


@pytest.mark.parametrize("version", ["", "v1.2.3", "1.2", "1.2.3-rc1"])
def test_script_rejects_a_malformed_version(tmp_path, version):
    result = subprocess.run(
        ["bash", os.fspath(SCRIPT), version, "HEAD", os.fspath(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        env=git_env(),
    )
    assert result.returncode != 0
    assert list(tmp_path.iterdir()) == []


def test_icon_is_included(package_zip):
    # icon はプラグインディレクトリからの相対パス。
    with zipfile.ZipFile(package_zip) as archive:
        icon = zip_metadata(archive)["icon"]
        assert f"{PACKAGE}/{icon}" in archive.namelist()


def test_zip_is_under_site_limit(package_zip):
    assert package_zip.stat().st_size < MAX_SIZE


def test_zip_has_no_stray_files(package_zip):
    with zipfile.ZipFile(package_zip) as archive:
        names = archive.namelist()
    # --add-file で足した metadata.txt が、追跡ファイルの metadata.txt と二重にならないこと。
    assert len(names) == len(set(names))
    strays = [
        name for name in names if not name.endswith("/") and not ALLOWED.fullmatch(name)
    ]
    assert strays == []
