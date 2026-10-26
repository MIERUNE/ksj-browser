# リリースの仕組み 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Release の公開を起点に、配布 ZIP（直下 `ksj_browser/`）を作って Release に添付し、トークンがあれば plugins.qgis.org に投稿するワークフローと、同じ ZIP をローカルで作るスクリプト、そのテストと文書を追加する。

**Architecture:** `scripts/build-plugin-zip.sh` が `git archive` に同梱パスを明示して ZIP を作り、`tests/test_plugin_package.py` がその内容を `git ls-tree` と突き合わせる。`.github/workflows/release.yaml` は Release の published で起動し、タグと `metadata.txt` の版の一致を検証 → スクリプトで ZIP 作成 → 内容検査 → Release に添付 → シークレット `QGIS_PLUGIN_TOKEN` があり pre-release でなければ API に投稿、の順に 1 ジョブで進む。README・AGENTS.md・コメントで手順を記録する。

**Tech Stack:** bash、git archive、GitHub Actions（`actions/checkout@v7`、`gh`、`curl`、`jq`、`unzip`）、pytest（Python 3.9 互換）、ruff

**Spec:** `docs/superpowers/specs/2026-10-26-release-workflow-design.md`

## Global Constraints

- ZIP 直下のフォルダ名（パッケージ名）は `ksj_browser`。リポジトリ名・URL・`pyproject.toml` の `name` は `ksj-browser` のまま。
- 同梱するパスは `ksj`、`__init__.py`、`plugin.py`、`metadata.txt`、`LICENSE` の 5 つだけ。
- ZIP の名前は `ksj_browser-<version>.zip`、サイズは 25,000,000 バイト未満。
- タグは `v<major>.<minor>.<patch>`。ワークフローは先頭の `v` を除いて `metadata.txt` の `version=` と一致することを検証し、`metadata.txt` を書き換えない。
- `release.yaml` だけ `permissions: contents: write`。`lint.yaml`・`test.yaml` は変えない。
- 投稿 API は `POST https://plugins.qgis.org/plugins/api/ksj_browser/version/add/`、`Authorization: Bearer`、multipart の `package`、`auto_approve_after_scan=true`。
- テストは Python 3.9 で動くこと（`tomllib` 不可、`tests/test_metadata.py` と同じ `configparser` で metadata を読む）。
- コメント・文書・コミットメッセージは日本語。コミットは Conventional Commits（`feat:`・`ci:`・`test:`・`docs:` など小文字）。
- コミットメッセージの末尾に次の 2 行を付ける。
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
  ```
- `uv run` は `uv.lock` を書き換えるので使わない。`.venv/bin/ruff`、`.venv/bin/python -m pytest` を使う。pytest は `source setup_qgis_env.sh` の後に `QT_QPA_PLATFORM=offscreen` を付けて実行する。
- 作業ブランチは `ci/release-workflow`（main から分岐、設計書を 21e9bf7 で commit 済み）。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `scripts/build-plugin-zip.sh`（新規） | `git archive` で `dist/ksj_browser-<version>.zip` を作る。ワークフローとローカルの共通入口 |
| `tests/test_plugin_package.py`（新規） | ZIP の内容が HEAD の追跡ファイルと一致し、サイトの要件を満たすことを検証 |
| `.github/workflows/release.yaml`（新規） | Release の published で検証・ZIP 作成・検査・添付・投稿 |
| `README.md`（修正） | 「開発環境」に「リリース」小節と「初回登録の手順」、「ライセンス」の修正 |
| `AGENTS.md`（修正） | 「ビルド・テスト・開発コマンド」にリリースの 1 文 |
| `metadata.txt`、`tests/test_metadata.py`（修正） | version のコメントにタグ検証の記述 |

---

### Task 1: 配布 ZIP を作るスクリプトとテスト

**Files:**
- Create: `scripts/build-plugin-zip.sh`
- Test: `tests/test_plugin_package.py`

**Interfaces:**
- Consumes: なし
- Produces: `bash scripts/build-plugin-zip.sh [ref] [出力ディレクトリ]`。`ref` 省略時 `HEAD`、出力ディレクトリ省略時 `dist/`。作った ZIP の絶対パスを標準出力に 1 行出す。終了コードは成功 0、`metadata.txt` の version が読めないとき 1、`git archive` 失敗時はその終了コード。Task 2 のワークフローがこの契約で呼ぶ。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_plugin_package.py` を次の内容で作る。

