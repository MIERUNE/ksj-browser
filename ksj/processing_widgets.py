"""通常のProcessing画面の選択UI。処理本体・バッチ実行からは独立する。"""

from pathlib import Path

from qgis.core import QgsProcessingContext, QgsProcessingFeedback
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QCompleter, QFormLayout, QLabel, QWidget
from processing.gui.AlgorithmDialog import AlgorithmDialog
from processing.gui.wrappers import WidgetWrapper

from . import catalog, local_storage, zip_scanner
from .processing_algorithms import scan_layers


class ChoiceBox(QComboBox):
    """表示名と処理値を分け、名前の一部からも候補を探せる選択欄。"""

    def __init__(self, strict=False):
        super().__init__()
        self.strict = strict
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMinimumContentsLength(24)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setMaxVisibleItems(16)

    def value(self):
        index = self.currentIndex()
        if index < 0 or self.itemText(index) != self.currentText():
            index = self.findText(self.currentText())
        if index >= 0:
            return self.itemData(index)
        return "" if self.strict else self.currentText().strip()

    def select(self, value):
        index = self.findData(value)
        if index >= 0:
            self.setCurrentIndex(index)
        elif self.strict:
            self.setCurrentIndex(0)
        else:
            self.setEditText(str(value or ""))

    def replace(self, options, placeholder="すべて", empty="", preserve=False):
        previous = self.value() if preserve else empty
        blocked = self.blockSignals(True)
        self.clear()
        self.addItem(placeholder, empty)
        for label, value in options:
            self.addItem(label, value)
        self.select(previous if self.findData(previous) >= 0 else empty)
        self.blockSignals(blocked)


def dimension_options(resources, dimension):
    groups = catalog.group_resources(resources, dimension)
    # group_resourcesのラベルは空値の表示用。処理へは元の値を渡す。
    return [(label, items[0].get(dimension) or "") for label, items in groups.items()]


