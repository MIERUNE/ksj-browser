# QGIS 4 対応（Processing 画面の 4.2 互換と移行ガイドの適用）

対象 Issue: [#21 QGIS 4.2 で Processing 画面が開けない](https://github.com/MIERUNE/ksj-browser/issues/21)、[#22 QGIS 4 への移行](https://github.com/MIERUNE/ksj-browser/issues/22)

## 目的と承認済みの動作

QGIS 3.40 から 4.x までの全バージョンで、プラグインが読み込まれ、ブラウザと Processing の両方が動くようにする。設計書は 1 つ、Pull Request は 2 つに分ける。

- PR1（Issue 21）: QGIS 4.2 で Processing のアルゴリズム画面が開き、実行結果のレイヤーが地図に追加される。CI の QGIS 4.2 ジョブを必須チェックに昇格する。
- PR2（Issue 22）: 公式移行ガイド（<https://plugins.qgis.org/docs/migrate-qgis4>）の要件を満たし、公式チェッカー `pyqgis4-checker` の指摘をゼロにして CI で継続的に確認する。

## 調査で確認した事実

- QGIS 4.2 は `processing.gui.AlgorithmDialog.AlgorithmDialog` を `processing.gui.algorithm_widget.AlgorithmWidget` に改名し（qgis/QGIS@7a2aeb08c）、基底を QDialog から QWidget（`QgsProcessingAlgorithmWidgetBase`、ドック可能）に変更した（qgis/QGIS@36575c904）。4.0 までは旧モジュールのみ、4.2 では新モジュールのみが存在する。
- プラグインが使う `mainWidget()`・`createProcessingParameters()`・`finish(successful, result, context, feedback, in_place)`・`close()`・`processing.gui.wrappers.WidgetWrapper` は 4.2 でも存続する。コンストラクタは 3.40 が `(alg, in_place=False, parent=None)`、4.2 が `(alg, in_place=False, parent=None, flags=..., initialState=...)` で、`(alg, parent=parent)` の呼び出しは両方に適合する。
- プラグインは `exec`・`accept`・`reject`・モーダル指定に依存していない。QDialog → QWidget の変更による動作差はない。
- 上流の `GdalAlgorithmWidget`（旧 `GdalAlgorithmDialog`）も同じ形で移行している。QGIS master では C++ 側の基底名がさらに `QgsProcessingAlgorithmWidget` に変わっているが、Python 側の `AlgorithmWidget` は変わっていない。
- QGIS 4.x のプラグイン登録（`src/app/qgspluginregistry.cpp` の `checkQgisVersion`）は、`qgisMaximumVersion` が無いと上限を「最低版のメジャー.99」とみなす。現在の `qgisMinimumVersion=3.40` だけでは上限が 3.99 となり、QGIS 4.0・4.2 はプラグインを非互換と判定して読み込まない。`supportsQt6=True` は 4.0 正式版で無効化されている。Docker テストはこの登録処理を経由しないため検出できていなかった。
- 公式チェッカー `ghcr.io/qgis/pyqgis4-checker:main-ubuntu` の dry-run は 26 箇所（プラグイン本体 15、テスト 11）を指摘し、全て QGIS 側 enum の修飾漏れだった。Qt 側の非互換はない。指摘どおりの修飾付き表記（例 `QgsDataItem.Type.Custom`）は QGIS 3.40 と 4.2 で同一の enum オブジェクトに解決する。
- 検証環境: Docker に `qgis/qgis:3.40`・`3.44`・`4.0-trixie`・`4.2-trixie`、ローカルに QGIS 4.2.2（`/Applications/QGIS-final-4_2_2.app`）。

## 方式の比較

### 旧 `AlgorithmDialog` と新 `AlgorithmWidget` の吸収

- **`processing_widgets.py` 内の import シム（採用、利用者承認済み）**: 新モジュールを先に試し、ImportError なら旧モジュールへ戻り、モジュール変数 `AlgorithmWidgetBase` として公開する。変更は 1 ファイルと 1 テスト。Python 側のクラス名にしか依存しないため、C++ 基底名の再変更の影響を受けない。
- 互換モジュール `ksj/qgis_compat.py` の新設: 将来のシムを集約できるが、現時点で必要なシムは 1 つだけで過剰。
- `Qgis.QGIS_VERSION_INT` によるバージョン分岐: 改名は開発版の途中で入っており境界値が曖昧。ImportError で実在を確認するほうが確実。

### enum 修飾の表記

- **チェッカーの提案形式 `クラス.Enum型.値` に揃える（採用、利用者承認済み）**: 公式ツールを `--dry_run` なしで実行して機械的に書き換え、差分をレビューする。CI で同じツールが指摘ゼロになることで完了を検証できる。
- `Qgis.BrowserItemType.Custom` のような `Qgis` 名前空間の表記: 同じオブジェクトを指すが手作業になり、`Qgis` 側に対応がない enum と表記が混在する。

### CI の追加

- **pyqgis4-checker を Lint ワークフローに追加（採用、利用者承認済み）**: 今回直す 26 箇所の再発を防ぐ。イメージは約 3GB でジョブ時間は数分増える。
- QGIS nightly（`qgis/qgis:latest`）の実験的ジョブ: 次の破壊的変更の早期検知になるが、今回は見送り。
- 追加なし: Issue 21 の 4.2 昇格のみ。

## 実装方針

### PR1: QGIS 4.2 で Processing 画面を開けるようにする（Issue 21）

- `ksj/processing_widgets.py`
  - 固定 import `from processing.gui.AlgorithmDialog import AlgorithmDialog` を次のシムに置き換える。

    ```python
    try:
        # QGIS 4.2 以降は AlgorithmDialog が AlgorithmWidget（QWidget 基底）に改名された。
        from processing.gui.algorithm_widget import AlgorithmWidget as AlgorithmWidgetBase
    except ImportError:
        from processing.gui.AlgorithmDialog import AlgorithmDialog as AlgorithmWidgetBase
    ```

  - `CatalogAlgorithmDialog` を `CatalogAlgorithmWidget(AlgorithmWidgetBase)` に改名する。`__init__(algorithm, parent=None)` と `finish(...)` の処理内容は変えない。
- `ksj/processing_algorithms.py`: `createCustomParametersWidget` の遅延 import 先を `CatalogAlgorithmWidget` にする。
- `tests/test_processing_widgets.py`: `test_gui_load_schedules_layer_for_map` の `from processing.gui.AlgorithmDialog import AlgorithmDialog` を `from ksj.processing_widgets import AlgorithmWidgetBase` に置き換え、その `finish` を差し替える。
- `metadata.txt`: `qgisMinimumVersion=3.40` の次行に `qgisMaximumVersion=4.99` を追加する。QGIS 4.x がプラグインを読み込むために必須。
- `.github/workflows/test.yaml`: マトリクスを `["3.40", "3.44", "4.0-trixie", "4.2-trixie"]` にし、`experimental` フラグ・`include`・`continue-on-error`・ジョブ名の条件式を削除して単純化する。
- README・AGENTS.md: 「QGIS 4.2 は実験的ジョブ」の記述を「3.40・3.44・4.0・4.2 を必須チェック」に改める。

エラー処理: 両方の import に失敗する QGIS は想定外なのでフォールバックは置かず、ImportError をそのまま表面化させる。

### PR2: QGIS 4 移行ガイドの完了（Issue 22）

PR1 のマージ後に main から分岐する。

- `metadata.txt`: `supportsQt6=True` を削除する。
- enum 修飾: 公式チェッカーを `--dry_run` なしでリポジトリに対して実行し、書き換え結果を `ruff format` で整えてレビューする。対象は次の 6 種類、26 箇所。
  - `QgsDataItem.Custom` / `QgsDataItem.Error` → `QgsDataItem.Type.Custom` / `QgsDataItem.Type.Error`
  - `QgsDataItem.Populated` → `QgsDataItem.State.Populated`
  - `QgsDataProvider.Net` → `QgsDataProvider.DataCapability.Net`
  - `QgsProcessingParameterNumber.Integer` → `QgsProcessingParameterNumber.Type.Integer`
  - `QgsProcessingParameterFile.Folder` → `QgsProcessingParameterFile.Behavior.Folder`
  - `QgsAction.GenericPython` → `QgsAction.ActionType.GenericPython`
- `.github/workflows/lint.yaml`: `ghcr.io/qgis/pyqgis4-checker:main-ubuntu` を `container` に使う `qt6-check` ジョブを追加する。手順は公式 README に従い、`pyqt5_to_pyqt6.py --dry_run --logfile pyqt6_checker.log .` でレポートを作り、続けて `pyqt5_to_pyqt6.py .` を実行して終了コードで失敗判定し、失敗時はログを成果物として保存する。2 回目の実行はワークスペース内のファイルを書き換えるが、CI のワークスペースは使い捨てなので問題ない。対象はリポジトリ全体（`ksj`・`scripts`・`tests`・`plugin.py`）。
  - `main-ubuntu` は移動タグ。チェッカーは QGIS の進化に追従するツールのため固定せず追従する。Dependabot の管理対象外である旨を README に記す。
- README・AGENTS.md: 対応バージョンを「QGIS 3.40 以上 4.x まで」と明記し、Lint の説明に Qt6 チェックを加え、ローカルで同じチェックを走らせる次のコマンドを記載する。

  ```sh
  docker run --rm --pull always --user "$(id -u):$(id -g)" --workdir /workspace/ \
    -v "$(pwd):/workspace/" ghcr.io/qgis/pyqgis4-checker:main-ubuntu \
    pyqt5_to_pyqt6.py --dry_run --logfile /workspace/pyqt6_checker.log .
  ```

エラー処理: 該当なし（挙動を変えない表記変更のみ）。

## 範囲と制約

- Python 3.9 以上、QGIS 3.40 以上 4.x まで、Qt は `qgis.PyQt` 経由、追加依存なし。説明は日本語。
- 範囲外: QGIS nightly のカナリアジョブ、互換モジュールの新設、4.2 のドック表示に合わせた画面の再設計、`WidgetWrapper` 以外の API への置き換え。
- クラス名の変更は内部 API のみで、Processing のアルゴリズム ID・パラメータ名・出力は変えない。

## 検証

### PR1

1. `bash scripts/test-docker.sh` を `QGIS_TEST_IMAGE` に `qgis/qgis:3.40`・`3.44`・`4.0-trixie`・`4.2-trixie` を指定して実行し、全件成功すること（4.2 は `tests/test_processing_widgets.py` の 13 件が失敗から成功に変わる）。
2. `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること（CI の Lint ジョブと同じ Ruff）。
3. QGIS 4.2.2 での手動確認（利用者が実施）:
   - `ln -s "$(pwd)" ~/Library/Application\ Support/QGIS/QGIS4/profiles/default/python/plugins/ksj-provider` でリンクし、QGIS 4.2.2 を起動してプラグイン管理から KSJ-Provider を有効化できること。
   - Processing ツールボックスの「国土数値情報（KSJ）」配下 4 アルゴリズム（データセット検索・配布一覧・配布ファイルのダウンロード・レイヤー読み込み）の画面が例外なく開くこと。
   - 配布一覧の画面でデータセットを選ぶと年度・地域の候補が連動して絞り込まれること。
   - レイヤー読み込みを実行すると地図にレイヤーが追加されること。

### PR2

1. 公式チェッカーの dry-run が指摘ゼロになること。
2. PR1 と同じ 4 バージョンの Docker テストと Ruff が通ること。
3. QGIS 4.2.2 で `supportsQt6` 削除後もプラグインが読み込まれ、ブラウザパネルで「国土数値情報」のツリー展開と右クリック項目が表示されること。