```python
"""配布 ZIP が追跡ファイルだけを ksj_browser/ 配下に含み、plugins.qgis.org の要件を満たすこと。"""

import configparser
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build-plugin-zip.sh"
# plugins.qgis.org は ZIP 直下のフォルダ名でプラグインを識別する。
PACKAGE = "ksj_browser"
# scripts/build-plugin-zip.sh の paths と同じ。同梱するパスを変えるときは両方を直す。
PATHS = ["ksj", "__init__.py", "plugin.py", "metadata.txt", "LICENSE"]
# plugins.qgis.org の上限（validator.py の PLUGIN_MAX_UPLOAD_SIZE）。
MAX_SIZE = 25_000_000

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git がない環境（QGIS 3.44 の Docker イメージなど）では配布 ZIP を作れない",
)


def git_env():
    """CI の Docker ではマウントした作業ツリーの所有者が違い、git が dubious ownership で拒否する。"""
    return {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": os.fspath(ROOT),
    }


@pytest.fixture(scope="module")
def package_zip(tmp_path_factory):
    """スクリプトを 1 回だけ実行し、作られた ZIP のパスを返す。"""
    out_dir = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        ["bash", os.fspath(SCRIPT), "HEAD", os.fspath(out_dir)],
        check=True,
        capture_output=True,
        text=True,
        env=git_env(),
    )
    return Path(result.stdout.strip())


def tracked_files():
    """HEAD で追跡している同梱対象のパスに、ZIP 直下のフォルダ名を付けた集合。"""
    output = subprocess.run(
        ["git", "-C", os.fspath(ROOT), "ls-tree", "-r", "--name-only", "HEAD", "--"]
        + PATHS,
        check=True,
        capture_output=True,
        text=True,
        env=git_env(),
    ).stdout
    return {f"{PACKAGE}/{line}" for line in output.splitlines()}


def zip_metadata(archive):
    parser = configparser.ConfigParser()
    parser.read_string(archive.read(f"{PACKAGE}/metadata.txt").decode("utf-8"))
    return parser["general"]


def test_zip_contains_exactly_the_tracked_files(package_zip):
    # 同梱漏れと混入（tests/、__pycache__/ など）を 1 つの比較で捉える。
    with zipfile.ZipFile(package_zip) as archive:
        assert archive.testzip() is None
        names = {name for name in archive.namelist() if not name.endswith("/")}
    assert names == tracked_files()


def test_zip_name_matches_metadata_version(package_zip):
    with zipfile.ZipFile(package_zip) as archive:
        version = zip_metadata(archive)["version"]
    assert package_zip.name == f"{PACKAGE}-{version}.zip"


def test_icon_is_included(package_zip):
    # icon はプラグインディレクトリからの相対パス。
    with zipfile.ZipFile(package_zip) as archive:
        icon = zip_metadata(archive)["icon"]
        assert f"{PACKAGE}/{icon}" in archive.namelist()


def test_zip_is_under_site_limit(package_zip):
    assert package_zip.stat().st_size < MAX_SIZE
```

- [ ] **Step 2: テストが失敗することを確認する**

Run:
```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugin_package.py -q
```
Expected: 4 件が ERROR。fixture `package_zip` で `subprocess.CalledProcessError` が出て、`returned non-zero exit status 127`（`bash: scripts/build-plugin-zip.sh: No such file or directory`）と表示される。

- [ ] **Step 3: スクリプトを書く**

`scripts/build-plugin-zip.sh` を次の内容で作り、`chmod +x scripts/build-plugin-zip.sh` を実行する。

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
# tests/test_plugin_package.py の PATHS と同じにする。
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

