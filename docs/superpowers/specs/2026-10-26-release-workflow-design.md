# リリースの仕組み 設計

日付: 2026-10-26
対象: `.github/workflows/release.yaml`、`scripts/build-plugin-zip.sh`、`tests/test_plugin_package.py`、`README.md`、`AGENTS.md`、`metadata.txt` と `tests/test_metadata.py` のコメント

## 目的

GitHub Release の公開を起点に、配布 ZIP を作って Release に添付し、QGIS 公式プラグインリポジトリ（plugins.qgis.org）へ投稿する仕組みを作る。版はリポジトリ（`metadata.txt`・`pyproject.toml`）を正とし、ワークフローはタグとの一致を検証するだけで書き換えない。参考にした MIERUNE/kumoy-qgis-plugin の `release.yaml` とは、版の扱い（kumoy はタグを `metadata.txt` に書き込む）、ZIP の作り方（kumoy は除外リスト）、投稿の省略条件（kumoy は常に投稿）が異なる。

## 前提となる事実（2026-10-26 の調査）

plugins.qgis.org の現行実装は qgis/QGIS-Plugins-Website（master、2026-10-21 push）。qgis/QGIS-Django は 2025-02 で更新が止まっている。

- 版の追加 API: `POST https://plugins.qgis.org/plugins/api/<package>/version/add/`、ヘッダー `Authorization: Bearer <token>`、multipart の `package` に ZIP。応答は成功で 201 の JSON（`success`、`version`、`approved: false`、`validation_status: "validating"`、`scan_url`）、検証失敗で 400 の JSON（`error`、`errors`）、トークン不正で 403、未登録プラグインで 404。同じ版の再投稿は 400（版はプラグイン内で一意）。
- 任意フィールド `auto_approve_after_scan=true`: トークンを作ったアカウントが trusted（`can_approve` 権限）のときだけ有効で、スキャン通過後に審査なしで公開される。それ以外のアカウントではサーバーが無視する。
- 投稿後の流れ: 自動セキュリティスキャン → 結果のメール → 人の審査（数分〜数日、週末は翌週）→ 公開。初版も 2 版目以降も同じ。
- トークンはプラグインごとに、登録後のプラグインページ（`/plugins/<package>/tokens/`）で作る。登録前には作れない。
- パッケージ検証: ZIP 直下のフォルダ名が `^[A-Za-z][A-Za-z0-9-_]+$`（新規登録は加えて PEP 8 準拠の小文字と下線のみ）、`<package>/metadata.txt`・`<package>/__init__.py`・`<package>/LICENSE` が必須、25 MB 以下、必須 metadata は `name`・`description`・`version`・`qgisMinimumVersion`・`author`・`email`。
- 承認ルール: `repository` は公開リポジトリであること、ライセンスは GPLv2 互換であること、`homepage`・`tracker`・`repository` のリンクが有効であること。更新版には changelog の記載を推奨。
- 本リポジトリの状態: GitHub 上は PRIVATE。`LICENSE` は GPL-2.0（2026-10-25 に GTFS-GO に倣って追加）だが README は「MIT ライセンス」と記載しており不一致。`ksj`・`__init__.py`・`plugin.py`・`metadata.txt`・`LICENSE` だけを `git archive` で固めた試作 ZIP は約 1.7 MB（展開 38 MB、391 ファイル）で、非 ASCII のファイル名はない。
- 既存 CI: `lint.yaml`（Ruff、pyqgis4-checker）と `test.yaml`（Docker で QGIS 3.44・4.0・4.2）。いずれも `permissions: contents: read`。QGIS 3.44 の Docker イメージには git がなく、4.2 のイメージにはある。

