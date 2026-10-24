#!/usr/bin/env bash
set -euo pipefail

# 呼び出し元のディレクトリに依存せず、CI とローカルで同じテストを実行する。
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
qgis_image="${QGIS_TEST_IMAGE:-qgis/qgis:3.44}"

if [ "$#" -eq 0 ]; then
  set -- -v --cov=ksj --cov=scripts --cov-report=term-missing --cov-report=xml
fi

# pytest-qgis 5 以降は QGIS 設定を <rootdir>/.qgis-settings に書くため、tmpfs でコンテナ内に閉じ込める
# （Docker が mount point のディレクトリをホスト側に作るので .gitignore にも登録している）。
# pip のキャッシュは名前付きボリュームに残し、2 回目以降の取得を短縮する。
# Xvfb の起動通知を受けられるよう --init を使う。
exec docker run --rm --init \
  --platform "${DOCKER_DEFAULT_PLATFORM:-linux/amd64}" \
  --volume "$project_root:/plugin" \
  --volume ksj-test-pip-cache:/root/.cache/pip \
  --tmpfs /plugin/.qgis-settings \
  --workdir /plugin \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env COVERAGE_FILE=/tmp/.coverage \
  "$qgis_image" \
  sh -ec '
    python3 -m venv --system-site-packages /tmp/ksj-test-venv
    /tmp/ksj-test-venv/bin/python -m pip install -r /plugin/requirements-test.txt
    exec xvfb-run -a -s "+extension GLX -screen 0 1024x768x24" \
      /tmp/ksj-test-venv/bin/python -m pytest -o cache_dir=/tmp/pytest-cache "$@"
  ' sh "$@"
