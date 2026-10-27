"""一時レイヤー用ディレクトリの作成と、レイヤーが閉じられた後の削除。"""

from pathlib import Path
from types import SimpleNamespace

from qgis.core import QgsProject, QgsVectorLayer

from ksj import temporary_files
from tests.helpers import point_geojson


def test_workspace_has_plugin_prefix_and_cleanup_removes_it(temp_root):
    workspace = temporary_files.workspace()
    path = Path(workspace.name)
    assert path.is_dir() and path.parent == temp_root
    assert path.name.startswith(temporary_files.PREFIX)
    temporary_files.cleanup(workspace)
    assert not path.exists()


def test_release_tracks_existing_duplicate_and_survives_readding_layer(
    qgis_app, qgis_new_project, temp_root
):
    project = QgsProject.instance()
    workspace = temporary_files.workspace()
    path = Path(workspace.name) / "point.geojson"
    path.write_text(point_geojson(), encoding="utf-8")
    original = QgsVectorLayer(str(path), "original", "ogr")
    duplicate = original.clone()
    project.addMapLayers([original, duplicate])
    temporary_files.release_when_closed(workspace, [original])
    taken = project.takeMapLayer(duplicate)
    try:
        project.removeMapLayer(original.id())
        assert path.is_file()
    finally:
        project.addMapLayer(taken)
    project.removeMapLayer(taken.id())
    assert not path.parent.exists()


def test_unrelated_layers_do_not_keep_workspace_alive(
    qgis_app, qgis_new_project, temp_root
):
    project = QgsProject.instance()
    workspace = temporary_files.workspace()
    root = Path(workspace.name)
    path = root / "point.geojson"
    path.write_text(point_geojson(), encoding="utf-8")
    original = QgsVectorLayer(str(path), "original", "ogr")
    temporary_files.release_when_closed(workspace, [original])
    # 文字列の前方一致だけでは隣のフォルダまで参照数に入ってしまう。
    sibling = root.with_name(root.name + "-other")
    sibling.mkdir()
    other_path = sibling / path.name
    other_path.write_bytes(path.read_bytes())
    unrelated = QgsVectorLayer(str(other_path), "unrelated", "ogr")
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "memory", "memory")
    project.addMapLayers([original, unrelated, memory])
    project.removeMapLayer(original.id())
    assert not root.exists()
    assert other_path.is_file() and len(list(unrelated.getFeatures())) == 1
    project.clear()


def test_cleanup_failure_is_logged_not_raised(capture_logs):
    logged = capture_logs(temporary_files)

    def fail():
        raise OSError("使用中のため削除できません")

    temporary_files.cleanup(SimpleNamespace(name="/tmp/ksj-layer-test", cleanup=fail))
    ((message, warning),) = logged
    assert "使用中のため削除できません" in message and "ksj-layer-test" in message
    assert warning


def test_release_when_closed_waits_for_the_last_layer(
    qgis_app, qgis_new_project, temp_root
):
    project = QgsProject.instance()
    workspace = temporary_files.workspace()
    path = Path(workspace.name)
    layers = [
        QgsVectorLayer("Point?crs=EPSG:4326", name, "memory") for name in ("a", "b")
    ]
    project.addMapLayers(layers, False)
    temporary_files.release_when_closed(workspace, layers)
    project.removeMapLayer(layers[0].id())
    assert path.is_dir()
    project.removeMapLayer(layers[1].id())
    assert not path.exists()
