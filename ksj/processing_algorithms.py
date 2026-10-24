"""GUI操作なしで、カタログから通常ファイルと解析用レイヤーへつなぐ。"""

import json
from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputMapLayer,
    QgsProcessingOutputNumber,
    QgsProcessingOutputString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)

from . import catalog, encoding_check, local_storage, zip_scanner

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# ksj:load_layer の ENCODING。先頭は Shapefile の自動判定、以降は明示指定。
AUTO_DETECT = "自動判定"
ENCODING_OPTIONS = [AUTO_DETECT, *encoding_check.ENCODINGS]


def check_canceled(feedback):
    if feedback.isCanceled():
        raise QgsProcessingException("処理を中止しました。")


def dataset_metadata(dataset):
    return {key: value for key, value in dataset.items() if key != "resources"}


def load_dataset(dataset_id):
    try:
        return catalog.load_dataset(dataset_id)
    except catalog.CatalogError as exc:
        raise QgsProcessingException(
            f"データセットを読み込めません: {dataset_id}。"
            "ksj:search_datasets の id を指定してください。"
        ) from exc


def default_layer_name(source, provider):
    """サブレイヤー名を優先し、なければファイル名を表示名にする。"""
    decoded = QgsProviderRegistry.instance().decodeUri(provider, source)
    return decoded.get("layerName") or Path(decoded.get("path") or source).stem


def matches(record, terms, filters):
    """検索語は全項目の部分一致AND、filtersは項目ごとの部分一致。"""
    if terms:
        text = json.dumps(record, ensure_ascii=False).casefold()
        if not all(term in text for term in terms):
            return False
    return all(
        value in str(record.get(key) or "").casefold() for key, value in filters.items()
    )


class KsjAlgorithm(QgsProcessingAlgorithm):
    def group(self):
        return "データ検索・取得"

    def groupId(self):
        return "data"

    def createInstance(self):
        return type(self)()

    def createCustomParametersWidget(self, parent=None):
        from .processing_widgets import CatalogAlgorithmWidget

        return CatalogAlgorithmWidget(self, parent=parent)

    def string(self, parameters, name, context):
        return self.parameterAsString(parameters, name, context).strip()

    def add_string(self, name, description, optional=False, default=None):
        self.addParameter(
            QgsProcessingParameterString(
                name, description, defaultValue=default, optional=optional
            )
        )


class PagedAlgorithm(KsjAlgorithm):
    def select(self, items, parameters, context, feedback, *filter_names):
        """QUERYと各項目（空欄は絞り込みなし）に一致する要素を返す。"""
        terms = self.string(parameters, "QUERY", context).casefold().split()
        filters = {
            name.lower(): self.string(parameters, name, context).casefold()
            for name in filter_names
        }
        filters = {key: value for key, value in filters.items() if value}
        records = []
        for item in items:
            check_canceled(feedback)
            if matches(item, terms, filters):
                records.append(item)
        return records

    def add_paging(self):
        self.addParameter(
            QgsProcessingParameterNumber(
                "LIMIT",
                "1ページの件数",
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=DEFAULT_PAGE_SIZE,
                minValue=1,
                maxValue=MAX_PAGE_SIZE,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                "OFFSET",
                "開始位置（0から）",
                type=QgsProcessingParameterNumber.Type.Integer,
                defaultValue=0,
                minValue=0,
            )
        )
        self.addOutput(QgsProcessingOutputString("RESULTS", "検索結果（JSON）"))
        self.addOutput(QgsProcessingOutputNumber("TOTAL", "絞り込み後の総件数"))

    def page(self, records, parameters, context, **metadata):
        limit = self.parameterAsInt(parameters, "LIMIT", context)
        offset = self.parameterAsInt(parameters, "OFFSET", context)
        total = len(records)
        result = {
            **metadata,
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit if offset + limit < total else None,
            "items": records[offset : offset + limit],
        }
        return {"RESULTS": json.dumps(result, ensure_ascii=False), "TOTAL": total}


class SearchDatasets(PagedAlgorithm):
    def name(self):
        return "search_datasets"

    def displayName(self):
        return "国土数値情報のデータセットを検索"

    def shortHelpString(self):
        return (
            "検索語を入力し、分類・版を選択してカタログを絞り込めます。結果はログのJSONで確認できます。\n\n"
            "国土数値情報をオフライン検索し、データセットIDをJSONで返します。"
            "QUERYは名称・ID・分類などの空白区切りAND検索。CATEGORYとEDITIONは部分一致。"
            "空欄は全件対象。RESULTSはitems、total、next_offsetを含むJSON文字列、"
            "TOTALは絞り込み後の総件数。LIMITとOFFSETで続きが取得できます。"
            "itemsのidをksj:list_resourcesのDATASET_IDへ渡してください。"
            "同梱カタログの情報であり、公開元の最新状態を保証しません。"
        )

    def initAlgorithm(self, config=None):
        for name, label in (
            ("QUERY", "検索語"),
            ("CATEGORY", "分類"),
            ("EDITION", "版（例: 現行形式）"),
        ):
            self.add_string(name, label, optional=True)
        self.add_paging()

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        try:
            index = catalog.load_index()
        except catalog.CatalogError as exc:
            raise QgsProcessingException(f"カタログを読み込めません: {exc}") from exc
        records = self.select(
            index["datasets"], parameters, context, feedback, "CATEGORY", "EDITION"
        )
        return self.page(
            records, parameters, context, generated_at=index.get("generated_at")
        )


