# 一時ベクタレイヤーを一時ファイル参照にする

## 目的

ブラウザの「一時レイヤーとして追加」で、ベクタは `QgsVectorLayer.materialize()` によりメモリレイヤーへ複製している。大きなデータでは複製に時間とメモリを使う。ラスタと同じく、取得・展開した一時ファイルをそのまま参照する方式へ揃える。

## 選択した方式

利用者は次を承認した。

- 一時ディレクトリは、そこから生成したレイヤーが**すべて**閉じられた時点で削除する（参照数管理）。ラスタも同じ仕組みへ統一し、現在の「最初のラスタ 1 枚にしか寿命が結び付かない」構造を解消する。
- レイヤーの生成は GUI スレッドで行い、save モードと同じ経路にする。ワーカーでレイヤーを生成して `QgsProcessingContext` で移す案は、配管が残るうえに複製コスト削減という本題に寄与しないため採用しない。
- 削除をレイヤーの `destroyed` ではなく `QgsProject` のシグナルで追跡する案は、プロジェクトへ追加できなかったレイヤーや `clear()` の扱いが増えるため採用しない。

## 動作

### ワーカー（`prepare`）

- 一時モードでは従来どおり `tempfile.TemporaryDirectory(prefix="ksj-layer-")` を作り、その中へ取得・展開する。保存済みデータがあれば通信せず再利用する分岐は維持する。
- 返り値は `{"layers": [(provider, source, title), ...], "temporary": workspace}` のみとする。
- `_materialize`、`QgsProcessingContext`、`QgsFeedback`、`QgsFeatureRequest`、`LayerLoadTask.feedback` と `cancel()` のオーバーライドは削除する。キャンセルは `task.isCanceled` の経路だけで足りる。
- 例外時に一時ディレクトリを削除する処理は維持する。

### GUI（`_finish`）

- save / temporary の区別なく、`provider` に応じて `QgsVectorLayer` か `QgsRasterLayer` を生成し、有効なものだけプロジェクトへ追加する。無効なものは従来どおりまとめて警告する。
- 一時モードでは、追加に成功したレイヤー全部を補助関数 `_release_when_closed(workspace, layers)` へ渡す。残数をクロージャで保持し、各レイヤーの `destroyed` で減らしてゼロになった時点で `workspace.cleanup()` を呼ぶ。1 つも追加できなかった場合は即削除する。
- 早期 return（置き換え済み・取消済み・エラー・結果なし）では `finally` で一時ディレクトリを削除する。寿命をレイヤーへ委ねた後は `workspace = None` にして `finally` の削除を避ける。
- `cleanup()` が `OSError` を出した場合（Windows でのロック残りなど）は `QgsMessageLog` に警告を残して握りつぶし、OS の一時領域掃除に任せる。レイヤー破棄のスロット内では例外を投げない。

### 帰結

- ベクタの一時レイヤーは `providerType() == "ogr"` で、`source()` は一時ディレクトリ内のファイルを指す。GPKG / GML の複数サブレイヤーは 1 つの一時ディレクトリを共有し、最後のレイヤーを閉じたときに削除される。
- 保存済みデータを再利用した場合、レイヤーは保存先フォルダのファイルを参照し、一時ディレクトリは空のまま後で削除される。保存データには触れない。
- プロジェクトを保存して QGIS を再起動すると、一時ファイルは消えているため「利用できないレイヤー」の扱いになる。メモリレイヤーでもデータは残らなかったため、README の注意書きどおりの挙動である。

## 変更箇所

- `ksj/layer_loading.py`: 上記のとおり。`LayerLoadTask` の docstring「取得とメモリ化を…」は「取得を取消可能なタスクで実行する」に改める。
- `ksj/local_storage.py`: 設定ダイアログの説明文を「一時レイヤーは一時ファイルを参照し、レイヤーを閉じると削除します。残す場合は別途保存してください。」に変更する。
- `README.md`: 「一時レイヤーとして追加」の説明を、ベクタ・ラスタとも一時ファイル参照である旨に書き換える。
- `imgs/loading-settings.png`: ダイアログ文言が写っているため古くなる。本作業の範囲外とし、実機での差し替えを依頼する。

## テスト（`tests/test_lazy_loading.py`）

- `providerType() == "memory"` を前提にした 3 箇所（設定変更、ドロップ、複数サブレイヤー）を `"ogr"` に改め、一時モードでは `source()` が保存先フォルダの外を指すことを確認する。
- `test_temporary_materialization_runs_in_worker_and_returns_gui_owned_layer` は前提が消えるため削除し、代わりにベクタ版の「レイヤーを閉じるとファイルが消える」テストを追加する（ラスタ版 `test_temporary_raster_keeps_file_until_layer_is_removed` と対にする）。
- 参照数管理のテストを追加する。GPKG の 2 サブレイヤーを一時モードで追加し、片方を削除してもファイルが残り、もう片方を削除するとディレクトリごと消えることを確認する。
- 取消テストで一時ディレクトリが残らないことを確認する。`tempfile.tempdir` を `tmp_path` へ向ける fixture を用意し、`ksj-layer-*` が残っていないことを見る。
- `tests/test_loading_indicator.py` は `remote_zip.ensure_member` を差し替えているため影響はない。

## 検証

Docker の全テスト（`bash scripts/test-docker.sh`）、Ruff の check / format、pyqgis4-checker の dry run を通す。
