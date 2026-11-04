"""初回案内の永続化、回答、ダウンロード経路を実QGISで確認する。"""

import importlib

import pytest
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtWidgets import QMessageBox

from ksj import catalog_browser, layer_loading, local_storage, mesh_index, zip_scanner
from tests.helpers import point_geojson, pump_until, run_workers, wait_for_layer_loading


@pytest.fixture
def invitation(survey_settings, monkeypatch):
    from ksj import survey

    QgsSettings().remove(survey_settings)
    dialogs, opened = [], []

    def answer(dialog):
        dialogs.append(dialog.text())
        assert dialog.button(QMessageBox.StandardButton.Yes).text() == "はい"
        assert dialog.button(QMessageBox.StandardButton.No).text() == "いいえ"
        # モーダル表示中に別の取得が始まっても重複表示しない。
        survey.prompt_once()
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", answer)
    monkeypatch.setattr(
        survey.QDesktopServices,
        "openUrl",
        lambda url: opened.append(url.toString()) or True,
    )
    return survey, dialogs, opened


def test_decline_is_remembered_across_module_reload(invitation, monkeypatch):
    survey, dialogs, opened = invitation
    key = survey.PROMPTED_KEY
    survey.prompt_once()
    importlib.reload(survey)
    monkeypatch.setattr(survey, "PROMPTED_KEY", key)
    survey.prompt_once()
    assert dialogs == ["ユーザーアンケートに回答しますか？"]
    assert not opened
    assert survey.prompted()


@pytest.mark.parametrize(
    "answer", [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No, 0]
)
def test_only_yes_opens_form_and_all_answers_are_remembered(
    invitation, monkeypatch, answer
):
    survey, dialogs, opened = invitation
    monkeypatch.setattr(
        QMessageBox, "exec", lambda dialog: dialogs.append(dialog.text()) or answer
    )
    survey.prompt_once()
    survey.prompt_once()
    assert len(dialogs) == 1
    assert opened == (
        [survey.SURVEY_URL] if answer == QMessageBox.StandardButton.Yes else []
    )


@pytest.mark.parametrize("member", ["", "point.geojson"])
@pytest.mark.parametrize("mode", ["save", "temporary"])
def test_layer_download_prompts_once(
    qgis_app, qgis_new_project, storage_settings, http_data, invitation, member, mode
):
    _, dialogs, _ = invitation
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    QgsSettings().setValue(local_storage.MODE_KEY, mode)
    http_data["range_support"] = True
    if not member:
        http_data.update(
            url=http_data["url"].replace("data.zip", "point.geojson"),
            body=point_geojson().encode(),
        )
    for _ in range(2):
        layer_loading.start(http_data["url"], member, "test")
        wait_for_layer_loading(qgis_app)
    assert len(dialogs) == 1
    assert http_data["requests"]
    assert len(QgsProject.instance().mapLayers()) == 2


@pytest.mark.parametrize("member", ["", "point.geojson"])
def test_saved_data_does_not_consume_invitation(
    qgis_app, storage_settings, http_data, invitation, member
):
    survey, dialogs, _ = invitation
    storage_settings.mkdir()
    run_workers(
        qgis_app,
        [
            lambda: local_storage.ensure_local_data(
                http_data["url"], str(storage_settings)
            )
        ],
    )
    survey.prompt_for_download(http_data["url"], str(storage_settings), member)
    assert not dialogs
    assert not survey.prompted()


def test_external_download_prompts_but_description_does_not(qgis_app, invitation):
    _, dialogs, opened = invitation
    item = catalog_browser.KsjResourceItem(
        None,
        "test",
        {
            "filename": "data.zip",
            "url": "https://example.org/data.zip",
            "source_url": "https://example.org/info",
        },
    )
    actions = item.actions(None)
    next(
        action
        for action in actions
        if action.text() == "この版の公式説明・利用条件を開く"
    ).trigger()
    assert not dialogs
    next(
        action for action in actions if action.text() == "配布ファイルをダウンロード"
    ).trigger()
    assert len(dialogs) == 1
    assert opened[-1] == "https://example.org/data.zip"


def test_unsupported_download_child_prompts(qgis_app, invitation):
    _, dialogs, opened = invitation
    item = catalog_browser.KsjResourceItem(
        None, "test", {"filename": "data.lzh", "url": "https://example.org/data.lzh"}
    )
    child = item.createChildren()[0]
    assert not dialogs
    assert child.handleDoubleClick()
    assert len(dialogs) == 1
    assert opened == ["https://example.org/data.lzh"]


def test_nested_zip_download_prompts(qgis_app, invitation):
    _, dialogs, opened = invitation
    parent = catalog_browser.KsjResourceItem(
        None, "test", {"filename": "data.zip", "url": "https://example.org/data.zip"}
    )
    folder = catalog_browser.remote_children(
        parent, zip_scanner.build_tree(["nested.zip"]), "https://example.org/data.zip"
    )[0]
    folder.createChildren()
    assert not dialogs
    actions = folder.actions(None)
    actions[0].trigger()
    assert len(dialogs) == 1
    assert opened == ["https://example.org/data.zip"]


def test_mesh_download_shares_invitation_with_browser(
    qgis_app, qgis_new_project, storage_settings, http_data, invitation
):
    _, dialogs, _ = invitation
    storage_settings.mkdir()
    QgsSettings().setValue(local_storage.DIRECTORY_KEY, str(storage_settings))
    index = mesh_index.add_mesh_index(
        "試験", [{"filename": "data.zip", "url": http_data["url"], "region": "5339"}]
    )
    mesh_index.load_mesh(index.id(), next(index.getFeatures()).id())
    pump_until(qgis_app, lambda: not mesh_index._pending, timeout=15)
    assert len(dialogs) == 1
    assert len(QgsProject.instance().mapLayers()) == 2
    layer_loading.start(http_data["url"], "point.geojson", "test")
    wait_for_layer_loading(qgis_app)
    assert len(dialogs) == 1
    assert len(QgsProject.instance().mapLayers()) == 3


def test_invalid_member_does_not_consume_invitation(invitation, storage_settings):
    survey, dialogs, _ = invitation
    survey.prompt_for_download(
        "https://example.org/data.zip", str(storage_settings), "../data.shp"
    )
    assert not dialogs
    assert not survey.prompted()


def test_canceled_settings_does_not_consume_invitation(
    invitation, storage_settings, monkeypatch
):
    survey, dialogs, _ = invitation
    monkeypatch.setattr(local_storage, "configure_loading", lambda: False)
    layer_loading.start("https://example.org/data.zip", "point.geojson", "test")
    assert not dialogs
    assert not layer_loading.pending
    assert not survey.prompted()


def test_processing_download_remains_noninteractive(
    qgis_app,
    processing_provider,
    sample_catalog,
    http_data,
    invitation,
    monkeypatch,
    storage_settings,
):
    from ksj import catalog
    from tests.test_processing import run

    survey, dialogs, _ = invitation
    dataset = catalog.load_dataset("dams")
    dataset["resources"][0]["url"] = http_data["url"]
    monkeypatch.setattr(catalog, "load_dataset", lambda dataset_id: dataset)
    storage_settings.mkdir()
    result = run(
        "download_resource",
        {
            "DATASET_ID": "dams",
            "RESOURCE_ID": local_storage.url_key(http_data["url"]),
            "DIRECTORY": str(storage_settings),
        },
    )
    assert result["LOCAL_PATH"]
    assert not dialogs
    assert not survey.prompted()
