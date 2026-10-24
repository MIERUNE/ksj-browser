"""メッセージログとメッセージバーへの通知。"""

from types import SimpleNamespace

from qgis import utils
from qgis.core import Qgis

from ksj import messages
from tests.helpers import message_log_signal


def test_log_message_records_with_ksj_tag_and_returns_level(qgis_app):
    received = []

    def record(message, tag, level, *_):
        received.append((message, tag, level))

    signal = message_log_signal(qgis_app)
    signal.connect(record)
    try:
        assert messages.log_message("情報") == Qgis.MessageLevel.Info
        assert messages.log_message("注意", warning=True) == Qgis.MessageLevel.Warning
    finally:
        signal.disconnect(record)
    assert received == [
        ("情報", "KSJ", Qgis.MessageLevel.Info),
        ("注意", "KSJ", Qgis.MessageLevel.Warning),
    ]


def test_notify_uses_message_bar_only_when_gui_exists(monkeypatch):
    pushed = []
    bar = SimpleNamespace(
        pushMessage=lambda tag, message, level, duration: pushed.append(
            (tag, message, level, duration)
        )
    )
    monkeypatch.setattr(
        utils,
        "iface",
        SimpleNamespace(messageBar=lambda: bar, mainWindow=lambda: "window"),
    )
    messages.notify("追加しました")
    assert pushed == [("KSJ", "追加しました", Qgis.MessageLevel.Info, 8)]
    assert messages.main_window() == "window"

    monkeypatch.setattr(utils, "iface", None)
    messages.notify("GUIなしでも例外にならない", warning=True)
    assert len(pushed) == 1
    assert messages.main_window() is None
