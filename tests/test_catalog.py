"""QGISを起動せずにカタログの構造を検証する。"""

import unittest

from ksj import catalog


class CatalogGroupingTests(unittest.TestCase):
    def test_bundled_catalog_has_no_missing_pages_or_resources(self):
        index = catalog.load_index()
        self.assertFalse(index["errors"])
        urls = set()
        ids = set()
        for entry in index["datasets"]:
            self.assertNotIn(entry["id"], ids)
            ids.add(entry["id"])
            data = catalog.load_dataset(entry["id"])
            self.assertEqual(len(data["resources"]), entry["resource_count"])
            self.assertGreater(entry["resource_count"], 0, entry["source_url"])
            self.assertFalse(data.get("issues"))
            resource_urls = [r["url"] for r in data["resources"]]
            self.assertEqual(len(resource_urls), len(set(resource_urls)))
            urls.update(resource_urls)
        self.assertEqual(len(urls), index["resource_count"])

    def test_year_region_and_variants_are_not_overwritten(self):
        records = [
            {"year": "2024年", "region": "全国", "url": "a"},
            {"year": "2025年", "region": "北海道", "url": "b"},
            {"year": "2025年", "region": "北海道", "url": "c"},
        ]
        years = catalog.group_resources(records, "year")
        self.assertEqual(list(years), ["2025年", "2024年"])
        regions = catalog.group_resources(years["2025年"], "region")
        self.assertEqual([r["url"] for r in regions["北海道"]], ["b", "c"])

    def test_missing_region_is_not_invented_as_nationwide(self):
        groups = catalog.group_resources([{"region": "", "url": "a"}], "region")
        self.assertEqual(list(groups), ["地域の指定なし"])

    def test_resource_label_preserves_river_datum_and_format(self):
        resource = {
            "filename": "x.zip",
            "format": "SHP",
            "metadata": {
                "河川": "石狩川",
                "測地系": "世界測地系",
                "ファイル容量": "3MB",
            },
        }
        label = catalog.resource_label(resource)
        for text in ("x.zip", "SHP", "石狩川", "世界測地系", "3MB"):
            self.assertIn(text, label)


if __name__ == "__main__":
    unittest.main()
