"""公式カタログの遅延読み込みと、データ構造に基づく表示用の分類。"""

import json
from pathlib import Path
import re

from .catalog_fields import LABEL_TERMS, MISSING_LABELS

CATALOG_DIR = Path(__file__).parent / "catalog"
# scripts/update_catalog.py の INDEXES にある現行一覧の表示名。旧形式と階層構造を分ける。
CURRENT_EDITION = "現行形式"


class CatalogError(Exception):
    """同梱カタログを読めない、または形式が合わないことを表す例外。"""


def _read(path, required_key):
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        raise CatalogError(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get(required_key), list):
        raise CatalogError(f"カタログに {required_key} がありません: {path.name}")
    return data


def load_index():
    data = _read(CATALOG_DIR / "index.json", "datasets")
    if data.get("schema_version") != 1:
        raise CatalogError("対応していないカタログ形式です")
    return data


def load_dataset(dataset_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", dataset_id):
        raise CatalogError("不正なデータセットIDです")
    return _read(CATALOG_DIR / f"{dataset_id}.json", "resources")


def dimension_label(resource, dimension):
    """年度・地域などの値。空なら表示用の欠損ラベルを返す。"""
    return resource.get(dimension) or MISSING_LABELS.get(dimension, "指定なし")


def group_resources(resources, dimension):
    groups = {}
    for resource in resources:
        label = dimension_label(resource, dimension)
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
        if any(term in key for term in LABEL_TERMS):
            if value not in parts:
                parts.append(value)
    return " ｜ ".join(parts)


def mesh_code(resource):
    """同梱カタログの配布単位である1次メッシュ（4桁）を識別する。"""
    code = resource.get("metadata", {}).get("メッシュ番号") or resource.get(
        "region", ""
    )
    if re.fullmatch(r"[0-9]{4}", code) and int(code[2:]) < 80:
        return code
    return None
