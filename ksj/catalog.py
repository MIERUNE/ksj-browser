"""公式カタログの遅延読み込みと、データ構造に基づく表示用の分類。"""

import json
from pathlib import Path
import re

CATALOG_DIR = Path(__file__).parent / "catalog"
# scripts/update_catalog.py の INDEXES にある現行一覧の表示名。旧形式と階層構造を分ける。
CURRENT_EDITION = "現行形式"
MISSING_LABELS = {"year": "年度記載なし", "region": "地域の指定なし"}


def load_index():
    with (CATALOG_DIR / "index.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    if data.get("schema_version") != 1:
        raise ValueError("対応していないカタログ形式です")
    return data


def load_dataset(dataset_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
        raise ValueError("不正なデータセットIDです")
    with (CATALOG_DIR / f"{dataset_id}.json").open(encoding="utf-8") as stream:
        return json.load(stream)


def group_resources(resources, dimension):
    groups = {}
    for resource in resources:
        label = resource.get(dimension) or MISSING_LABELS.get(dimension, "指定なし")
        groups.setdefault(label, []).append(resource)
    if dimension == "year":

        def order(label):
            match = re.search(r"(?:19|20)\d{2}", label)
            return (-int(match.group()) if match else 0, label)

        return dict(sorted(groups.items(), key=lambda item: order(item[0])))
    return groups


def resource_label(resource):
    parts = [resource["filename"]]
    if resource.get("format"):
        parts.append(resource["format"])
    metadata = resource.get("metadata", {})
    for key, value in metadata.items():
        if any(term in key for term in ("河川", "測地系", "容量", "メッシュ", "種別")):
            if value not in parts:
                parts.append(value)
    return " ｜ ".join(parts)
