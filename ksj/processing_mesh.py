"""配布メッシュの索引を Processing 出力として返す。"""

from qgis.core import QgsProcessingException, QgsProcessingOutputMapLayer

from . import mesh_index
from .processing_algorithms import ResourceFilterAlgorithm, check_canceled


class CreateMeshIndex(ResourceFilterAlgorithm):
    def name(self):
        return "create_mesh_index"

    def displayName(self):
        return "国土数値情報の配布メッシュ索引を作成"

    def shortHelpString(self):
        return (
            "配布のある一次メッシュを地図・解析用の索引レイヤーとして返します。通信は行いません。\n\n"
            "DATASET_ID は ksj:search_datasets の id。YEAR / REGION / FORMAT / QUERY は "
            "ksj:list_resources と同じ絞り込みで、該当する全配布を対象にします（ページングなし）。"
            "OUTPUT は EPSG:4326 のポリゴンレイヤー。mesh_code、file_count、resources（配布の JSON）を持ちます。"
            "resources の resource_id を ksj:list_resource_files または ksj:load_resource へ渡せます。"
            "索引は配布単位の一次メッシュ（4 桁、約 80 km）の概略位置です。"
            "旧日本測地系の厳密な境界や、データ自体のメッシュ細分・収録範囲を示すものではありません。"
            "プロジェクトへ追加後はブラウザの索引と同じ地物アクションが利用できます。"
            "処理本体はプロジェクトを変更しません。"
        )

    def initAlgorithm(self, config=None):
        self.add_resource_filters()
        self.addOutput(QgsProcessingOutputMapLayer("OUTPUT", "配布メッシュ索引"))

    def processAlgorithm(self, parameters, context, feedback):
        check_canceled(feedback)
        dataset, resources = self.filtered_resources(parameters, context, feedback)
        feedback.pushInfo("配布メッシュの索引を作成しています")
        try:
            layer = mesh_index.create_mesh_index(dataset["title"], resources)
        except ValueError as exc:
            raise QgsProcessingException(str(exc)) from exc
        check_canceled(feedback)
        context.temporaryLayerStore().addMapLayer(layer)
        feedback.setProgress(100)
        return {"OUTPUT": layer.id()}
