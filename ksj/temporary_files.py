"""一時レイヤー用の作業ディレクトリ。複製を含む参照レイヤーが閉じられた時点で削除する。"""

import tempfile
from pathlib import Path

from qgis.core import QgsProject, QgsProviderRegistry

from .messages import log_message

PREFIX = "ksj-layer-"


def workspace():
    """取得・展開先の一時ディレクトリ。削除は cleanup() か release_when_closed() で行う。"""
    return tempfile.TemporaryDirectory(prefix=PREFIX)


def cleanup(workspace):
    """一時ディレクトリを削除する。失敗は警告ログに残すだけで、OSの一時領域掃除に任せる。"""
    try:
        workspace.cleanup()
    except OSError as exc:
        log_message(
            f"一時ファイルを削除できません: {workspace.name} ({exc})", warning=True
        )


def release_when_closed(workspace, layers):
    """生成したレイヤーと、同じ一時ディレクトリを参照する複製の寿命を追跡する。"""
    project = QgsProject.instance()
    root = Path(workspace.name).resolve()
    remaining = set()

    def release(layer_id):
        remaining.remove(layer_id)
        if not remaining:
            project.layersAdded.disconnect(track_added)
            cleanup(workspace)

    def track(layer):
        layer_id = layer.id()
        # 初回追加や takeMapLayer() 後の再追加で二重に数えない。
        if layer_id not in remaining:
            remaining.add(layer_id)
            # レイヤー本体を保持せず、destroyed でプロバイダー解放後に削除する。
            layer.destroyed.connect(lambda: release(layer_id))

    def track_added(added):
        registry = QgsProviderRegistry.instance()
        for layer in added:
            source = registry.decodeUri(layer.providerType(), layer.source()).get(
                "path"
            )
            if source and root in Path(source).resolve().parents:
                track(layer)

    for layer in layers:
        track(layer)
    project.layersAdded.connect(track_added)
    track_added(project.mapLayers().values())