## 決定事項

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 版の扱い | `metadata.txt`・`pyproject.toml` を正とし、ワークフローはタグとの一致を検証する | 既存の一致テスト（`tests/test_metadata.py`）が生き、配布 ZIP の内容がリポジトリのコミットと同一になる |
| トリガー | GitHub Release の公開（`release: types: [published]`） | Release ノートを人が書ける。下書きでは起動しない。kumoy と同じ手順 |
| タグ形式 | `v<major>.<minor>.<patch>`（例 `v0.1.0`） | 先頭の `v` を除いて `metadata.txt` の `version` と比較する |
| 配布 ZIP の作り方 | `git archive` に同梱するパスを明示（`ksj`、`__init__.py`、`plugin.py`、`metadata.txt`、`LICENSE`） | 列挙方式なので除外漏れがなく、追跡ファイルだけが入り、同じコミットから同じバイト列ができる |
| パッケージ名（ZIP 直下のフォルダ） | `ksj_browser` | 新規登録の規則（小文字と下線）に従う。リポジトリ名・URL・pyproject の `name` は `ksj-browser` のまま |
| Release の添付名 | `ksj_browser-<version>.zip` | サイトの配布名 `ksj_browser.<version>.zip` と区別でき、複数版を保存しても混ざらない |
| 初回登録 | 同じワークフローで ZIP を作り、トークン未設定なら投稿だけ省略する | トークンは登録後にしか作れない。Release の添付と Web 登録の ZIP が同じバイト列になり、失敗する実行が残らない |
| `auto_approve_after_scan` | `true` を付ける | trusted なアカウントなら審査待ちなしで公開され、そうでなければ無視される。手動審査を必ず通したい場合は外す |
| pre-release | ZIP の作成と添付までで止め、投稿しない | 公開前に ZIP を試す手段になる。タグは正式版と同じ `v<version>` 形式なので、試した後は pre-release とタグを削除してから同じタグで正式な Release を公開する |
| ライセンス表記 | README を GPL-2.0 以降に直す（`LICENSE` が正） | `LICENSE` は意図して追加されたもので、GTFS-GO と QGIS 本体（GPL）に揃う |
| 権限 | `release.yaml` だけ `contents: write` | Release への添付に必要。既存 2 ワークフローの `read` は変えない |
| 投稿後の確認 | API の JSON 応答で判定し、`scan_url` をサマリーに残す | 現行 API は失敗を 400 で返すため `curl --fail-with-body` で検出できる |

## 変更内容

### `.github/workflows/release.yaml`（新規、全文）

```yaml
name: Release plugin

on:
  release:
    types: [published]

# Release に ZIP を添付するため contents: write が要る。lint.yaml・test.yaml の read は変えない。
permissions:
  contents: write

env:
  PACKAGE_NAME: ksj_browser

jobs:
  release:
    name: Build and publish
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      # secrets は if: で直接参照できないため、ジョブの env に写して未設定を判定する。
      QGIS_PLUGIN_TOKEN: ${{ secrets.QGIS_PLUGIN_TOKEN }}
      TAG_NAME: ${{ github.event.release.tag_name }}
    steps:
      - uses: actions/checkout@v7

      - name: タグと metadata.txt の版が一致することを検証
        run: |
          version="${TAG_NAME#v}"
          if ! printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
            echo "::error::タグ $TAG_NAME は v<major>.<minor>.<patch> の形式ではありません"
            exit 1
          fi
          metadata_version="$(sed -n 's/^version=//p' metadata.txt)"
          if [ "$version" != "$metadata_version" ]; then
            echo "::error::タグの版 $version と metadata.txt の version=$metadata_version が一致しません"
            exit 1
          fi
          echo "VERSION=$version" >> "$GITHUB_ENV"
          echo "## リリース $TAG_NAME" >> "$GITHUB_STEP_SUMMARY"
          echo "- 版: $version（metadata.txt と一致）" >> "$GITHUB_STEP_SUMMARY"

      - name: 配布 ZIP を作成
        run: |
          zip_path="$(bash scripts/build-plugin-zip.sh)"
          echo "ZIP_PATH=$zip_path" >> "$GITHUB_ENV"

      - name: ZIP の内容を検査
        run: |
          entries="$(unzip -Z1 "$ZIP_PATH")"
          if printf '%s\n' "$entries" | grep -v "^$PACKAGE_NAME/"; then
            echo "::error::$PACKAGE_NAME/ の外に項目があります"
            exit 1
          fi
          icon="$(sed -n 's/^icon=//p' metadata.txt)"
          for required in metadata.txt __init__.py plugin.py LICENSE "$icon"; do
            if ! printf '%s\n' "$entries" | grep -qx "$PACKAGE_NAME/$required"; then
              echo "::error::$PACKAGE_NAME/$required が ZIP にありません"
              exit 1
            fi
          done
          if printf '%s\n' "$entries" | grep -E '/(tests|specs|docs|imgs|scripts|__pycache__|\.github)/'; then
            echo "::error::配布に含めないディレクトリが ZIP にあります"
            exit 1
          fi
          size="$(wc -c < "$ZIP_PATH" | tr -d ' ')"
          if [ "$size" -ge 25000000 ]; then
            echo "::error::ZIP が plugins.qgis.org の上限 25 MB 以上です（$size バイト）"
            exit 1
          fi
          echo "- ZIP: $(basename "$ZIP_PATH")（$size バイト、$(printf '%s\n' "$entries" | grep -vc '/$') ファイル）" >> "$GITHUB_STEP_SUMMARY"

      - name: Release に添付
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release upload "$TAG_NAME" "$ZIP_PATH" --clobber
          echo "- Release に添付しました" >> "$GITHUB_STEP_SUMMARY"

      - name: plugins.qgis.org に投稿
        if: ${{ env.QGIS_PLUGIN_TOKEN != '' && !github.event.release.prerelease }}
        run: |
          if ! curl --fail-with-body --silent --show-error -X POST \
            "https://plugins.qgis.org/plugins/api/$PACKAGE_NAME/version/add/" \
            -H "Authorization: Bearer $QGIS_PLUGIN_TOKEN" \
            -F "package=@$ZIP_PATH" \
            -F "auto_approve_after_scan=true" \
            -o response.json; then
            echo "::error::plugins.qgis.org への投稿に失敗しました"
            cat response.json
            exit 1
          fi
          scan_url="$(jq -r '.scan_url // empty' response.json)"
          echo "- plugins.qgis.org に投稿しました。スキャン結果: https://plugins.qgis.org$scan_url" >> "$GITHUB_STEP_SUMMARY"

      - name: 投稿の省略を記録
        if: ${{ env.QGIS_PLUGIN_TOKEN == '' || github.event.release.prerelease }}
        run: |
          if [ -z "$QGIS_PLUGIN_TOKEN" ]; then
            echo "- plugins.qgis.org への投稿は省略しました（シークレット QGIS_PLUGIN_TOKEN が未設定）。初回は Release の ZIP を Web から登録してください" >> "$GITHUB_STEP_SUMMARY"
          else
            echo "- plugins.qgis.org への投稿は省略しました（pre-release）" >> "$GITHUB_STEP_SUMMARY"
          fi
```

