"""一時レイヤー用の作業ディレクトリ。生成したレイヤーがすべて閉じられた時点で削除する。"""

import tempfile

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
    """一時ディレクトリを、そこから生成したレイヤーがすべて閉じられるまで保つ。"""
    remaining = len(layers)

    def release():
        nonlocal remaining
        remaining -= 1
        if remaining == 0:
            cleanup(workspace)

    for layer in layers:
        layer.destroyed.connect(release)
