"""通常のProcessing画面の選択UI。処理本体・バッチ実行からは独立する。"""

from pathlib import Path

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputMultipleLayers,
    QgsProviderRegistry,
)
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QCompleter, QFormLayout, QLabel, QWidget
from processing.gui.wrappers import WidgetWrapper

from . import catalog, local_storage, zip_scanner
from .processing_algorithms import scan_layers

try:
    # QGIS 4.2 以降は AlgorithmDialog が AlgorithmWidget（QWidget 基底）に改名された。
    from processing.gui.algorithm_widget import AlgorithmWidget as AlgorithmWidgetBase
except ImportError:
    from processing.gui.AlgorithmDialog import AlgorithmDialog as AlgorithmWidgetBase

# パラメータ名ごとの画面の種類、参照するカタログ項目、従属する親パラメータ。
# 画面を開くときにこの表から widget_wrapper メタデータを作る。
CHOICES = {
    "DATASET_ID": {"kind": "dataset"},
    "CATEGORY": {"kind": "index", "field": "category"},
    "EDITION": {"kind": "index", "field": "edition"},
    "YEAR": {"kind": "dimension", "field": "year", "depends": "DATASET_ID"},
    "REGION": {"kind": "dimension", "field": "region", "depends": "DATASET_ID"},
    "FORMAT": {"kind": "dimension", "field": "format", "depends": "DATASET_ID"},
    "RESOURCE_ID": {"kind": "resource", "depends": "DATASET_ID"},
    "SOURCE": {"kind": "source"},
    "PROVIDER": {"kind": "provider", "depends": "SOURCE"},
}
PLACEHOLDERS = {"dataset": "データセット名で検索・選択", "provider": "種類を選択"}
PROVIDER_OPTIONS = [("ベクタ・テーブル", "ogr"), ("ラスタ", "gdal")]


class ChoiceBox(QComboBox):
    """表示名と処理値を分け、名前の一部からも候補を探せる選択欄。"""

    def __init__(self, strict=False):
        super().__init__()
        self.strict = strict
        self.empty = ""
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
        return self.empty if self.strict else self.currentText().strip()

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
        self.empty = empty
        blocked = self.blockSignals(True)
        self.clear()
        self.addItem(placeholder, empty)
        for label, value in options:
            self.addItem(label, value)
        index = self.findData(previous)
        self.setCurrentIndex(index if index >= 0 else 0)
        self.blockSignals(blocked)


def dimension_options(records, dimension):
    """ラベルは group_resources の表示用。処理へは元の値（空なら ""）を渡す。"""
    groups = catalog.group_resources(records, dimension)
    return [(label, items[0].get(dimension) or "") for label, items in groups.items()]


def file_label(resource):
    return " ｜ ".join(
        (
            catalog.dimension_label(resource, "year"),
            catalog.dimension_label(resource, "region"),
            catalog.resource_label(resource),
        )
    )


def load_resources(dataset_id):
    """データセットの配布一覧と、読めないときの説明を返す。"""
    if not dataset_id:
        return [], ""
    try:
        return catalog.load_dataset(dataset_id)["resources"], ""
    except catalog.CatalogError as exc:
        return [], f"配布一覧を読み込めません: {exc}"