補足:

- `gh`・`curl`・`jq`・`unzip` は ubuntu-latest に同梱。新しい外部アクションは `actions/checkout@v7` だけで、既存の Dependabot（月次）の対象になる。
- `scan_url` は API がパス（`/plugins/ksj_browser/version/0.1.0/#security-tab`）で返すため、サマリーでは先頭にホストを付ける。
- 失敗は版の検証・ZIP の検査・添付・投稿のどこで止まっても後続を実行しない。投稿で 400 のときは応答の JSON をそのままログに出す。

### `scripts/build-plugin-zip.sh`（新規、全文）

```bash
#!/usr/bin/env bash
set -euo pipefail

# 配布 ZIP を git の追跡ファイルだけから作る。ワークフロー（release.yaml）とローカルで同じ ZIP になる。
# 使い方: scripts/build-plugin-zip.sh [ref] [出力ディレクトリ]
#   ref はコミット・タグ・ブランチ（省略時 HEAD）。作業ツリーの未コミット変更は入らない。
#   出力ディレクトリは省略時 dist/。作った ZIP のパスを標準出力に出す。
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ref="${1:-HEAD}"
out_dir="${2:-$project_root/dist}"
package="ksj_browser"

# plugins.qgis.org は ZIP 直下のフォルダ名でプラグインを識別する（新規登録は小文字と下線のみ）。
# 同梱するのはプラグインの実行に要るものと、サイトが必須にする LICENSE だけ。
paths=(ksj __init__.py plugin.py metadata.txt LICENSE)

version="$(git -C "$project_root" show "$ref:metadata.txt" | sed -n 's/^version=//p')"
if [ -z "$version" ]; then
  echo "metadata.txt の version を読めません: $ref" >&2
  exit 1
fi

mkdir -p "$out_dir"
out_dir="$(cd -- "$out_dir" && pwd)"
zip_path="$out_dir/$package-$version.zip"
git -C "$project_root" archive --format=zip --prefix="$package/" -o "$zip_path" "$ref" -- "${paths[@]}"
echo "$zip_path"
```

列挙したパスが ref に無ければ `git archive` が失敗する。既存の ZIP は上書きする。

### `tests/test_plugin_package.py`（新規）

