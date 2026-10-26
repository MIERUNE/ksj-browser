# README の再構成と画像の更新 設計

日付: 2026-10-26
対象: `README.md`、`imgs/`、`scripts/capture_readme_images.py`（新規）、`tests/test_readme_assets.py`（新規）

## 目的

README の画像を現在のプラグインの表示に合わせて撮り直し、本文を見出しのある読みやすい構成に組み直す。PR #35 の申し送り（ブラウザパネルの画像がルート名・ルートアイコンとも古い）を解消する。

画像の現状:

| 画像 | 状態 |
| --- | --- |
| `browser-panel-dark.png` / `browser-panel-light.png` | 古い。ルート名が「国土数値情報（KSJ）」、ルートアイコンが旧線画、先頭の「追加方法」行がない |
| `browser-loading-indicator.png` | ルートアイコンだけ旧線画。ダーク表示 |
| `browser-loading-mode.png` | ルートアイコンだけ旧線画 |
| `loading-settings.png` | 現行どおり（文言はコードと一致） |
| `processing-download.png` / `processing-load-encoding.png` | 現行どおり（ラベル・ヘルプ文はコードと一致） |
| 未使用 7 枚（`browser-file-context-menu.png`、`browser-file-icons.png`、`browser-mesh-index-action-dark.png`、`browser-mesh-index-action-light.png`、`mesh-index-qgis.jpg`、`mesh-layer-selection.png`、`mesh-resource-dialog.jpg`） | README からも `specs/` からも参照されていない |

本文の現状: 「使い方」の下に、探し方・追加・設定・保存データ・文字コード・共有・旧形式・メッシュ索引が見出しなしで並び、ブラウザ全体の画像がメッシュ索引の節の末尾にある。「開発環境」「構成」が本文の 3 割を占める。

## 決定事項

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| README の読み手 | 1 つの README に利用者向け・開発者向けの両方を残し、階層と順序だけ整える | 利用者の指定。ファイルを増やさない |
| インストール節 | 書かない | 公式プラグインリポジトリへの登録予定があり、配布形態が固まってから追記する（別仕様「リリースの仕組み」） |
| ブラウザ全体の画像 | ライト表示 1 枚（`browser-panel-light.png`）。ダーク版は削除 | 撮り直しと保守が半分で済み、他の画像とも揃う |
| 読み込み中表示の画像 | ライト表示で撮り直す | 他の画像と揃える |
| メッシュ索引の画像 | 既存の `browser-mesh-index-action-light.png`、`mesh-layer-selection.png` を使い、`mesh-resource-dialog.jpg` はライト表示の PNG で撮り直す。`mesh-index-qgis.jpg` は使わない | QGIS 全体の画像はダーク表示で他と揃わず、縮小すると枠と番号が読めない |
| アイコン一覧の画像 | 既存の `browser-file-icons.png` を「アイコンの意味」の段落で使う | 内容は現行どおりで、文章だけより伝わる |
| Processing の節 | 手順・ダイアログの説明・Python の例を削除し、アルゴリズム ID の表だけを「## Processing アルゴリズム」として残す | 利用者の指定。Processing は主にエージェントや自動処理が使う機能で、人が読む意味合いが薄い。ID の一覧だけは README に残す |
| 撮影方法 | QGIS.app 同梱 Python でウィジェットを描画して `grab()` する。スクリプトを `scripts/capture_readme_images.py` としてコミットする | 画像の撮り直しは今回で 3 度目で、文言変更のたびに必要になる。手順を残して次回の工数を減らす |
| 撮影に使う QGIS | ホストの QGIS.app（3.42）の Python（`.venv`） | 前回の `loading-settings.png` と同じ環境。ツリー表示とダイアログの見た目は最低対応版 3.44 と変わらない |
| 本文の事実 | 削らない。位置と順序だけ変える | 制約や既知の挙動の記録を失わない。削るのは Processing の手順と Python の例だけ |

## README の構成

現在の README の行番号で、各段落の移動先を示す。