class ResourceChooser(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.resources = []
        self.year, self.region, self.format = (ChoiceBox(strict=True) for _ in range(3))
        self.files = ChoiceBox(strict=True)
        self.status = QLabel("先にデータセットを選択してください。")
        self.status.setWordWrap(True)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, combo in (
            ("年度", self.year),
            ("地域・メッシュ", self.region),
            ("形式", self.format),
            ("配布ファイル", self.files),
        ):
            layout.addRow(label, combo)
        layout.addRow(self.status)
        self.year.currentTextChanged.connect(lambda: self.refresh(1))
        self.region.currentTextChanged.connect(lambda: self.refresh(2))
        self.format.currentTextChanged.connect(lambda: self.refresh(3))
        self.files.currentTextChanged.connect(self.changed)
        self.files.currentIndexChanged.connect(self.changed)
        self.refresh()

    def set_dataset(self, dataset_id):
        self.resources = []
        error = ""
        if dataset_id:
            try:
                self.resources = catalog.load_dataset(dataset_id)["resources"]
            except (OSError, ValueError, KeyError) as exc:
                error = f"配布一覧を読み込めません: {exc}"
        self.refresh()
        if error:
            self.status.setText(error)
        elif not dataset_id:
            self.status.setText("先にデータセットを選択してください。")

    def refresh(self, start=0):
        records = self.resources
        for index, (dimension, combo) in enumerate(
            (("year", self.year), ("region", self.region), ("format", self.format))
        ):
            if index >= start:
                combo.replace(
                    dimension_options(records, dimension),
                    empty=None,
                    preserve=start > 0,
                )
            value = combo.value()
            if value is not None:
                records = [
                    item for item in records if (item.get(dimension) or "") == value
                ]
            combo.setEnabled(bool(self.resources))
        options = []
        for item in records:
            label = " ｜ ".join(
                (
                    item.get("year") or "年度記載なし",
                    item.get("region") or "地域の指定なし",
                    catalog.resource_label(item),
                )
            )
            options.append((label, local_storage.url_key(item["url"])))
        self.files.replace(options, placeholder="配布ファイルを選択してください")
        self.files.setEnabled(bool(options))
        self.status.setText(
            f"候補 {len(records)} 件。年度・地域・形式を確認して選択してください。"
            if records
            else "条件に一致する配布ファイルがありません。"
        )
        self.changed.emit()

    def value(self):
        return self.files.value() or ""

    def set_value(self, value):
        # 履歴の復元時はフィルタで隠れた配布も選べるようにする。
        if self.files.findData(value) < 0:
            self.refresh()
        self.files.select(value)


class SourceChooser(QWidget):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.file = QgsFileWidget()
        self.file.setDialogTitle("保存済みの国土数値情報ファイルを選択")
        extensions = " ".join("*" + ext for ext in sorted(zip_scanner.LAYER_EXTENSIONS))
        self.file.setFilter(f"対応データ ({extensions});;すべてのファイル (*)")
        self.file.setDefaultRoot(local_storage.download_directory())
        self.layers = QComboBox()
        self.status = QLabel("ファイルを選択すると、読み込めるレイヤーが表示されます。")
        self.status.setWordWrap(True)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("ファイル", self.file)
        layout.addRow("レイヤー", self.layers)
        layout.addRow(self.status)
        self.file.fileChanged.connect(self.scan)
        self.layers.currentIndexChanged.connect(self.selection_changed)

    def selection_changed(self, index):
        if index >= 0:
            self.status.setText(f"読み込み可能なレイヤー: {self.layers.count()} 件")
        self.changed.emit()

    def scan(self, path):
        self.layers.clear()
        if Path(path).is_file():
            try:
                layers, _ = scan_layers(path, QgsProcessingFeedback())
            except (OSError, RuntimeError, ValueError) as exc:
                self.status.setText(f"読み込めません: {exc}")
                self.changed.emit()
                return
            for layer in layers:
                kind = "ラスタ" if layer["provider"] == "gdal" else "ベクタ・テーブル"
                self.layers.addItem(f"{layer['name']} ｜ {kind}", layer)
        self.status.setText(
            f"読み込み可能なレイヤー: {self.layers.count()} 件"
            if self.layers.count()
            else "読み込めるレイヤーがありません。ファイルを確認してください。"
        )
        self.changed.emit()

    def value(self):
        return (self.layers.currentData() or {}).get("source", "")

    def set_value(self, source):
        if not source:
            self.file.setFilePath("")
            return
        path = str(source).split("|", 1)[0]
        self.file.setFilePath(path)
        selected = 0 if source == path and self.layers.count() else -1
        for index in range(self.layers.count()):
            if self.layers.itemData(index)["source"] == source:
                selected = index
                break
        self.layers.setCurrentIndex(selected)
        self.status.setText(
            f"読み込み可能なレイヤー: {self.layers.count()} 件"
            if selected >= 0
            else "指定されたレイヤーが見つかりません。ファイル・レイヤーを選び直してください。"
        )


class CatalogWidgetWrapper(WidgetWrapper):
    def createWidget(self):
        name = self.parameterDefinition().name()
        if name == "RESOURCE_ID":
            widget = ResourceChooser()
        elif name == "SOURCE":
            widget = SourceChooser()
        else:
            widget = ChoiceBox(strict=name in {"DATASET_ID", "PROVIDER"})
            options = []
            if name == "PROVIDER":
                options = [("ベクタ・テーブル", "ogr"), ("ラスタ", "gdal")]
            elif name in {"DATASET_ID", "CATEGORY", "EDITION"}:
                try:
                    datasets = catalog.load_index()["datasets"]
                    if name == "DATASET_ID":
                        options = [
                            (
                                f"{item['title']} ｜ {item.get('category', '')} ｜ {item.get('edition', '')}",
                                item["id"],
                            )
                            for item in datasets
                        ]
                    else:
                        options = [
                            (value, value)
                            for value in dict.fromkeys(
                                item.get(name.lower(), "") for item in datasets
                            )
                            if value
                        ]
                except (OSError, ValueError, KeyError) as exc:
                    widget.setToolTip(f"カタログを読み込めません: {exc}")
            placeholder = {
                "DATASET_ID": "データセット名で検索・選択",
                "PROVIDER": "種類を選択",
            }.get(name, "すべて")
            widget.replace(options, placeholder)
        if isinstance(widget, ChoiceBox):
            widget.currentTextChanged.connect(
                lambda: self.widgetValueHasChanged.emit(self)
            )
            widget.currentIndexChanged.connect(
                lambda: self.widgetValueHasChanged.emit(self)
            )
        else:
            widget.changed.connect(lambda: self.widgetValueHasChanged.emit(self))
        # PythonのカスタムウィジェットはWidgetWrapperで所有する。
        self.control = widget
        return widget

    def value(self):
        return self.control.value()

    def setValue(self, value):
        widget = self.control
        if isinstance(widget, ChoiceBox):
            widget.select(value)
        else:
            widget.set_value(value)

    def postInitialize(self, wrappers):
        name = self.parameterDefinition().name()
        by_name = {
            wrapper.parameterDefinition().name(): wrapper for wrapper in wrappers
        }
        if name in {"YEAR", "REGION", "FORMAT", "RESOURCE_ID"}:
            parent = by_name.get("DATASET_ID")
            if parent:
                parent.widgetValueHasChanged.connect(self.dataset_changed)
                self.dataset_changed(parent)
        elif name == "PROVIDER" and "SOURCE" in by_name:
            by_name["SOURCE"].widgetValueHasChanged.connect(self.source_changed)
            self.source_changed(by_name["SOURCE"])

    def dataset_changed(self, parent):
        name = self.parameterDefinition().name()
        value = parent.parameterValue()
        if getattr(self, "dataset_id", None) == value:
            return
        self.dataset_id = value
        widget = self.control
        if name == "RESOURCE_ID":
            widget.set_dataset(value)
            return
        resources = []
        widget.setToolTip("")
        if value:
            try:
                resources = catalog.load_dataset(value)["resources"]
            except (OSError, ValueError, KeyError) as exc:
                widget.setToolTip(f"候補を読み込めません: {exc}")
        widget.replace(
            [
                (label, value)
                for label, value in dimension_options(resources, name.lower())
                if value
            ]
        )
        self.widgetValueHasChanged.emit(self)

    def source_changed(self, parent):
        layer = parent.control.layers.currentData()
        if layer:
            self.control.select(layer["provider"])


CHOICE_PARAMETERS = {
    "DATASET_ID",
    "RESOURCE_ID",
    "YEAR",
    "REGION",
    "FORMAT",
    "CATEGORY",
    "EDITION",
    "SOURCE",
    "PROVIDER",
}


class CatalogAlgorithmDialog(AlgorithmDialog):
    def __init__(self, algorithm, parent=None):
        # GUI専用のコピーだけを装飾する。レジストリ・バッチ・モデルの定義を変えない。
        configured = algorithm.create()
        for parameter in configured.parameterDefinitions():
            if parameter.name() in CHOICE_PARAMETERS:
                parameter.setMetadata(
                    {"widget_wrapper": {"class": f"{__name__}.CatalogWidgetWrapper"}}
                )
        super().__init__(configured, parent=parent)

    def finish(self, successful, result, context, feedback, in_place=False):
        if (
            successful
            and not feedback.isCanceled()
            and self.algorithm().name() == "load_layer"
        ):
            layer_id = result.get("OUTPUT")
            layer = context.getMapLayer(layer_id) if layer_id else None
            if layer is not None and context.project() is not None:
                context.addLayerToLoadOnCompletion(
                    layer_id,
                    QgsProcessingContext.LayerDetails(
                        layer.name(), context.project(), "OUTPUT"
                    ),
                )
        super().finish(successful, result, context, feedback, in_place)