class ListResources(PagedAlgorithm):
    def name(self):
        return "list_resources"

    def displayName(self):
        return "国土数値情報の配布ファイルを検索"

    def shortHelpString(self):
        return (
            "データセットを名前から選び、年度・地域・形式で絞り込めます。結果はログのJSONで確認できます。\n\n"
            "データセット内の年度・地域・形式を検索し、配布IDをJSONで返します。"
            "DATASET_IDにはksj:search_datasetsのidを指定。YEAR（例: 2024）、"
            "REGION（例: 東京都、5339）、FORMATは部分一致、QUERYは全項目の"
            "空白区切りAND検索です。形式が空欄の配布はQUERYでファイル名も検索できます。"
            "空欄は絞り込みなし。RESULTSはdataset（公式説明・利用条件）、items、"
            "total、next_offsetを含むJSON文字列。LIMIT/OFFSETでページング。"
            "年度・地域・形式・測地系を確認し、resource_idをksj:download_resourceへ渡します。"
        )

    def initAlgorithm(self, config=None):
        self.add_string("DATASET_ID", "データセット")
        for name, label in (
            ("YEAR", "年度"),
            ("REGION", "地域・メッシュ"),
            ("FORMAT", "形式"),
            ("QUERY", "検索語"),
        ):
            self.add_string(name, label, optional=True)
        self.add_paging()

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        dataset = load_dataset(self.string(parameters, "DATASET_ID", context))
        records = [
            {**resource, "resource_id": local_storage.url_key(resource["url"])}
            for resource in self.select(
                dataset["resources"],
                parameters,
                context,
                feedback,
                "YEAR",
                "REGION",
                "FORMAT",
            )
        ]
        return self.page(
            records, parameters, context, dataset=dataset_metadata(dataset)
        )


def scan_layers(local_path, feedback):
    """実ファイルのサブレイヤーURIを返す。レイヤー所有権はまだ作らない。"""
    root = Path(local_path)
    paths = (
        [root / entry for entry in zip_scanner.supported_entries(local_path)]
        if root.is_dir()
        else [root]
    )
    registry = QgsProviderRegistry.instance()
    layers, unreadable = [], []
    for path in paths:
        check_canceled(feedback)
        provider = registry.providerMetadata(zip_scanner.provider_key(path))
        details = (
            provider.querySublayers(str(path), feedback=feedback) if provider else []
        )
        check_canceled(feedback)
        if not details:
            unreadable.append(str(path))
            feedback.pushWarning(f"直接読み込めないファイル: {path.name}")
        for detail in details:
            layers.append(
                {
                    "name": detail.name(),
                    "source": detail.uri(),
                    "provider": detail.providerKey(),
                    "file": str(path),
                }
            )
    return layers, unreadable