docstring: 「配布 ZIP が追跡ファイルだけを `ksj_browser/` 配下に含み、plugins.qgis.org の要件を満たすこと。」

- `git` が無い環境（QGIS 3.44 の Docker イメージ）はモジュール全体を `pytest.mark.skipif(shutil.which("git") is None, ...)` で skip する。4.0・4.2 のイメージとホストでは実行する。
- マウントした作業ツリーの所有者がコンテナのユーザーと異なる環境（GitHub Actions 上の Docker など）では git が `dubious ownership` で拒否するため、subprocess には `GIT_CONFIG_COUNT=1`・`GIT_CONFIG_KEY_0=safe.directory`・`GIT_CONFIG_VALUE_0=<リポジトリのパス>` を環境変数で渡す（macOS の Docker Desktop では所有者が一致するため不要だが、同じコードで動く）。
- module スコープの fixture でスクリプトを `bash scripts/build-plugin-zip.sh HEAD <tmp_path>` として 1 回だけ実行し、標準出力のパスを使う。
- 検証:
  - `ZipFile.testzip()` が `None`。
  - ディレクトリ項目を除いた項目の集合が、`git ls-tree -r --name-only HEAD -- ksj __init__.py plugin.py metadata.txt LICENSE` の各行に `ksj_browser/` を付けた集合と完全に一致する（同梱漏れと混入を 1 つの比較で捉える）。
  - ファイル名が `ksj_browser-<version>.zip` で、`<version>` が ZIP 内の `metadata.txt` の `version` と一致する。
  - ZIP 内の `metadata.txt` の `icon` が指すファイルが ZIP 内に存在する。
  - ZIP のサイズが 25,000,000 バイト未満。
- ZIP 内の `metadata.txt` は `configparser` で読む（`tests/test_metadata.py` と同じ）。

### `README.md`

「開発環境」の末尾（「構成」の前）に小節「リリース」を追加する。内容:

1. 版の更新: `metadata.txt` と `pyproject.toml` の `version` を同じ値に上げる PR を作り、マージする。`metadata.txt` の `changelog=` にその版の変更点を書くことを推奨する（承認ルールが更新版に推奨）。
2. Release の公開: GitHub で `v<version>`（例 `v0.1.0`）のタグで Release を公開する。ワークフロー `release.yaml` が、タグと `metadata.txt` の版の一致を検証し、`ksj_browser-<version>.zip` を作って内容を検査し、Release に添付し、シークレット `QGIS_PLUGIN_TOKEN` があれば plugins.qgis.org に投稿する。結果は Actions の実行サマリーに出る。pre-release は添付までで投稿しない。pre-release で ZIP を試した後は、その Release とタグを削除してから同じタグで正式な Release を公開する。
3. 失敗したとき: 版の不一致や ZIP の検査で失敗した場合は Release とタグを削除し、修正 PR のマージ後に作り直す。添付や投稿の一時的な失敗は Actions の Re-run で再実行できる。
4. 初回登録の手順: 「初回登録の手順」の節を参照。
5. ローカルで ZIP を作る: `bash scripts/build-plugin-zip.sh` で `dist/ksj_browser-<version>.zip` ができる。QGIS の「プラグインの管理とインストール」→「ZIP からインストール」で試せる。コミット済みの内容だけが入る。

「ライセンス」の 1 文を次に改める: 「プラグインは GNU General Public License v2 以降（[LICENSE](LICENSE)）です。国土数値情報のデータは各版の使用許諾条件に従ってください。」

利用者向けの「インストール」節は、既決どおり plugins.qgis.org への登録後に別途追加する。

### `AGENTS.md`

「ビルド・テスト・開発コマンド」の CI の説明の後に 1 文を足す: 「リリースは `v<version>` の GitHub Release を公開すると `release.yaml` がタグと `metadata.txt` の版の一致を検証し、`scripts/build-plugin-zip.sh` で配布 ZIP（直下は `ksj_browser/`）を作って Release に添付し、シークレット `QGIS_PLUGIN_TOKEN` があれば plugins.qgis.org に投稿します。」

### `metadata.txt`、`tests/test_metadata.py`

- `metadata.txt` の version 行のコメントを「pyproject.toml の version と揃える。リリース時に両方を手で更新し、タグ v<version> との一致をリリースワークフローが検証する。」にする。
- `tests/test_metadata.py` の `test_version_matches_pyproject` のコメントにも同じ趣旨を足す。

## 運用手順

### 通常のリリース

