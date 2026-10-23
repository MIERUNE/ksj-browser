#!/usr/bin/env bash
set -euo pipefail

# 呼び出し元のディレクトリに依存せず、CI とローカルで同じテストを実行する。
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
qgis_image="${QGIS_TEST_IMAGE:-qgis/qgis:3.44}"

if [ "$#" -eq 0 ]; then
  set -- -v --cov=ksj --cov=scripts --cov-report=term-missing
fi

# Xvfb の起動通知を受けられるよう --init を使い、QGIS 設定は実行ごとに分離する。
exec docker run --rm --init \
  --platform "${DOCKER_DEFAULT_PLATFORM:-linux/amd64}" \
  --volume "$project_root:/plugin" \
  --tmpfs /plugin/.qgis-settings \
  --workdir /plugin \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env COVERAGE_FILE=/tmp/.coverage \
  "$qgis_image" \
  sh -ec '
    python3 -m venv --system-site-packages /tmp/ksj-test-venv
    /tmp/ksj-test-venv/bin/python -m pip install "pytest>=8" "pytest-qgis>=2.1" pytest-cov
    exec xvfb-run -a -s "+extension GLX -screen 0 1024x768x24" \
      /tmp/ksj-test-venv/bin/python -m pytest "$@"
  ' sh "$@"