- [ ] **Step 4: テストが通ることを確認する**

Run:
```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_plugin_package.py -v
```
Expected: 4 passed。

- [ ] **Step 5: スクリプト単体の動作を確認する**

Run:
```bash
bash scripts/build-plugin-zip.sh && unzip -Z1 dist/ksj_browser-0.1.0.zip | grep -v '^ksj_browser/ksj/catalog/' && ls -l dist/ksj_browser-0.1.0.zip
```
Expected: 標準出力の 1 行目が `.../dist/ksj_browser-0.1.0.zip`。一覧は `ksj_browser/`、`ksj_browser/LICENSE`、`ksj_browser/__init__.py`、`ksj_browser/ksj/`、`ksj_browser/ksj/__init__.py`、`ksj_browser/ksj/*.py`、`ksj_browser/ksj/icons/`、`ksj_browser/ksj/icons/*.png`、`ksj_browser/metadata.txt`、`ksj_browser/plugin.py` だけ（`tests/`・`specs/`・`__pycache__/` がない）。サイズは約 1.7 MB。

存在しない ref での失敗も確認する。
```bash
bash scripts/build-plugin-zip.sh no-such-ref; echo "exit=$?"
```
Expected: `fatal: ...` または「metadata.txt の version を読めません」が標準エラーに出て、`exit=` が 0 以外。

- [ ] **Step 6: lint を通す**

Run:
```bash
.venv/bin/ruff format tests/test_plugin_package.py && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```
Expected: `All checks passed!` と `N files already formatted`。`ruff format` が整形を変えた場合はその結果を採用する。

- [ ] **Step 7: コミット**

```bash
git add scripts/build-plugin-zip.sh tests/test_plugin_package.py
git commit -m "$(cat <<'EOF'
feat: 配布 ZIP を git archive で作るスクリプトとテストを追加

ksj・__init__.py・plugin.py・metadata.txt・LICENSE だけを ksj_browser/ 直下に固め、
dist/ksj_browser-<version>.zip に出力する。テストは ZIP の内容が HEAD の追跡ファイルと
一致すること、名前と version の一致、icon の同梱、25 MB 未満を検証する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
)"
```

---

### Task 2: リリースワークフロー

**Files:**
- Create: `.github/workflows/release.yaml`

**Interfaces:**
- Consumes: Task 1 の `bash scripts/build-plugin-zip.sh`（引数なし → HEAD、`dist/`、標準出力に ZIP のパス）。
- Produces: Release の published で起動するワークフロー `Release plugin`。リポジトリの Secrets に `QGIS_PLUGIN_TOKEN` があれば投稿する。Task 3 の README がこのファイル名と挙動を説明する。

- [ ] **Step 1: ワークフローを書く**

`.github/workflows/release.yaml` を次の内容で作る（設計書の全文と同じ）。ZIP のサイズは macOS でもローカルで同じ手順を試せるよう `wc -c` で取る。

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
          if ! grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' <<< "$version"; then
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
          echo "- 版: ${version}（metadata.txt と一致）" >> "$GITHUB_STEP_SUMMARY"

      - name: 配布 ZIP を作成
        run: |
          zip_path="$(bash scripts/build-plugin-zip.sh)"
          echo "ZIP_PATH=$zip_path" >> "$GITHUB_ENV"

      - name: ZIP の内容を検査
        run: |
          entries="$(unzip -Z1 "$ZIP_PATH")"
          if grep -v "^$PACKAGE_NAME/" <<< "$entries"; then
            echo "::error::$PACKAGE_NAME/ の外に項目があります"
            exit 1
          fi
          icon="$(sed -n 's/^icon=//p' metadata.txt)"
          for required in metadata.txt __init__.py plugin.py LICENSE "$icon"; do
            if ! grep -qx "$PACKAGE_NAME/$required" <<< "$entries"; then
              echo "::error::$PACKAGE_NAME/$required が ZIP にありません"
              exit 1
            fi
          done
          if grep -E '/(tests|specs|docs|imgs|scripts|__pycache__|\.github)/' <<< "$entries"; then
            echo "::error::配布に含めないディレクトリが ZIP にあります"
            exit 1
          fi
          size="$(wc -c < "$ZIP_PATH" | tr -d ' ')"
          if [ "$size" -ge 25000000 ]; then
            echo "::error::ZIP が plugins.qgis.org の上限 25 MB 以上です（$size バイト）"
            exit 1
          fi
          echo "- ZIP: $(basename "$ZIP_PATH")（$size バイト、$(grep -vc '/$' <<< "$entries") ファイル）" >> "$GITHUB_STEP_SUMMARY"

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