1. 版の更新 PR（`metadata.txt`・`pyproject.toml`、任意で `changelog=`）をマージする。CI（lint・test）が通った main のコミットから Release を作る。
2. GitHub の Releases で `v<version>` のタグを新規作成して Release を公開する（`gh release create v0.1.0 --generate-notes` でもよい）。
3. 実行サマリーで版・ZIP・投稿結果（`scan_url`）を確認する。
4. plugins.qgis.org からスキャン結果と審査のメールが届く。承認されると公開される。

### 初回登録の手順

1. 前提を整える。リポジトリを公開にする（審査で `repository`・`tracker`・`homepage` の URL が確認される）。README のライセンス表記は本設計で修正済みにする。
2. `v0.1.0` の Release を公開する。ワークフローは検証・ZIP 作成・添付まで行い、投稿は「シークレット未設定のため省略」とサマリーに残して正常終了する。これが版の検証から添付までを本番で通す検証を兼ねる。
3. plugins.qgis.org に OSGeo ID でログインし、「Upload a plugin」から Release の `ksj_browser-0.1.0.zip` を登録する。名前・説明・リンク・アイコンは ZIP 内の `metadata.txt` から取り込まれる。kumoy と同じ MIERUNE のアカウントで登録すると管理が揃う。
4. 自動スキャンの結果がメールで届き、審査を経て公開される。
5. 承認後、プラグインページ `https://plugins.qgis.org/plugins/ksj_browser/` の「Tokens」でトークンを作り、GitHub の Settings → Secrets and variables → Actions に `QGIS_PLUGIN_TOKEN` として登録する。
6. 次の版からは Release の公開だけで投稿まで自動になる。
7. 登録後に README の「インストール」節を追記する（別タスク）。

## エラー処理

| 事象 | ワークフローの挙動 | 対処 |
| --- | --- | --- |
| タグの形式が違う、`metadata.txt` の版と不一致 | ZIP を作らずに失敗 | Release とタグを削除し、版を直す PR のマージ後に作り直す |
| ZIP の検査失敗（必須ファイル欠落、混入、25 MB 以上） | 添付せずに失敗 | 同上。原因を直してから作り直す |
| Release への添付失敗（GitHub 側の一時障害） | 失敗 | Re-run。`--clobber` で上書きするため重複しない |
| 投稿 403 | 失敗 | トークンの失効・無効。トークンを作り直してシークレットを更新し、Re-run |
| 投稿 404 | 失敗 | プラグイン未登録、またはパッケージ名の不一致。サイト側を確認 |
| 投稿 400 | 応答の JSON をログに出して失敗 | 版の重複なら既に受理済みで対応不要。検証失敗は内容を直して次の版で対応 |

Re-run は版の検証から添付までが冪等で、投稿は受理済みなら 400 で止まるため、二重登録にならない。

## 検証

1. `bash scripts/build-plugin-zip.sh` で `dist/ksj_browser-0.1.0.zip` ができ、`unzip -l` の内容が `ksj`・`__init__.py`・`plugin.py`・`metadata.txt`・`LICENSE` だけであること。
2. その ZIP を QGIS-LTR.app の「ZIP からインストール」で入れ、ブラウザパネルの「国土数値情報」と Processing の `ksj` プロバイダが動くこと（ホストの QGIS.app は 3.42 で対象外）。
3. `source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugin_package.py tests/test_metadata.py tests/test_readme_assets.py -q` が通ること。
4. `QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh tests/test_plugin_package.py -q` が通り、`bash scripts/test-docker.sh tests/test_plugin_package.py -q`（3.44）では skip になること。
5. `.venv/bin/ruff check .` と `.venv/bin/ruff format --check .` が通ること。
6. `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest` で `release.yaml` に指摘がないこと。
7. 本番の確認は初回の Release `v0.1.0` で行う（投稿は省略される）。

## 範囲外と申し送り

- README の利用者向け「インストール」節は plugins.qgis.org への登録後に追加する。
- Release ノートから `changelog=` への自動注入、タグの `metadata.txt` への書き込み（kumoy 方式）は採用しない。
- リリース前のテスト実行の強制（main の CI 済みコミットから Release を作る前提）と main のブランチ保護は扱わない。
- trusted 申請（QGIS Developer メーリングリスト）、pre-release を `experimental` 版として投稿する運用は扱わない。
- リポジトリを公開にする操作は利用者が行う。
