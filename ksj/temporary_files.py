"""一時レイヤー用の作業ディレクトリ。中のファイルを参照するレイヤーが閉じられた時点で削除する。"""

import tempfile
from pathlib import Path

from qgis.core import QgsProject

from .encoding_check import source_path
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


def release_when_closed(workspace):
    """一時ディレクトリを、中のファイルを参照するレイヤー（複製を含む）が
    プロジェクトからすべて消えるまで保つ。参照するレイヤーがなければ直ちに削除する。"""
    # macOS では /var が /private/var へのシンボリックリンクなので、両辺を解決して比べる。
    root = Path(workspace.name).resolve()
    remaining = set()

    def release(layer_id):
        remaining.remove(layer_id)
        if not remaining:
            QgsProject.instance().layersAdded.disconnect(track)
            cleanup(workspace)

    def watch(layer):
        layer_id = layer.id()
        remaining.add(layer_id)
        # レイヤー本体を保持せず、destroyed でプロバイダー解放後に削除する。
        layer.destroyed.connect(lambda: release(layer_id))

    def track(layers):
        for layer in layers:
            # takeMapLayer() 後の再追加を二重に数えない。
            if layer.id() in remaining:
                continue
            if root in source_path(layer).resolve().parents:
                watch(layer)

    # QgsProject のラッパーをクロージャに抱えない。不要になった後にワーカースレッドの
    # GC で解放されると、同じ QgsProject に繋いだ他の Python スロットまで外れる。
    project = QgsProject.instance()
    track(project.mapLayers().values())
    if remaining:
        project.layersAdded.connect(track)
    else:
        cleanup(workspace)
