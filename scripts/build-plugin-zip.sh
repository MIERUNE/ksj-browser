#!/usr/bin/env bash
set -euo pipefail

# 配布 ZIP を git の追跡ファイルだけから作る。ワークフロー（release.yaml）とローカルで同じ ZIP になる。
# 使い方: scripts/build-plugin-zip.sh <version> [ref] [出力ディレクトリ]
#   version は <major>.<minor>.<patch>（タグ v<version> から v を除いた値）。ZIP の metadata.txt の version になる。
#   ref はコミット・タグ・ブランチ（省略時 HEAD）。作業ツリーの未コミット変更は入らない。
#   出力ディレクトリは省略時 dist/。作った ZIP のパスを標準出力に出す。
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
version="${1:-}"
ref="${2:-HEAD}"
out_dir="${3:-$project_root/dist}"
package="ksj_browser"
placeholder="{{PLUGIN_VERSION}}"

if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "使い方: $0 <major>.<minor>.<patch> [ref] [出力ディレクトリ]（指定された版: '$version'）" >&2
  exit 1
fi

# plugins.qgis.org は ZIP 直下のフォルダ名でプラグインを識別する（新規登録は小文字と下線のみ）。
# 同梱するのはプラグインの実行に要るものと、サイトが必須にする LICENSE だけ。
# metadata.txt も同梱するが、版を書き込んだものを --add-file で別に足す。
# tests/test_plugin_package.py の PATHS（metadata.txt を含む）と同じものが入る。
paths=(ksj __init__.py plugin.py LICENSE)

# リポジトリの metadata.txt は version={{PLUGIN_VERSION}} のまま。ZIP に入れる metadata.txt にだけ版を書き込む。
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT
git -C "$project_root" show "$ref:metadata.txt" > "$work_dir/metadata.src"
if ! grep -qxF "version=$placeholder" "$work_dir/metadata.src"; then
  echo "metadata.txt に version=$placeholder の行がありません: $ref" >&2
  exit 1
fi
sed "s/^version=${placeholder}\$/version=${version}/" "$work_dir/metadata.src" > "$work_dir/metadata.txt"

mkdir -p "$out_dir"
out_dir="$(cd -- "$out_dir" && pwd)"
zip_path="$out_dir/$package-$version.zip"
git -C "$project_root" archive --format=zip --prefix="$package/" --add-file="$work_dir/metadata.txt" -o "$zip_path" "$ref" -- "${paths[@]}"
echo "$zip_path"