```
# ksj-browser — 国土数値情報ブラウザ（QGIS プラグイン）
  概要（L3）、対応 QGIS（L7）、Processing にもアルゴリズムがある旨の 1 文（L5 を短縮）
  [画像] browser-panel-light.png

## ブラウザパネルで使う
### データを探す
  展開の手順 1〜4（L11〜14）
  配布形態の網羅と都市計画決定情報（L21）
  アイコンの意味と件数表示（L23）[画像] browser-file-icons.png
  右クリックで公式説明・属性定義・利用条件（L25）
  旧形式のまとめ方と GDAL で読めない形式（L87。Processing への言及は 1 句に短縮）
### レイヤーを追加する
  ダブルクリック・ドラッグ・サブレイヤー（L15）
  読み込み中表示（L17）[画像] browser-loading-indicator.png
  取得するファイルの範囲（L37）
  全体取得が必要な場合（L47）
  進捗の確認と取消（L39 末尾）
### 追加方法・保存先を設定する
  設定画面の開き方・3 つの選択肢・変更の反映（L29・L41）
  Processing の取得処理には適用しない旨（L93 を 1 文に）
  [画像] browser-loading-mode.png、loading-settings.png
  #### フォルダに保存して追加（L31）
  #### 一時レイヤーとして追加（L32）
  #### クラウド（kumoy）にアップロードして追加（L33、L55〜61）
### 地図のメッシュをクリックして追加する（L63〜81）
  [画像] 手順 1 の後に browser-mesh-index-action-light.png
         手順 3 の後に mesh-resource-dialog.png
         手順 4 の後に mesh-layer-selection.png

## 保存したデータの扱い
### 保存先の構成（L39）
### 公開元が更新されたとき（L49）
### プロジェクトを共有する（L51〜53）

## 文字コード（L35。Processing の文字コード指定への言及は 1 句に短縮）

## 収録範囲とカタログの更新（L156〜178。内容は現状維持）

## Processing アルゴリズム
  導入 1 文、ID と入出力の表（L125〜130）、「詳細は processing.algorithmHelp() で確認」の 1 文

## 開発環境（L180〜262。内容は現状維持、見出しの語句のみ調整）
## 構成（L264〜290。撮影スクリプトの行を追加）
## ライセンス（L292〜294。現状維持）
```

削除する段落: Processing の手順とダイアログの説明（L89〜123）、Python の例と kumoy との連結例（L132〜154）。
残すリンク: メッシュ索引の検証記録（L81）、収録範囲の検証記録（L160）。

## 本文の修正方針

- 事実（制約・既知の挙動・検証記録へのリンク）は削らず、上の構成の位置へ移す。
- 各節は「基本の手順 → 補足・制約」の順に段落を並べる。1 段落 1 話題に分ける。列挙（追加方法の 3 択、メッシュ索引の手順）は箇条書きのまま。
- 英数字と日本語の間は空白ありに統一する（「QGIS の」「Shapefile は」）。`AGENTS.md` と `metadata.txt` の表記に合わせる。全角の「／」「・」は現状どおり使い、半角スラッシュは ID や拡張子（`ogr` / `gdal`）だけに使う。
- 見出しは「データを探す」「レイヤーを追加する」のように動詞で終える。「Processingツールボックスから利用する」のような表記揺れを直す。
- 画像の代替テキストは、写っているものを 1 句で書く。
- 文体はです・ます調のまま。

## 画像

### 撮り直す 4 枚

すべてライト表示（macOS の Aqua 外観）、Retina を 1x に縮小した PNG。

| 画像 | 内容 | 大きさの目安 |
| --- | --- | --- |
| `browser-panel-light.png` | ルート（新アイコン）、先頭の「追加方法」行、分類一覧。「地形 → 低位地帯（ポリゴン）→ 2015年 → 都道府県」まで展開 | 幅 440 px |
| `browser-loading-mode.png` | ルート、「追加方法: 一時レイヤー（フォルダに保存しない）」行、分類一覧 | 幅 630 px |
| `browser-loading-indicator.png` | 「土地利用 → 土地利用3次メッシュ → 2021年 → 3622 → ZIP」を展開し、`.shp` の行を読み込み中表示に | 幅 900 px |
| `mesh-resource-dialog.png` | メッシュをクリックした後の配布ファイル選択ダイアログ | ダイアログの自然な大きさ |

ブラウザ表示の 3 枚は「追加方法」行をすべて「一時レイヤー（フォルダに保存しない）」で揃える。

### 撮影スクリプト scripts/capture_readme_images.py

macOS 専用。冒頭の docstring にその旨と実行手順を書く。

```bash
source setup_qgis_env.sh
.venv/bin/python scripts/capture_readme_images.py            # 4 枚すべて
.venv/bin/python scripts/capture_readme_images.py --only browser-loading-mode
```

出力先は既定で `imgs/`。`--output` で変えられる。

組み立て:

