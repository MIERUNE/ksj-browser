"""一時レイヤー用ディレクトリの作成と、レイヤーが閉じられた後の削除。"""

from pathlib import Path
from types import SimpleNamespace

from qgis.core import QgsProject, QgsVectorLayer

from ksj import temporary_files


def test_workspace_has_plugin_prefix_and_cleanup_removes_it(temp_root):
    workspace = temporary_files.workspace()
    path = Path(workspace.name)
    assert path.is_dir() and path.parent == temp_root
    assert path.name.startswith(temporary_files.PREFIX)
    temporary_files.cleanup(workspace)
    assert not path.exists()


def test_cleanup_failure_is_logged_not_raised(monkeypatch):
    logged = []
    monkeypatch.setattr(
        temporary_files,
        "log_message",
        lambda message, warning=False: logged.append((message, warning)),
    )

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