- [ ] **Step 2: actionlint で静的検査する**

Run:
```bash
docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest -color
```
Expected: 出力なしで終了コード 0（既存の `lint.yaml`・`test.yaml` も検査対象になる）。shellcheck の指摘が出た場合は、引用符の付け忘れなど指摘どおりに直す。`unzip`・`jq`・`gh` が見つからない旨の指摘は出ない（actionlint はコマンドの存在を検査しない）。

- [ ] **Step 3: 検証・ZIP 作成・検査の 3 ステップをローカルで通す**

ワークフローの `run:` を名前で取り出し、GitHub Actions の既定シェル（`bash -eo pipefail`）と同じ環境変数で順に実行する。`dist/` に ZIP ができる。

```bash
.venv/bin/python - <<'EOF'
import os
import subprocess
import tempfile

import yaml

with open(".github/workflows/release.yaml", encoding="utf-8") as f:
    workflow = yaml.safe_load(f)
steps = {s["name"]: s["run"] for s in workflow["jobs"]["release"]["steps"] if "name" in s}
env = {
    **os.environ,
    "PACKAGE_NAME": workflow["env"]["PACKAGE_NAME"],
    "TAG_NAME": "v0.1.0",
    "GITHUB_ENV": tempfile.NamedTemporaryFile(delete=False).name,
    "GITHUB_STEP_SUMMARY": tempfile.NamedTemporaryFile(delete=False).name,
}
for name in ["タグと metadata.txt の版が一致することを検証", "配布 ZIP を作成", "ZIP の内容を検査"]:
    subprocess.run(["bash", "-eo", "pipefail", "-c", steps[name]], check=True, env=env)
    with open(env["GITHUB_ENV"], encoding="utf-8") as f:
        for line in f:
            key, _, value = line.rstrip("\n").partition("=")
            env[key] = value
with open(env["GITHUB_STEP_SUMMARY"], encoding="utf-8") as f:
    print(f.read())
EOF
```
Expected: 例外なく終わり、最後に次が表示される（バイト数とファイル数は目安）。
```
## リリース v0.1.0
- 版: 0.1.0（metadata.txt と一致）
- ZIP: ksj_browser-0.1.0.zip（1736717 バイト、387 ファイル）
```

- [ ] **Step 4: 版の不一致で止まることを確認する**

Run:
```bash
.venv/bin/python - <<'EOF'
import os
import subprocess
import tempfile

import yaml

with open(".github/workflows/release.yaml", encoding="utf-8") as f:
    workflow = yaml.safe_load(f)
steps = {s["name"]: s["run"] for s in workflow["jobs"]["release"]["steps"] if "name" in s}
env = {
    **os.environ,
    "GITHUB_ENV": tempfile.NamedTemporaryFile(delete=False).name,
    "GITHUB_STEP_SUMMARY": tempfile.NamedTemporaryFile(delete=False).name,
}
for tag in ["v9.9.9", "0.1.0", "v0.1"]:
    result = subprocess.run(
        ["bash", "-eo", "pipefail", "-c", steps["タグと metadata.txt の版が一致することを検証"]],
        env={**env, "TAG_NAME": tag},
        capture_output=True,
        text=True,
    )
    print(tag, "exit", result.returncode, result.stdout.strip())
EOF
```
Expected:
```
v9.9.9 exit 1 ::error::タグの版 9.9.9 と metadata.txt の version=0.1.0 が一致しません
0.1.0 exit 0 
v0.1 exit 1 ::error::タグ v0.1 は v<major>.<minor>.<patch> の形式ではありません
```
`0.1.0`（`v` なし）は `${TAG_NAME#v}` が何も除かず一致するため通る。これは設計どおり（`v` の有無は運用手順で `v` 付きに統一する）。

