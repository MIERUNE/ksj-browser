"""配布の目次・選択ファイルを、対話なしで取得する Processing API。"""

import json
from pathlib import Path, PurePosixPath

from qgis.core import (
    QgsProcessingException,
    QgsProcessingOutputMultipleLayers,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
    QgsProcessingUtils,
)

from . import local_storage, remote_zip, zip_scanner
from .processing_algorithms import (
    ENCODING_OPTIONS,
    KsjAlgorithm,
    PagedAlgorithm,
    add_encoding_parameter,
    check_canceled,
    create_layer,
    dataset_metadata,
    load_dataset,
    scan_layers,
)

FETCH_ERRORS = (local_storage.DownloadError, zip_scanner.ZipScanError, OSError)
FORMAT_SELECTION_HELP = "同じ内容なら Shapefile を優先してください。"
SHAPEFILE_RECOMMENDATION = (
    "必須の付属ファイルが揃っています。同じ内容なら QGIS での描画用に Shapefile を推奨します。"
    "内容の同一性は未確認です。"
)
RESOURCE_INPUT_HELP = "DATASET_ID / RESOURCE_ID は ksj:list_resources、MEMBER は ksj:list_resource_files の member を指定。"
FULL_DOWNLOAD_HELP = (
    "ksj:download_resource で MEMBER を空欄にして全体取得してください。"
)
ENCODING_HELP = (
    "ENCODING は "
    + "、".join(f"{index}: {name}" for index, name in enumerate(ENCODING_OPTIONS))
    + "（Shapefile のみ）。"
)


def add_resource_parameters(algorithm):
    algorithm.add_string("DATASET_ID", "データセット")
    algorithm.add_string("RESOURCE_ID", "配布ファイルの選択")
    algorithm.addParameter(
        QgsProcessingParameterFile(
            "DIRECTORY",
            "保存先フォルダ（省略時は既存設定）",
            behavior=QgsProcessingParameterFile.Behavior.Folder,
            optional=True,
        )
    )


def resolve_resource(algorithm, parameters, context):
    dataset = load_dataset(algorithm.string(parameters, "DATASET_ID", context))
    resource_id = algorithm.string(parameters, "RESOURCE_ID", context)
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
    return dataset, {**resource, "resource_id": resource_id}


def is_zip(resource):
    return zip_scanner.download_suffix(resource["url"]) == ".zip"


def saved_directory(algorithm, parameters, context):
    return (
        algorithm.parameterAsFile(parameters, "DIRECTORY", context).strip()
        or local_storage.download_directory()
    )


def temporary_root(context):
    """Processing の一時領域は呼び出しをまたいで保持される。

    ブラウザ用 TemporaryDirectory の GUI 依存の寿命管理は使わない。
    """
    root = Path(QgsProcessingUtils.tempFolder(context)) / "ksj"
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


class DownloadAlgorithm(KsjAlgorithm):
    """配布 1 件を取得する共通部分。既定の取得先と MEMBER の要否はクラス属性で宣言する。"""

    TEMPORARY_DEFAULT = False
    REQUIRE_MEMBER = False

    def initAlgorithm(self, config=None):
        add_resource_parameters(self)
        self.add_string("MEMBER", "ZIP 内のファイル（目次の member）", optional=True)
        self.addParameter(
            QgsProcessingParameterBoolean(
                "TEMPORARY",
                "一時領域に取得（保存済みなら再利用）",
                defaultValue=self.TEMPORARY_DEFAULT,
            )
        )
        self.addOutput(
            QgsProcessingOutputString("RESULTS", "取得元とレイヤー一覧（JSON）")
        )
        self.addOutput(QgsProcessingOutputString("LOCAL_PATH", "取得済みデータのパス"))

    def obtain(self, parameters, context, feedback):
        """既存の保存構成・部分取得を共用。全体取得への切り替えは入力で明示する。"""
        check_canceled(feedback)
        dataset, resource = resolve_resource(self, parameters, context)
        member = self.string(parameters, "MEMBER", context)
        if not is_zip(resource):
            if member:
                raise QgsProcessingException(
                    "ZIP 以外の配布では MEMBER を空欄にしてください。"
                )
        elif member:
            reason = remote_zip.unavailable_reason(member)
            if reason:
                raise QgsProcessingException(reason + FULL_DOWNLOAD_HELP)
        elif self.REQUIRE_MEMBER:
            raise QgsProcessingException(
                "ZIP は MEMBER の指定が必要です。ksj:list_resource_files で目次を確認してください。"
            )
        directory = saved_directory(self, parameters, context)
        temporary = self.parameterAsBool(parameters, "TEMPORARY", context)
        if not temporary and not directory:
            raise QgsProcessingException(
                "DIRECTORYに既存の保存先フォルダを指定してください。"
            )
        feedback.pushInfo(
            f"{'部分取得' if member else '全体取得'}: {resource['filename']} {member}"
        )
        try:
            scratch = temporary_root(context) if temporary else None
            if member:
                path = remote_zip.obtain_member(
                    resource["url"],
                    member,
                    directory,
                    scratch,
                    feedback.isCanceled,
                    feedback.setProgress,
                )
            else:
                path = local_storage.obtain_local_data(
                    resource["url"],
                    directory,
                    scratch,
                    feedback.isCanceled,
                    feedback.setProgress,
                )
            feedback.setProgressText("取得済みファイルのレイヤーを確認しています")
            layers, unreadable = scan_layers(path, feedback)
        except FETCH_ERRORS as exc:
            raise QgsProcessingException(str(exc)) from exc
        check_canceled(feedback)
        if not layers:
            feedback.pushWarning(
                "読み込めるレイヤーがありません。保存データと公式説明を確認してください。"
            )
        return {
            "dataset": dataset_metadata(dataset),
            "resource": resource,
            "member": member,
            "local_path": path,
            "layers": layers,
            "unreadable_files": unreadable,
        }

    def outputs(self, result, feedback):
        feedback.setProgress(100)
        return {
            "RESULTS": json.dumps(result, ensure_ascii=False),
            "LOCAL_PATH": result["local_path"],
        }