class DownloadResource(KsjAlgorithm):
    def name(self):
        return "download_resource"

    def displayName(self):
        return "国土数値情報を取得・展開してレイヤー一覧を返す"

    def shortHelpString(self):
        return (
            "データセットを名前から選び、年度・地域・形式で絞り込んで配布ファイルを選択してください。"
            "保存先フォルダを指定して実行すると取得・展開します。"
            "地図に表示するには「取得済み国土数値情報を解析用レイヤーとして読み込む」で保存ファイルを開いてください。\n\n"
            "配布IDで1ファイルを取得・展開し、読み込めるレイヤーの一覧をJSONで返します。"
            "DATASET_IDとRESOURCE_IDにはksj:list_resourcesの結果を指定。"
            "DIRECTORYは既存の保存フォルダ。省略時はブラウザの保存先設定を使い、"
            "未設定ならエラーになります。設定変更やダイアログ表示は行いません。"
            "同じ配布は再取得せず再利用します。長い取得はバックグラウンド実行を推奨。"
            "LOCAL_PATHは保存先、RESULTSはdataset、resource、layers、unreadable_filesを"
            "含むJSON文字列。layersのsource/provider/nameを選び、ksj:load_layerの"
            "SOURCE/PROVIDER/NAMEへ渡します。SHPとGMLの同一内容を重複追加しないでください。"
            "読み込み可能なレイヤーがなくても取得結果を返すため、layersを確認してください。"
        )

    def initAlgorithm(self, config=None):
        self.add_string("DATASET_ID", "データセット")
        self.add_string("RESOURCE_ID", "配布ファイルの選択")
        self.addParameter(
            QgsProcessingParameterFile(
                "DIRECTORY",
                "保存先フォルダ（省略時は既存設定）",
                behavior=QgsProcessingParameterFile.Behavior.Folder,
                optional=True,
            )
        )
        self.addOutput(
            QgsProcessingOutputString("RESULTS", "取得元とレイヤー一覧（JSON）")
        )
        self.addOutput(QgsProcessingOutputString("LOCAL_PATH", "保存済みデータのパス"))

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        dataset = load_dataset(self.string(parameters, "DATASET_ID", context))
        resource_id = self.string(parameters, "RESOURCE_ID", context)
        resource = next(
            (
                item
                for item in dataset["resources"]
                if local_storage.url_key(item["url"]) == resource_id
            ),
            None,
        )
        if resource is None:
            raise QgsProcessingException(
                "配布IDが見つかりません。ksj:list_resourcesで確認してください。"
            )
        if (
            zip_scanner.download_suffix(resource["url"])
            not in zip_scanner.SUPPORTED_EXTENSIONS
        ):
            raise QgsProcessingException(
                "この配布形式は直接読み込めません。公式説明ページから原本を取得してください: "
                f"{resource['url']}"
            )
        directory = (
            self.parameterAsFile(parameters, "DIRECTORY", context).strip()
            or local_storage.download_directory()
        )
        if not directory:
            raise QgsProcessingException(
                "DIRECTORYに既存の保存先フォルダを指定してください。"
            )
        feedback.pushInfo(f"取得: {resource['filename']}")
        try:
            local_path = local_storage.ensure_local_data(
                resource["url"],
                directory,
                is_canceled=feedback.isCanceled,
                progress=feedback.setProgress,
            )
            layers, unreadable = scan_layers(local_path, feedback)
        except (local_storage.DownloadError, zip_scanner.ZipScanError, OSError) as exc:
            raise QgsProcessingException(str(exc)) from exc
        check_canceled(feedback)
        if not layers:
            feedback.pushWarning(
                "読み込めるレイヤーがありません。保存データと公式説明を確認してください。"
            )
        result = {
            "dataset": dataset_metadata(dataset),
            "resource": {**resource, "resource_id": resource_id},
            "local_path": local_path,
            "layers": layers,
            "unreadable_files": unreadable,
        }
        feedback.setProgress(100)
        return {
            "RESULTS": json.dumps(result, ensure_ascii=False),
            "LOCAL_PATH": local_path,
        }


class LoadLayer(KsjAlgorithm):
    def name(self):
        return "load_layer"

    def displayName(self):
        return "取得済み国土数値情報を解析用レイヤーとして読み込む"

    def shortHelpString(self):
        return (
            "保存済みのファイルを開き、レイヤーを選択してください。データの種類は自動設定されます。"
            "この画面から実行すると、読み込んだレイヤーを地図に追加します。\n\n"
            "取得済み一覧から選んだ1レイヤーを読み込み、地図表示・解析用OUTPUTを返します。"
            "ksj:download_resourceのRESULTS.layersのsourceをSOURCE、providerをPROVIDER"
            "（ogrまたはgdal）、nameを任意のNAMEへ渡します。OUTPUTは単一のマップレイヤー。"
            "processing.runの結果を後続解析に渡すか、QgsProjectへ追加できます。"
            "アルゴリズム自体はプロジェクトを変更しません。CRS・属性は元データのまま。"
            "通常ファイルを参照するため、プロジェクト保存後も保存データを移動・削除しないでください。"
            "ENCODINGはShapefileの文字コード。既定の自動判定は.dbfの属性値と.cpgなどから決め、"
            "判定できない場合はQGISの既定に従います。GeoJSON・GMLなどはUTF-8固定で指定は無視されます。"
        )

    def initAlgorithm(self, config=None):
        self.add_string("SOURCE", "読み込むデータ")
        self.add_string(
            "PROVIDER", "データの種類（ファイル選択で自動設定）", default="ogr"
        )
        self.add_string("NAME", "レイヤー名", optional=True)
        self.addParameter(
            QgsProcessingParameterEnum(
                "ENCODING",
                "文字コード（Shapefile）",
                options=ENCODING_OPTIONS,
                defaultValue=0,
            )
        )
        self.addOutput(QgsProcessingOutputMapLayer("OUTPUT", "解析用レイヤー"))

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        source = self.string(parameters, "SOURCE", context)
        provider = self.string(parameters, "PROVIDER", context)
        if provider not in {"ogr", "gdal"}:
            raise QgsProcessingException(
                "PROVIDERにはogrまたはgdalを指定してください。"
            )
        name = self.string(parameters, "NAME", context) or default_layer_name(
            source, provider
        )
        layer_class = QgsRasterLayer if provider == "gdal" else QgsVectorLayer
        options = layer_class.LayerOptions()
        options.transformContext = context.transformContext()
        layer = layer_class(source, name, provider, options)
        if not layer.isValid():
            raise QgsProcessingException(f"レイヤーを読み込めません: {source}")
        check_canceled(feedback)
        choice = self.parameterAsEnum(parameters, "ENCODING", context)
        encoding = ENCODING_OPTIONS[choice]
        if encoding == AUTO_DETECT:
            encoding_check.apply_detected_encoding(layer)
        elif provider == "ogr":
            layer.setProviderEncoding(encoding_check.provider_encoding(encoding))
        context.temporaryLayerStore().addMapLayer(layer)
        return {"OUTPUT": layer.id()}