- `QgsApplication.setPrefixPath("/Applications/QGIS.app/Contents/MacOS", True)` → `QgsApplication([], True)` → `initQgis()`。ネイティブの cocoa で描画し、`QgsApplication` 生成後に ctypes で `NSApplication.sharedApplication` に `NSAppearanceNameAqua` を設定する（`imgs/loading-settings.png` を撮ったときと同じ方法）。
- `KsjDataItemProvider` を `dataItemProviderRegistry()` に登録し、`QgsBrowserModel` → `QgsBrowserProxyModel` → `QgsBrowserTreeView` を組み立てる。プロキシの `setShownDataItemProviderKeyFilter` でプロバイダ名「国土数値情報ブラウザ」の項目だけを表示し、ホームやドライブなど他のルートは出さない。
- 展開は `model.fetchMore(index)` の後、`rowCount > 0` になるまで `processEvents()` で待ち（`tests/helpers.pump_until` と同じ方法）、`view.expand(proxy.mapFromSource(index))` する。子は名前の前方一致で探す。
- 「追加方法」行は、`ksj.local_storage.loading_mode` と `download_directory` をモジュール属性ごと差し替えて `"temporary"` と `""` を返させる。利用者の QgsSettings には書き込まない。
- 読み込み中表示は、対象の `KsjFileItem` の `url`・`member` を持つダミーキーを `ksj.layer_loading.pending` に入れて `loading_signals.changed.emit()` し、本来の `update_loading()` を通す。撮影後に取り除く。
- 配布ファイル選択ダイアログは、同梱カタログから配布が 2 件以上あるメッシュを選び、本来の `ksj.mesh_index.choose_resource` を呼ぶ。`QTimer.singleShot` で `QApplication.activeModalWidget()` を `grab()` してから `reject()` する。
- 各画像は `widget.resize(幅, 高さ)` → `show()` → 500 ms 後に `grab()` → `devicePixelRatio` で割って 1x に縮小 → PNG 保存。
- 読み込み中表示の画像だけ、ZIP の目次を部分取得するため通信が発生する。それ以外は同梱カタログだけで描画できる。

### 新たに README で使う既存画像

`browser-file-icons.png`、`browser-mesh-index-action-light.png`、`mesh-layer-selection.png`。

### 削除する画像

`browser-panel-dark.png`、`browser-file-context-menu.png`、`browser-mesh-index-action-dark.png`、`mesh-index-qgis.jpg`、`mesh-resource-dialog.jpg`（PNG で撮り直す）、`processing-load-encoding.png`。

### 残す画像

`specs/` から参照される `catalog-browser.png`、`local-storage-setup.png`、`browser-message-types.png`、`processing-download.png`。README からは参照しなくなるものもあるが、検証記録の一部として残す。

## tests/test_readme_assets.py

標準ライブラリだけで書いたテストを 2 つ足す。`tests/conftest.py` が QGIS を読み込むため、実行には他のテストと同じく QGIS 環境を使う。

```python
def test_readme_relative_links_resolve():
    # README の相対リンク（画像・specs・metadata.txt など）がすべて存在する。
    ...

def test_every_image_is_referenced():
    # imgs/ の各ファイルが README か specs/**/*.md のいずれかから参照されている。
    ...
```

リンクの抽出は `](path)` の正規表現で行い、`http://`・`https://`・`#` で始まるものは除く。`specs/` 側の参照は各 Markdown のディレクトリを基準に解決する（`../../imgs/x.png` の形）。`docs/superpowers/` の設計書・計画は履歴であり、存在しない画像に触れていることがあるため対象にしない。

## 構成の表への追記

| パス | 役割 |
| --- | --- |
| `scripts/capture_readme_images.py` | README 用スクリーンショットの生成（macOS） |

## 検証

1. `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること。
2. `source setup_qgis_env.sh` のうえで `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q` が通ること。Docker（3.44）と 4.x は画像に影響しないため CI に任せる。
3. 撮り直した 4 枚を開き、ルートのアイコンが `ksj/icons/plugin.png`、ルート名が「国土数値情報」、「追加方法」行の文言が `ksj/catalog_browser.py` の文字列と一致すること。
4. `git grep -n "（KSJ）" -- README.md imgs` が 0 件であること。
5. README を通し読みし、各節が「基本の手順 → 補足」の順になっていること。
6. README の見出しが構成どおりで、画像が指定の位置にあること。

## 範囲外と申し送り

- 「インストール」節は、公式プラグインリポジトリへの登録と配布 ZIP の作り方が決まってから追記する。
- 「開発環境」「構成」「収録範囲とカタログの更新」の内容は変えない。ただし「開発環境」では、`python3 -m unittest …` のコマンド例を導入文「標準ライブラリだけを使う…」の直後へ移す段落順の整理だけ行う。
- リリースの仕組み（GitHub Release から ZIP を作り plugins.qgis.org へ投稿するワークフロー）は別の設計書で扱う。その際の既知の制約: plugins.qgis.org の新規登録では ZIP 直下のフォルダ名が `^[a-z_][a-z0-9_]*$` に一致する必要があり（公式 `validator.py`）、`ksj-browser` のままでは拒否される。配布パッケージのフォルダ名は `ksj_browser` にする。リポジトリ名・URL・pyproject の名前は `ksj-browser` のままでよい。
- `imgs/processing-download.png` は README から参照されなくなるが、`specs/007-processing/verification.md` の記録として残す。
