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
