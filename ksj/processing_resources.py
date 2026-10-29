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


FULL_DOWNLOAD_HELP = (
    "ksj:download_resource で MEMBER を空欄にして全体取得してください。"
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


def add_download_parameters(algorithm, temporary_default=False):
    add_resource_parameters(algorithm)
    algorithm.add_string("MEMBER", "ZIP 内のファイル（目次の member）", optional=True)
    algorithm.addParameter(
        QgsProcessingParameterBoolean(
            "TEMPORARY",
            "一時領域に取得（保存済みなら再利用）",
            defaultValue=temporary_default,
        )
    )
    algorithm.addOutput(
        QgsProcessingOutputString("RESULTS", "取得元とレイヤー一覧（JSON）")
    )
    algorithm.addOutput(QgsProcessingOutputString("LOCAL_PATH", "取得済みデータのパス"))


def resolve_resource(algorithm, parameters, context):
    dataset = load_dataset(algorithm.string(parameters, "DATASET_ID", context))
    resource_id = algorithm.string(parameters, "RESOURCE_ID", context)
    for resource in dataset["resources"]:
        if local_storage.url_key(resource["url"]) == resource_id:
            if (
                zip_scanner.download_suffix(resource["url"])
                not in zip_scanner.SUPPORTED_EXTENSIONS
            ):
                raise QgsProcessingException(
                    "この配布形式は直接読み込めません。公式説明ページから原本を取得してください: "
                    f"{resource['url']}"
                )
            return dataset, {**resource, "resource_id": resource_id}
    raise QgsProcessingException(
        "配布IDが見つかりません。ksj:list_resourcesで確認してください。"
    )


def saved_directory(algorithm, parameters, context):
    return (
        algorithm.parameterAsFile(parameters, "DIRECTORY", context).strip()
        or local_storage.download_directory()
    )


def partial_unavailable_reason(member):
    if zip_scanner.is_archive(member):
        return "入れ子 ZIP の内部を読むには配布全体の取得が必要です。"
    if PurePosixPath(member).suffix.lower() == ".vrt":
        return "VRT は外部データを参照するため配布全体の取得が必要です。"
    if not zip_scanner.is_layer_file(member):
        return "読み込み対象のレイヤーファイルを指定してください。"
    return ""


def obtain_resource(algorithm, parameters, context, feedback, require_member=False):
    """既存の保存構成・部分取得を共用。全体取得への切り替えは入力で明示する。"""
    check_canceled(feedback)
    dataset, resource = resolve_resource(algorithm, parameters, context)
    member = algorithm.string(parameters, "MEMBER", context)
    is_zip = zip_scanner.download_suffix(resource["url"]) == ".zip"
    if member and not is_zip:
        raise QgsProcessingException("ZIP 以外の配布では MEMBER を空欄にしてください。")
    if require_member and is_zip and not member:
        raise QgsProcessingException(
            "ZIP は MEMBER の指定が必要です。ksj:list_resource_files で目次を確認してください。"
        )
    if member:
        reason = partial_unavailable_reason(member)
        if reason:
            raise QgsProcessingException(reason + FULL_DOWNLOAD_HELP)
    directory = saved_directory(algorithm, parameters, context)
    temporary = algorithm.parameterAsBool(parameters, "TEMPORARY", context)
    if not temporary and not directory:
        raise QgsProcessingException(
            "DIRECTORYに既存の保存先フォルダを指定してください。"
        )
    feedback.pushInfo(
        f"{'部分取得' if member else '全体取得'}: {resource['filename']} {member}"
    )
    try:
        path = None
        if temporary:
            path = (
                remote_zip.saved_member(resource["url"], member, directory)
                if member
                else local_storage.saved_local_data(resource["url"], directory)
            )
            # Processing の一時領域は呼び出しをまたいで保持される。
            # ブラウザ用 TemporaryDirectory の GUI 依存の寿命管理は使わない。
            if not path:
                root = Path(QgsProcessingUtils.tempFolder(context)) / "ksj"
                root.mkdir(parents=True, exist_ok=True)
                directory = str(root)
        if not path:
            if member:
                path = remote_zip.ensure_member(
                    resource["url"],
                    member,
                    directory,
                    feedback.isCanceled,
                    feedback.setProgress,
                )
            else:
                path = local_storage.ensure_local_data(
                    resource["url"],
                    directory,
                    feedback.isCanceled,
                    feedback.setProgress,
                )
        feedback.setProgressText("取得済みファイルのレイヤーを確認しています")
        layers, unreadable = scan_layers(path, feedback)
    except (local_storage.DownloadError, zip_scanner.ZipScanError, OSError) as exc:
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


def download_outputs(result, feedback):
    feedback.setProgress(100)
    return {
        "RESULTS": json.dumps(result, ensure_ascii=False),
        "LOCAL_PATH": result["local_path"],
    }


class DownloadResource(KsjAlgorithm):
    def name(self):
        return "download_resource"

    def displayName(self):
        return "国土数値情報を取得・展開してレイヤー一覧を返す"

    def shortHelpString(self):
        return (
            "ZIP 内の指定ファイルを部分取得します。MEMBER が空欄なら配布全体を取得・展開します。\n\n"
            "DATASET_ID / RESOURCE_ID は ksj:list_resources、MEMBER は ksj:list_resource_files の member を指定。"
            "Shapefile の .shx / .dbf / .prj / .cpg など必要な付属ファイルも取得します。"
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

    def initAlgorithm(self, config=None):
        add_download_parameters(self)

    def processAlgorithm(self, parameters, context, feedback):
        result = obtain_resource(self, parameters, context, feedback)
        return download_outputs(result, feedback)


class ListResourceFiles(PagedAlgorithm):
    def name(self):
        return "list_resource_files"

    def displayName(self):
        return "国土数値情報の ZIP 内ファイルを一覧・検索（目次の部分取得）"

    def shortHelpString(self):
        return (
            "ZIP の目次だけを部分取得し、取得対象のファイルを検索します。保存先の設定は不要です。\n\n"
            "DATASET_ID / RESOURCE_ID は ksj:list_resources の結果を指定。"
            "QUERY は空白区切り AND 検索、LIMIT / OFFSET でページングします。"
            "DIRECTORY の保存済み目次も再利用（省略時はブラウザの保存先）。"
            "RESULTS は dataset（出典・利用条件）、resource、items、total、next_offset を含む JSON。"
            "items の member を ksj:download_resource または ksj:load_resource の MEMBER へ渡します。"
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
        directory = saved_directory(self, parameters, context)
        records = []
        if zip_scanner.download_suffix(resource["url"]) == ".zip":
            feedback.pushInfo(f"ZIP の目次を確認: {resource['filename']}")
            try:
                names = remote_zip.list_members(
                    resource["url"], directory, feedback.isCanceled
                )
                # 付属ファイルは同フォルダ・同名で索引化する。
                # 各レイヤーごとに ZIP 全目次を再走査すると、大きな配布で二乗時間になる。
                companions = {}
                for name in names:
                    check_canceled(feedback)
                    path = PurePosixPath(name)
                    companions.setdefault(
                        (path.parent, path.stem.casefold()), []
                    ).append(name)
                for name in names:
                    check_canceled(feedback)
                    if not zip_scanner.is_supported_entry(name):
                        continue
                    reason = partial_unavailable_reason(name)
                    path = PurePosixPath(name)
                    if not reason and path.suffix.lower() == ".shp":
                        try:
                            remote_zip.related_members(
                                name, companions[(path.parent, path.stem.casefold())]
                            )
                        except local_storage.DownloadError as exc:
                            reason = str(exc)
                    records.append(
                        {
                            "member": name,
                            "name": PurePosixPath(name).name,
                            "provider": ""
                            if zip_scanner.is_archive(name)
                            else zip_scanner.provider_key(name),
                            "partial_available": not bool(reason),
                            "reason": reason,
                        }
                    )
            except (
                local_storage.DownloadError,
                zip_scanner.ZipScanError,
                OSError,
            ) as exc:
                raise QgsProcessingException(str(exc)) from exc
        else:
            records.append(
                {
                    "member": "",
                    "name": resource["filename"],
                    "provider": zip_scanner.provider_key(resource["filename"]),
                    "partial_available": False,
                    "reason": "単体ファイルです。MEMBER は空欄で取得できます。",
                }
            )
        records = self.select(records, parameters, context, feedback)
        feedback.setProgress(100)
        return self.page(
            records,
            parameters,
            context,
            dataset=dataset_metadata(dataset),
            resource=resource,
        )


class LoadResource(KsjAlgorithm):
    def name(self):
        return "load_resource"

    def displayName(self):
        return "国土数値情報を部分取得してレイヤーとして読み込む"

    def shortHelpString(self):
        return (
            "ZIP 内の選択ファイルを部分取得し、解析用レイヤーを返します。既定は保存先不要の一時取得です。\n\n"
            "DATASET_ID / RESOURCE_ID は ksj:list_resources、MEMBER は ksj:list_resource_files の member を指定。"
            "ZIP では MEMBER 必須、単体ファイルでは空欄。自動で ZIP 全体を取得しません。"
            "Shapefile などの付属ファイルも取得し、保存済みデータは再利用します。"
            "TEMPORARY の既定は true。false にすると DIRECTORY（省略時はブラウザ設定）に保存します。"
            "一時ファイルは Processing の一時領域で保持し、レイヤーを閉じても即時削除しません。"
            "プロジェクト保存だけでは永続化されないため、必要な結果は別途保存してください。"
            "GML / GeoPackage などは選択ファイル内の全サブレイヤーを返します。"
            "SUBLAYER に取得結果の layers[].name を完全一致で指定すると絞り込めます。"
            "ENCODING は 0: 自動判定、1: UTF-8、2: Shift_JIS、3: EUC-JP（Shapefile のみ）。"
            "LAYERS は標準の複数マップレイヤー出力、LOCAL_PATH は取得先、RESULTS は出典・利用条件とレイヤー一覧の JSON。"
            "アルゴリズム自体はプロジェクトを変更しません。processing.run の LAYERS を後続解析へ渡せます。"
            "Mapsuke では run_processing_in_background('ksj:load_resource', parameters) により、"
            "取得・読み込みをバックグラウンドで行い、完了時に Mapsuke が結果を地図へ追加します。"
        )

    def initAlgorithm(self, config=None):
        add_download_parameters(self, temporary_default=True)
        self.add_string(
            "SUBLAYER",
            "サブレイヤー名（空欄は選択ファイル内の全レイヤー）",
            optional=True,
        )
        add_encoding_parameter(self)
        self.addOutput(QgsProcessingOutputMultipleLayers("LAYERS", "解析用レイヤー"))

    def processAlgorithm(self, parameters, context, feedback):
        result = obtain_resource(
            self, parameters, context, feedback, require_member=True
        )
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
        result["layers"] = selected
        return {
            **download_outputs(result, feedback),
            "LAYERS": [layer.id() for layer in layers],
        }
