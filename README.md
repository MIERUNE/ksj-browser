# ksj-provider - 国土数値情報 QGIS ブラウザプラグイン

国土数値情報（KSJ）のリモート ZIP データを QGIS ブラウザパネルから直接閲覧・読み込みできるプラグインです。

## 機能

- **リモート ZIP 探索**: ネットワーク上の ZIP ファイルを GDAL VSI 経由で直接スキャン
- **階層表示**: ZIP 内のフォルダ構造をブラウザパネルにツリー形式で表示
- **対応形式**: `.shp` (Shapefile), `.geojson` (GeoJSON), `.gml` (Geography Markup Language)
- **ドラッグ&ドロップ**: ブラウザからマップキャンバスへファイルを直接追加
- **複数コレクション対応**:
  - 土砂災害警戒区域（A33）
  - 行政区域（N03）

## Preparation

1. install \`uv\`

   - <https://docs.astral.sh/uv/#getting-started>

2. install dependencies with uv

   \`\`\`sh

   # macOS

   uv venv --python /Applications/QGIS.app/Contents/MacOS/bin/python3 --system-site-packages

   # Windows 適切なバージョンの QGIS のディレクトリを参照すること

   uv venv --python C:\Program Files\QGIS 3.28.2\apps\Python39\python.exe --system-site-packages
   \`\`\`

   仮想環境がカレントディレクトリに\`.venv\`フォルダとして作成されます。

3. (when VSCode) 仮想環境を VSCode 上の Python インタプリタとして選択

   VSCode はカレントディレクトリの仮想環境を検出しますが、手動で選択する必要がある場合もあります。

   1. [Cmd + Shift + P]でコマンドパレットを開く
   2. [Python: Select Interpreter]を見つけてクリック
   3. 利用可能なインタプリタ一覧が表示されるので、先ほど作成した仮想環境\`/.venv/bin/python\`を選択（通常、リストの一番上に"Recommended"として表示される）

## データコレクションの更新

新しい国土数値情報データが公開された場合、以下のスクリプトでデータ定義を更新できます：

### 行政区域データ（N03）の更新

\`\`\`bash
python scripts/update_gyousei_kuiki.py
\`\`\`

このスクリプトは以下を実行します：

1. N03 ページの HTML をパース
2. 年度・地域・ファイル名を抽出
3. \`ksj/data_collections/gyousei_kuiki.json\` を更新

詳細は [specs/002-admin-area-data/quickstart.md](specs/002-admin-area-data/quickstart.md) を参照してください。

## テスト実行

**macOS の場合**: QGIS 環境変数を設定してからテストを実行する必要があります。

\`\`\`bash

# QGIS 環境変数を設定（macOS のみ）

source setup_qgis_env.sh && uv run python -m pytest -v

# 全テストを実行

.venv/bin/pytest tests/ -v

# カバレッジ付きで実行

.venv/bin/pytest tests/ --cov=ksj --cov=scripts --cov-report=term-missing
\`\`\`

## QGIS での使用方法

1. QGIS を起動
2. ブラウザパネルを開く（表示 → パネル → ブラウザ）
3. 「国土数値情報（KSJ）」ノードを展開
4. 目的のコレクション（例: 「行政区域」）を選択
5. 年度と地域を展開
6. \`.shp\`, \`.geojson\`, \`.gml\` ファイルをダブルクリックまたはドラッグ&ドロップでマップに追加

## プロジェクト構成

\`\`\`
ksj-provider/
├── ksj/ # プラグイン本体
│ ├── browser.py # ブラウザアイテム実装
│ ├── data_loader.py # URL 生成・データ定義読み込み
│ ├── zip_scanner.py # リモート ZIP スキャナ
│ └── data_collections/ # データ定義 JSON
│ ├── dosyasaigai_keikai_kuiki.json # A33 土砂災害警戒区域
│ └── gyousei_kuiki.json # N03 行政区域
├── scripts/ # 開発者ツール
│ ├── update_gyousei_kuiki.py # N03 データ定義生成ツール
│ └── update_dosyasaigai_keikai_kuiki.py # A33 土砂災害警戒区域データ更新ツール
├── tests/ # テストスイート
│ ├── test_browser_items.py # ブラウザアイテムテスト
│ ├── test_data_loader.py # データローダーテスト
│ ├── test_zip_scanner.py # ZIP スキャナテスト
│ ├── test_update_gyousei_kuiki.py # 行政区域更新ツールテスト
│ └── test_update_dosyasaigai_keikai_kuiki.py # 土砂災害警戒区域更新ツールテスト
└── specs/ # 仕様ドキュメント
├── 001-zip-recursive-browse/ # ZIP 再帰探索機能
└── 002-admin-area-data/ # 行政区域データサポート
\`\`\`

## アーキテクチャ

### ブラウザアイテム階層

\`\`\`
KsjRootItem (国土数値情報（KSJ）)
└── KsjCollectionItem (例: 行政区域)
└── KsjYearItem (例: 2025 年)
└── KsjPrefectureItem (例: 北海道)
└── KsjZipFolderItem (ZIP 内フォルダ)
└── KsjZipFileItem (ZIP 内ファイル: .shp, .geojson, .gml)
\`\`\`

### URL 生成戦略

異なるデータコレクションは異なる URL 形式を持つため、戦略パターンを使用：

- **A33（土砂災害警戒区域）**: \`data/A33/A33-YY/<filename>\`
  - ディレクトリ年はファイル名の下 2 桁から決定（例: \`A33-24_01.zip\` → \`24\`）
- **N03（行政区域）**: \`data/N03/N03-YYYY/<filename>\`
  - ディレクトリ年は年度キーから 4 桁抽出（例: \`2025 年\` → \`2025\`）

### リモート ZIP スキャン

GDAL VSI（Virtual File System Interface）を使用してリモート ZIP を直接スキャン：

\`\`\`
/vsizip//vsicurl/https://nlftp.mlit.go.jp/ksj/.../file.zip
\`\`\`

## 開発のヒント

- 関心ごとに応じて、モジュールを分割しましょう（例：\`ui\`モジュール）
- \`relative import\`の利用を推奨します：以下のような絶対パスによるインポートは[Plugin Reloader](https://plugins.qgis.org/plugins/plugin_reloader/)で変更が反映されなくなることがあります

  \`\`\`python

  # root.py

  from child import Child # NG
  from .child import Child # OK

  # child.py

  from grand_child import GrandChild # 子要素がその子要素インポートする際も同様
  from .grand_child import GrandChild # OK
  \`\`\`

- \`ui\`ファイルから生成されるインスタンスには型定義がありません。以下のようなコードで型定義を手動で当てることが出来ます。

  \`\`\`python
  class DialogType: # 型定義：UI ファイルで定義されていて Python から操作したいインスタンスはここに定義する # 生成 AI に任せてもそこそこまともに出力してくれます
  verticalLayout: QVBoxLayout
  lineEdit: QLineEdit
  horizontalLayout: QHBoxLayout
  pushButton_run: QPushButton
  pushButton_cancel: QPushButton

  class Dialog(QDialog):
  def **init**(self):
  super().**init**()

          # 強制的に型キャスト：型の正しさは開発者の責任
          self.ui = cast(
              DialogType,
              uic.loadUi(os.path.join(os.path.dirname(__file__), "dialog.ui"), self),
          )

          self.ui.pushButton_run.clicked.connect(self.get_and_show_input_text)
          self.ui.pushButton_cancel.clicked.connect(self.close)

  \`\`\`

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。

## 関連リンク

- [国土数値情報ダウンロードサイト](https://nlftp.mlit.go.jp/ksj/)
- [QGIS Documentation](https://docs.qgis.org/)
- [GDAL VSI Documentation](https://gdal.org/user/virtual_file_systems.html)