- [ ] **Step 5: コミット**

```bash
git add .github/workflows/release.yaml
git commit -m "$(cat <<'EOF'
ci: Release の公開で配布 ZIP を作り plugins.qgis.org に投稿するワークフローを追加

タグと metadata.txt の版の一致を検証し、scripts/build-plugin-zip.sh で ZIP を作って
内容を検査し、Release に添付する。シークレット QGIS_PLUGIN_TOKEN があり pre-release
でなければ plugins.qgis.org の API に投稿し、結果を実行サマリーに記録する。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
)"
```

---

### Task 3: 文書とコメント

**Files:**
- Modify: `README.md`（`## 構成` の直前に小節を追加、`## ライセンス` の本文 1 行）
- Modify: `AGENTS.md:7`（「ビルド・テスト・開発コマンド」の段落）
- Modify: `metadata.txt:11`（version 行のコメント）
- Modify: `tests/test_metadata.py:31`（`test_version_matches_pyproject` のコメント）
- Test: `tests/test_readme_assets.py`、`tests/test_metadata.py`（既存。変更後も通ること）

**Interfaces:**
- Consumes: Task 1 の `scripts/build-plugin-zip.sh`、Task 2 の `.github/workflows/release.yaml`（README から相対リンクで参照するため、両方が存在していること）。
- Produces: なし。

- [ ] **Step 1: README に「リリース」小節を追加する**

`README.md` の `## 構成` の見出し（直前は「macOS で QGIS 付属 Python を…証明書検証を無効化する必要はありません。」の段落）の前に、次を挿入する。Edit の `old_string` は `## 構成\n\n| パス`、`new_string` はその前に以下を足したもの。

````markdown
### リリース