class ResourceChooser(QWidget):
    changed = pyqtSignal()
    HINT = "先にデータセットを選択してください。"
    NO_MATCH = "条件に一致する配布ファイルがありません。"

    def __init__(self):
        super().__init__()
        self.entries = []  # (配布, 表示名, 配布ID)
        self.hint = self.HINT
        self.selected = (None, None, None)
        self.year, self.region, self.format, self.files = (
            ChoiceBox(strict=True) for _ in range(4)
        )
        self.dimensions = (
            ("year", self.year),
            ("region", self.region),
            ("format", self.format),
        )
        self.status = QLabel()
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
        for start, (_, combo) in enumerate(self.dimensions, 1):
            combo.currentTextChanged.connect(
                lambda *_, start=start: self.refresh(start)
            )
        self.files.currentTextChanged.connect(self.changed)
        self.files.currentIndexChanged.connect(self.changed)
        self.refresh()

    def set_dataset(self, resources, hint=NO_MATCH):
        self.entries = [
            (item, file_label(item), local_storage.url_key(item["url"]))
            for item in resources
        ]
        self.hint = hint
        self.refresh()

    def refresh(self, start=0):
        """start 番目以降の絞り込み候補と配布一覧を作り直す。"""
        if start and self.dimensions[start - 1][1].value() == self.selected[start - 1]:
            return
        entries = self.entries
        selected = []
        for index, (dimension, combo) in enumerate(self.dimensions):
            if index >= start:
                combo.replace(
                    dimension_options([item for item, _, _ in entries], dimension),
                    empty=None,
                    preserve=start > 0,
                )
            value = combo.value()
            selected.append(value)
            if value is not None:
                entries = [
                    entry
                    for entry in entries
                    if (entry[0].get(dimension) or "") == value
                ]
            combo.setEnabled(bool(self.entries))
        self.selected = tuple(selected)
        self.files.replace(
            [(label, key) for _, label, key in entries],
            placeholder="配布ファイルを選択してください",
        )
        self.files.setEnabled(bool(entries))
        self.status.setText(
            f"候補 {len(entries)} 件。年度・地域・形式を確認して選択してください。"
            if entries
            else self.hint
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
    HINT = "ファイルを選択すると、読み込めるレイヤーが表示されます。"
    NO_LAYERS = "読み込めるレイヤーがありません。ファイルを確認してください。"

    def __init__(self):
        super().__init__()
        self.file = QgsFileWidget()
        self.file.setDialogTitle("保存済みの国土数値情報ファイルを選択")
        extensions = " ".join("*" + ext for ext in sorted(zip_scanner.LAYER_EXTENSIONS))
        self.file.setFilter(f"対応データ ({extensions});;すべてのファイル (*)")
        self.file.setDefaultRoot(local_storage.download_directory())
        self.layers = QComboBox()
        self.status = QLabel(self.HINT)
        self.status.setWordWrap(True)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addRow("ファイル", self.file)
        layout.addRow("レイヤー", self.layers)
        layout.addRow(self.status)
        self.file.fileChanged.connect(self.scan)
        self.layers.currentIndexChanged.connect(self.selection_changed)

    def layer_count(self):
        return f"読み込み可能なレイヤー: {self.layers.count()} 件"

    def selection_changed(self, index):
        if index >= 0:
            self.status.setText(self.layer_count())
        self.changed.emit()

    def scan(self, path):
        message = self.NO_LAYERS if path else self.HINT
        blocked = self.layers.blockSignals(True)
        self.layers.clear()
        if Path(path).is_file():
            try:
                layers, _ = scan_layers(path, QgsProcessingFeedback())
            except (OSError, RuntimeError, ValueError) as exc:
                layers, message = [], f"読み込めません: {exc}"
            for layer in layers:
                kind = "ラスタ" if layer["provider"] == "gdal" else "ベクタ・テーブル"
                self.layers.addItem(f"{layer['name']} ｜ {kind}", layer)
        self.layers.blockSignals(blocked)
        self.status.setText(self.layer_count() if self.layers.count() else message)
        self.changed.emit()

    def value(self):
        return (self.layers.currentData() or {}).get("source", "")

    def set_value(self, source):
        if not source:
            self.file.setFilePath("")
            return
        source = str(source)
        # ogr のサブレイヤーURI（path|layername=…）からファイルパスを取り出す。
        decoded = QgsProviderRegistry.instance().decodeUri("ogr", source)
        path = decoded.get("path") or source
        self.file.setFilePath(path)
        selected = 0 if source == path and self.layers.count() else -1
        for index in range(self.layers.count()):
            if self.layers.itemData(index)["source"] == source:
                selected = index
                break
        self.layers.setCurrentIndex(selected)
        self.status.setText(
            self.layer_count()
            if selected >= 0
            else "指定されたレイヤーが見つかりません。ファイル・レイヤーを選び直してください。"
        )


class CatalogWidgetWrapper(WidgetWrapper):
    """CHOICES の設定に従い、表示名で選んだ候補を処理用の値へ変換する。"""

    def createWidget(self, kind, field=None, depends=None):
        self.kind, self.field, self.depends = kind, field, depends
        self.last_value = None
        self.dataset_id = None
        # kind == "dataset" が読み込み、従属項目へ渡す配布一覧とエラー。
        self.resources, self.error = [], ""
        if kind == "resource":
            widget = ResourceChooser()
        elif kind == "source":
            widget = SourceChooser()
        else:
            widget = ChoiceBox(strict=kind in {"dataset", "provider"})
            options = []
            if kind == "provider":
                options = PROVIDER_OPTIONS
            elif kind in {"dataset", "index"}:
                options = self.index_options(widget)
            widget.replace(options, PLACEHOLDERS.get(kind, "すべて"))
        signals = (
            (widget.currentTextChanged, widget.currentIndexChanged)
            if isinstance(widget, ChoiceBox)
            else (widget.changed,)
        )
        for signal in signals:
            signal.connect(self.value_changed)
        return widget

    def index_options(self, widget):
        try:
            datasets = catalog.load_index()["datasets"]
        except catalog.CatalogError as exc:
            widget.setToolTip(f"カタログを読み込めません: {exc}")
            return []
        if self.kind == "dataset":
            return [
                (
                    f"{item['title']} ｜ {item.get('category', '')} ｜ {item.get('edition', '')}",
                    item["id"],
                )
                for item in datasets
            ]
        return [
            (label, value)
            for label, value in dimension_options(datasets, self.field)
            if value
        ]

    def value_changed(self, *_):
        """値が実際に変わったときだけ通知する（text と index の二重発火を抑える）。"""
        value = self.value()
        if value == self.last_value:
            return
        self.last_value = value
        if self.kind == "dataset":
            self.resources, self.error = load_resources(value)
        self.widgetValueHasChanged.emit(self)

    def value(self):
        return self.widget.value()

    def setValue(self, value):
        if isinstance(self.widget, ChoiceBox):
            self.widget.select(value)
        else:
            self.widget.set_value(value)

    def postInitialize(self, wrappers):
        parent = next(
            (w for w in wrappers if w.parameterDefinition().name() == self.depends),
            None,
        )
        if parent is None:
            return
        slot = self.source_changed if self.kind == "provider" else self.dataset_changed
        parent.widgetValueHasChanged.connect(slot)
        slot(parent)

    def dataset_changed(self, parent):
        value = parent.parameterValue()
        if self.dataset_id == value:
            return
        self.dataset_id = value
        if self.kind == "resource":
            hint = parent.error or (
                ResourceChooser.NO_MATCH if value else ResourceChooser.HINT
            )
            self.widget.set_dataset(parent.resources, hint)
            return
        self.widget.setToolTip(parent.error)
        self.widget.replace(
            [
                (label, option)
                for label, option in dimension_options(parent.resources, self.field)
                if option
            ]
        )
        self.value_changed()

    def source_changed(self, parent):
        layer = parent.widget.layers.currentData()
        if layer:
            self.widget.select(layer["provider"])


class CatalogAlgorithmWidget(AlgorithmWidgetBase):
    def __init__(self, algorithm, parent=None):
        # GUI専用のコピーだけを装飾する。レジストリ・バッチ・モデルの定義を変えない。
        configured = algorithm.create()
        for parameter in configured.parameterDefinitions():
            choice = CHOICES.get(parameter.name())
            if choice:
                parameter.setMetadata(
                    {
                        "widget_wrapper": {
                            "class": f"{__name__}.CatalogWidgetWrapper",
                            **choice,
                        }
                    }
                )
        super().__init__(configured, parent=parent)

    def finish(self, successful, result, context, feedback, in_place=False):
        # 画面からの実行に限り、マップレイヤー出力を標準の結果処理で地図へ追加する。
        if successful and not feedback.isCanceled() and context.project() is not None:
            for output in self.algorithm().outputDefinitions():
                if isinstance(output, QgsProcessingOutputMultipleLayers):
                    layer_ids = result.get(output.name()) or []
                elif isinstance(output, QgsProcessingOutputMapLayer):
                    layer_ids = [result.get(output.name())]
                else:
                    continue
                for layer_id in layer_ids:
                    layer = context.getMapLayer(layer_id) if layer_id else None
                    if layer is not None:
                        context.addLayerToLoadOnCompletion(
                            layer_id,
                            QgsProcessingContext.LayerDetails(
                                layer.name(), context.project(), output.name()
                            ),
                        )
        super().finish(successful, result, context, feedback, in_place)