class DownloadResource(DownloadAlgorithm):
    def name(self):
        return "download_resource"

    def displayName(self):
        return "国土数値情報を取得・展開してレイヤー一覧を返す"

    def shortHelpString(self):
        return (
            FORMAT_SELECTION_HELP
            + "ZIP 内の指定ファイルを部分取得します。MEMBER が空欄なら配布全体を取得・展開します。\n\n"
            + RESOURCE_INPUT_HELP
            + "Shapefile の .shx / .dbf / .prj / .cpg など必要な付属ファイルも取得します。"
            "入れ子 ZIP・VRT は MEMBER を空欄にして全体取得してください。部分取得失敗時は自動で全体取得しません。"
            "DIRECTORY は既存の保存フォルダ（省略時はブラウザの保存先、未設定ならエラー）。"
            "TEMPORARY=true なら保存先不要で Processing の一時領域に取得します。既定は false。"
            "保存済みデータは再利用します。一時ファイルは後続処理でも使えますが、永続保存には使えません。"
            "LOCAL_PATH は取得先、RESULTS は dataset（出典・利用条件）、resource、member、local_path、"
            "layers（source / provider / name / file）、unreadable_files を含む JSON。"
            "layers の source / provider / name を ksj:load_layer の SOURCE / PROVIDER / NAME へ渡せます。"
            "取得して直接レイヤーを返す場合は ksj:load_resource を利用できます。"
            "ダイアログ表示・設定変更は行いません。Mapsuke では run_processing_in_background で実行できます。"
        )

    def processAlgorithm(self, parameters, context, feedback):
        return self.outputs(self.obtain(parameters, context, feedback), feedback)


def member_records(names, feedback):
    """部分取得の可否・推奨情報を付け、取得可能な Shapefile を先に返す。

    付属ファイルは同フォルダ・同名で索引化する。各レイヤーごとに ZIP 全目次を
    再走査すると、大きな配布で二乗時間になる。
    """
    entries, companions = [], {}
    for name in names:
        check_canceled(feedback)
        path = PurePosixPath(name)
        key = (path.parent, path.stem.casefold())
        companions.setdefault(key, []).append(name)
        entries.append((name, path, key))
    preferred, remaining = [], []
    for name, path, key in entries:
        check_canceled(feedback)
        if not zip_scanner.is_supported_entry(name):
            continue
        reason = remote_zip.unavailable_reason(name, companions[key])
        recommended = path.suffix.lower() == ".shp" and not reason
        records = preferred if recommended else remaining
        records.append(
            {
                "member": name,
                "name": path.name,
                "provider": ""
                if zip_scanner.is_archive(name)
                else zip_scanner.provider_key(name),
                "partial_available": not reason,
                "reason": reason,
                "recommended": recommended,
                "recommendation_reason": SHAPEFILE_RECOMMENDATION
                if recommended
                else "",
            }
        )
    return preferred + remaining