配布 ZIP の作成と QGIS 公式プラグインリポジトリ（[plugins.qgis.org](https://plugins.qgis.org/)）への投稿は、GitHub Release の公開を起点に [`release.yaml`](.github/workflows/release.yaml) が行います。

1. **版の更新**: [`metadata.txt`](metadata.txt) と [`pyproject.toml`](pyproject.toml) の `version` を同じ値に上げる PR を作り、マージします。`metadata.txt` の `changelog=` にその版の変更点を書くことを推奨します（公式リポジトリの承認ルールが更新版に推奨しています）。
2. **Release の公開**: GitHub の Releases で `v<version>`（例 `v0.1.0`）のタグを新規作成して Release を公開します。ワークフローは、タグと `metadata.txt` の版の一致を検証し、`ksj_browser-<version>.zip` を作って内容（直下が `ksj_browser/`、必須ファイル、25 MB 未満）を検査し、Release に添付し、シークレット `QGIS_PLUGIN_TOKEN` があれば plugins.qgis.org に投稿します。結果は Actions の実行サマリーに出ます。投稿後は自動セキュリティスキャンと審査を経て公開されます。
3. **pre-release**: ZIP の作成と添付までで止め、投稿しません。試した後は、その Release とタグを削除してから同じタグで正式な Release を公開します。
4. **失敗したとき**: 版の不一致や ZIP の検査で失敗した場合は Release とタグを削除し、修正 PR のマージ後に作り直します。添付や投稿の一時的な失敗は Actions の Re-run で再実行できます。投稿が 403 ならトークンを作り直してシークレットを更新し、400 なら応答の JSON（版の重複など）を確認します。

ローカルで同じ ZIP を作るには次を実行します。`dist/ksj_browser-<version>.zip` ができ、QGIS の「プラグインの管理とインストール」→「ZIP からインストール」で試せます。コミット済みの内容だけが入ります。

```bash
bash scripts/build-plugin-zip.sh
```

#### 初回登録の手順

1. リポジトリを公開にします（審査で `repository`・`tracker`・`homepage` の URL が確認されます）。
2. `v0.1.0` の Release を公開します。ワークフローは検証・ZIP 作成・添付まで行い、投稿は「シークレット未設定のため省略」とサマリーに残して正常終了します。
3. plugins.qgis.org に OSGeo ID でログインし、「Upload a plugin」から Release の `ksj_browser-0.1.0.zip` を登録します。名前・説明・リンク・アイコンは ZIP 内の `metadata.txt` から取り込まれます。
4. 自動スキャンの結果がメールで届き、審査（数分〜数日）を経て公開されます。
5. 承認後、プラグインページ（`https://plugins.qgis.org/plugins/ksj_browser/`）の「Tokens」でトークンを作り、GitHub の Settings → Secrets and variables → Actions に `QGIS_PLUGIN_TOKEN` として登録します。
6. 次の版からは Release の公開だけで投稿まで自動になります。

````

- [ ] **Step 2: README のライセンスを直す**

`## ライセンス` の本文を次に置き換える。

変更前:
```
プラグインは MIT ライセンスです。国土数値情報のデータは各版の使用許諾条件に従ってください。
```
変更後:
```
プラグインは GNU General Public License v2 以降（[LICENSE](LICENSE)）です。国土数値情報のデータは各版の使用許諾条件に従ってください。
```

- [ ] **Step 3: AGENTS.md に 1 文足す**

`AGENTS.md` の「ビルド・テスト・開発コマンド」の段落で、「GitHub Actions は同じスクリプトで QGIS 3.44・4.0・4.2 を確認します。」の直後に次を挿入する（同じ段落内、改行しない）。

```
リリースは `v<version>` の GitHub Release を公開すると `release.yaml` がタグと `metadata.txt` の版の一致を検証し、`scripts/build-plugin-zip.sh` で配布 ZIP（直下は `ksj_browser/`）を作って Release に添付し、シークレット `QGIS_PLUGIN_TOKEN` があれば plugins.qgis.org に投稿します。
```

- [ ] **Step 4: metadata.txt と test_metadata.py のコメントを直す**

`metadata.txt` の 11 行目:

変更前:
```
# pyproject.toml の version と揃える。リリース時に両方を手で更新する。
```
変更後:
```
# pyproject.toml の version と揃える。リリース時に両方を手で更新し、タグ v<version> との一致をリリースワークフローが検証する。
```

`tests/test_metadata.py` の `test_version_matches_pyproject` 冒頭のコメント:

変更前:
```python
    # リリース時は metadata.txt と pyproject.toml の両方を手で更新する。
```
変更後:
```python
    # リリース時は metadata.txt と pyproject.toml の両方を手で更新する。
    # タグ v<version> との一致は .github/workflows/release.yaml が検証する。
```

- [ ] **Step 5: テストと lint を通す**

Run:
```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_readme_assets.py tests/test_metadata.py tests/test_plugin_package.py -q && .venv/bin/ruff check . && .venv/bin/ruff format --check .
```
Expected: すべて passed（README の相対リンク `.github/workflows/release.yaml`・`metadata.txt`・`pyproject.toml`・`LICENSE` が解決すること）、`All checks passed!`。

- [ ] **Step 6: コミット**

```bash
git add README.md AGENTS.md metadata.txt tests/test_metadata.py
git commit -m "$(cat <<'EOF'
docs: リリース手順と初回登録の手順を README に書き、ライセンス表記を LICENSE に合わせる

AGENTS.md にリリースの仕組みの 1 文を足し、metadata.txt と test_metadata.py の
コメントにタグとの一致検証を記す。README の「MIT ライセンス」は LICENSE（GPL-2.0）と
食い違っていたため GPL v2 以降に直す。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SRJgpJFmJdYJ2mrXw2HU5f
EOF
)"
```

---

### Task 4: 全体の検証

**Files:**
- なし（検証のみ）

**Interfaces:**
- Consumes: Task 1〜3 の成果物すべて。
- Produces: 検証結果の記録（PR 本文に転記する）。

- [ ] **Step 1: Docker（QGIS 3.44）で skip になることを確認する**

Run:
```bash
bash scripts/test-docker.sh tests/test_plugin_package.py -q -rs
```
Expected: `4 skipped` と理由「git がない環境（QGIS 3.44 の Docker イメージなど）では配布 ZIP を作れない」。

- [ ] **Step 2: Docker（QGIS 4.2）で通ることを確認する**

Run:
```bash
QGIS_TEST_IMAGE=qgis/qgis:4.2-trixie bash scripts/test-docker.sh tests/test_plugin_package.py tests/test_metadata.py tests/test_readme_assets.py -q
```
Expected: すべて passed（4.2 のイメージには git 2.47 がある）。`dubious ownership` が出た場合は `git_env()` の環境変数が subprocess に渡っていない。

- [ ] **Step 3: ホストで全テストを実行する**

Run:
```bash
source setup_qgis_env.sh && QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```
Expected: 失敗 0。既存テストに影響する変更はないので、失敗があれば原因を調べて報告する（直す前に報告）。

- [ ] **Step 4: 配布 ZIP の展開先から QGIS 3.44（QGIS-LTR.app）の Python でインポートできることを確認する**

QGIS の「ZIP からインストール」と同じく、ZIP を展開した `ksj_browser/` をパッケージとして読み込む。`/Applications/QGIS-LTR.app`（3.44）の Python を直接使う。

```bash
tmp="$(mktemp -d)" && unzip -q dist/ksj_browser-0.1.0.zip -d "$tmp" && \
QT_QPA_PLATFORM=offscreen \
PYTHONHOME=/Applications/QGIS-LTR.app/Contents/Frameworks \
PYTHONPATH="$tmp:/Applications/QGIS-LTR.app/Contents/Resources/qgis/python:/Applications/QGIS-LTR.app/Contents/Resources/qgis/python/plugins" \
PROJ_LIB=/Applications/QGIS-LTR.app/Contents/Resources/qgis/proj \
GDAL_DATA=/Applications/QGIS-LTR.app/Contents/Resources/qgis/gdal \
/Applications/QGIS-LTR.app/Contents/MacOS/python3.12 -c "import ksj_browser.plugin as plugin; print(plugin.PLUGIN_NAME, plugin.Plugin)"
```
Expected: `国土数値情報ブラウザ <class 'ksj_browser.plugin.Plugin'>`。失敗した場合は、原因が ZIP の内容（ファイル欠落）か実行環境（Python のパスや環境変数）かを切り分けて報告する。プラグイン本体は変更しない。

- [ ] **Step 5: QGIS の GUI で ZIP からインストールする（利用者が実施）**

利用者への案内（エージェントは実施しない）:

1. QGIS-LTR.app（3.44）を起動し、「プラグイン」→「プラグインの管理とインストール」→「ZIP からインストール」で `dist/ksj_browser-0.1.0.zip` を選ぶ。
2. 既存の開発用プラグイン（`python/plugins/ksj-provider` または `ksj-browser` のシンボリックリンク）が有効なら、重複を避けるため先に無効化する。
3. ブラウザパネルに「国土数値情報」が出て、分類を展開できること。Processing ツールボックスに `ksj` プロバイダが出ること。
4. 確認後は「国土数値情報ブラウザ」をアンインストールし、開発用プラグインを有効に戻す。

- [ ] **Step 6: 作業ツリーが clean であることを確認する**

Run:
```bash
git status --short && git log --oneline main..HEAD
```
Expected: 変更なし。コミットは設計書・Task 1・Task 2・Task 3 の 4 件。

---

## 完了後

- superpowers:finishing-a-development-branch に従い、PR を作るかを利用者に確認する。PR 本文には影響範囲、Task 4 の検証結果（コマンドと結果）、設計書へのリンクを書く。
- 初回登録（リポジトリの公開、`v0.1.0` の Release、Web からの登録、トークンの設定）は利用者の操作。README の「初回登録の手順」を案内する。