class ListResourceFiles(PagedAlgorithm):
    def name(self):
        return "list_resource_files"

    def displayName(self):
        return "国土数値情報の ZIP 内ファイルを一覧・検索（目次の部分取得）"

    def shortHelpString(self):
        return (
            FORMAT_SELECTION_HELP
            + "ZIP の目次だけを部分取得し、取得対象のファイルを検索します。保存先の設定は不要です。\n\n"
            "DATASET_ID / RESOURCE_ID は ksj:list_resources の結果を指定。"
            "QUERY は空白区切り AND 検索、LIMIT / OFFSET でページングします。"
            "DIRECTORY の保存済み目次も再利用（省略時はブラウザの保存先）。"
            "RESULTS は dataset（出典・利用条件）、resource、items、total、next_offset を含む JSON。"
            "items の member を ksj:download_resource または ksj:load_resource の MEMBER へ渡します。"
            "必須の付属ファイルが揃い部分取得可能な Shapefile を先に返し、recommended=true と recommendation_reason（推奨理由）を付けます。"
            "その他は recommended=false、推奨理由は空文字です。全候補を残し、同じ優先度では元の順序を維持します。"
            "推奨は内容の同一性を保証しません。明示した MEMBER の形式は変更しません。"
            "provider は形式からの推定で、実際のサブレイヤーは取得後に確認します。"
            "partial_available=false の項目には reason を返します。入れ子 ZIP・VRT は全体取得が必要です。"
            "ZIP 以外は通信せず単体ファイルの情報（member は空文字）を返します。"
            "部分取得非対応時はエラーとなり、自動で全体取得しません。"
            "Mapsuke では run_processing_in_background で実行できます。"
        )

    def initAlgorithm(self, config=None):
        add_resource_parameters(self)
        self.add_string("QUERY", "ファイル名の検索語", optional=True)
        self.add_paging()

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        dataset, resource = resolve_resource(self, parameters, context)
        if is_zip(resource):
            feedback.pushInfo(f"ZIP の目次を確認: {resource['filename']}")
            try:
                names = remote_zip.list_members(
                    resource["url"],
                    saved_directory(self, parameters, context),
                    feedback.isCanceled,
                )
            except FETCH_ERRORS as exc:
                raise QgsProcessingException(str(exc)) from exc
            records = member_records(names, feedback)
        else:
            records = [
                {
                    "member": "",
                    "name": resource["filename"],
                    "provider": zip_scanner.provider_key(resource["filename"]),
                    "partial_available": False,
                    "reason": "単体ファイルです。MEMBER は空欄で取得できます。",
                    "recommended": False,
                    "recommendation_reason": "",
                }
            ]
        records = self.select(records, parameters, context, feedback)
        feedback.setProgress(100)
        return self.page(
            records,
            parameters,
            context,
            dataset=dataset_metadata(dataset),
            resource=resource,
        )


class LoadResource(DownloadAlgorithm):
    TEMPORARY_DEFAULT = True
    REQUIRE_MEMBER = True

    def name(self):
        return "load_resource"

    def displayName(self):
        return "国土数値情報を部分取得してレイヤーとして読み込む"

    def shortHelpString(self):
        return (
            FORMAT_SELECTION_HELP
            + "ZIP 内の選択ファイルを部分取得し、解析用レイヤーを返します。既定は保存先不要の一時取得です。\n\n"
            + RESOURCE_INPUT_HELP
            + "ZIP では MEMBER 必須、単体ファイルでは空欄。自動で ZIP 全体を取得しません。"
            "Shapefile などの付属ファイルも取得し、保存済みデータは再利用します。"
            "TEMPORARY の既定は true。false にすると DIRECTORY（省略時はブラウザ設定）に保存します。"
            "一時ファイルは Processing の一時領域で保持し、レイヤーを閉じても即時削除しません。"
            "プロジェクト保存だけでは永続化されないため、必要な結果は別途保存してください。"
            "GML / GeoPackage などは選択ファイル内の全サブレイヤーを返します。"
            "SUBLAYER に取得結果の layers[].name を完全一致で指定すると絞り込めます。"
            + ENCODING_HELP
            + "LAYERS は標準の複数マップレイヤー出力、LOCAL_PATH は取得先、RESULTS は出典・利用条件とレイヤー一覧の JSON。"
            "アルゴリズム自体はプロジェクトを変更しません。processing.run の LAYERS を後続解析へ渡せます。"
            "Mapsuke では run_processing_in_background('ksj:load_resource', parameters) により、"
            "取得・読み込みをバックグラウンドで行い、完了時に Mapsuke が結果を地図へ追加します。"
        )

    def initAlgorithm(self, config=None):
        super().initAlgorithm(config)
        self.add_string(
            "SUBLAYER",
            "サブレイヤー名（空欄は選択ファイル内の全レイヤー）",
            optional=True,
        )
        add_encoding_parameter(self)
        self.addOutput(QgsProcessingOutputMultipleLayers("LAYERS", "解析用レイヤー"))

    def processAlgorithm(self, parameters, context, feedback):
        result = self.obtain(parameters, context, feedback)
        sublayer = self.string(parameters, "SUBLAYER", context)
        selected = [
            item
            for item in result["layers"]
            if not sublayer or item["name"] == sublayer
        ]
        if not selected:
            available = ", ".join(item["name"] for item in result["layers"])
            raise QgsProcessingException(
                f"読み込めるレイヤーがありません。SUBLAYER を確認してください。候補: {available or 'なし'}"
            )
        encoding = ENCODING_OPTIONS[
            self.parameterAsEnum(parameters, "ENCODING", context)
        ]
        # 全件が成功するまでコンテキストに公開しない。失敗時に半端な出力を残さない。
        layers = [
            create_layer(
                item["source"],
                item["provider"],
                item["name"],
                encoding,
                context,
                feedback,
            )
            for item in selected
        ]
        check_canceled(feedback)
        for layer in layers:
            context.temporaryLayerStore().addMapLayer(layer)
        return {
            **self.outputs({**result, "layers": selected}, feedback),
            "LAYERS": [layer.id() for layer in layers],
        }
