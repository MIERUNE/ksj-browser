"""公式HTMLの分類・配布一覧が欠落しないことを検証する。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_catalog as catalog


class CatalogParserTests(unittest.TestCase):
    def test_related_title_does_not_imply_one_historical_specification(self):
        title = catalog.related_title(
            "国土数値情報 | 洪水浸水想定区域（1次メッシュ単位）データ",
            catalog.INDEX_URL + "gml/datalist/KsjTmplt-A31-2022.html",
            5,
        )
        self.assertIn("洪水浸水想定区域", title)
        self.assertIn("過年度・複数仕様", title)
        self.assertIn("[A31]", title)
        self.assertNotIn("1次メッシュ単位", title)

    def test_trailing_space_in_official_download_url(self):
        html = """<a onclick="DownLd('1MB','a.zip','../data/a.zip ',this)">取得</a>"""
        resources = catalog.parse_page(html, catalog.INDEX_URL)["resources"]
        self.assertEqual(len(resources), 1)
        self.assertTrue(resources[0]["url"].endswith("/data/a.zip"))

    def test_verification_screen_is_not_an_empty_dataset(self):
        with self.assertRaisesRegex(ValueError, "認証"):
            catalog.parse_page(
                "<title>アクセスの増加を検知しました</title>", catalog.INDEX_URL
            )

    def test_dynamic_city_planning_catalog(self):
        javascript = r"""const tokei_data2024=[
        {"pref":"北海道","city":"札幌市","year":"2024年度","data":"GEOJSON形式",
         "file":"A55.zip","dl":"\/ksj\/gml\/data\/A55.zip","citycode":"01100",
         "CS":"世界測地系","filecapacity":"1MB"}];"""
        resources = catalog.parse_script_data(javascript, catalog.INDEX_URL)
        self.assertEqual(resources[0]["url"], catalog.INDEX_URL + "gml/data/A55.zip")
        self.assertEqual(resources[0]["region"], "北海道")
        self.assertEqual(resources[0]["municipality"], "札幌市")
        self.assertEqual(resources[0]["year"], "2024年")

    def test_scripts_only_for_published_years(self):
        html = """
        <input name="year" value="2024年度">
        <!-- <input name="year" value="2023年度"> -->
        <script src="/ksj/js/tokei_data2023.js"></script>
        <script src="/ksj/js/tokei_data2024.js"></script>
        """
        scripts = catalog.parse_page(html, catalog.INDEX_URL)["scripts"]
        self.assertEqual(scripts, [catalog.INDEX_URL + "js/tokei_data2024.js"])

    def test_different_mesh_products_are_not_merged(self):
        a = catalog.INDEX_URL + "gml/datalist/KsjTmplt-L03-a-2021.html"
        b = catalog.INDEX_URL + "gml/datalist/KsjTmplt-L03-b-2021.html"
        old = catalog.INDEX_URL + "gml/datalist/KsjTmplt-L03-a-2016.html"
        datasets = [
            {"id": "a", "source_url": a, "title": "3次メッシュ"},
            {"id": "b", "source_url": b, "title": "細分メッシュ"},
        ]
        pages = {
            a: {"links": {b: "関連", old: "旧版"}, "resources": [{"url": "a.zip"}]},
            b: {"links": {}, "resources": [{"url": "b.zip"}]},
            old: {"links": {}, "resources": [{"url": "old.zip"}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            catalog.write_catalog(Path(directory), datasets, pages, {})
            data = json.loads((Path(directory) / "a.json").read_text())
        self.assertEqual({r["url"] for r in data["resources"]}, {"a.zip", "old.zip"})

    def test_failed_update_preserves_existing_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "index.json").write_text("previous")
            (path / "stale.json").write_text("previous dataset")
            with self.assertRaises(ValueError):
                catalog.write_catalog(path, [], {}, {"page": "failed"})
            self.assertEqual((path / "index.json").read_text(), "previous")
            self.assertEqual((path / "stale.json").read_text(), "previous dataset")

    def test_successful_update_removes_only_obsolete_catalog_files(self):
        url = catalog.INDEX_URL + "gml/datalist/KsjTmplt-X.html"
        related_url = catalog.INDEX_URL + "gml/datalist/KsjTmplt-Y.html"
        datasets = [{"id": "current", "source_url": url, "title": "現行データ"}]
        pages = {
            url: {"links": {}, "resources": [{"url": "current.zip"}]},
            related_url: {"links": {}, "resources": [{"url": "related.zip"}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "stale.json").write_text("obsolete dataset")
            (path / "current.json").write_text("previous version")
            (path / "notes.txt").write_text("keep")
            nested = path / "backup.json"
            nested.mkdir()
            (nested / "stale.json").write_text("keep nested file")

            result = catalog.write_catalog(path, datasets, pages, {})

            self.assertEqual(
                {p.name for p in path.iterdir()},
                {
                    "index.json",
                    "current.json",
                    "gml_datalist_KsjTmplt-Y.json",
                    "notes.txt",
                    "backup.json",
                },
            )
            self.assertEqual(json.loads((path / "index.json").read_text()), result)
            self.assertEqual(
                json.loads((path / "current.json").read_text())["resources"],
                [{"url": "current.zip"}],
            )
            self.assertEqual(
                json.loads((path / "gml_datalist_KsjTmplt-Y.json").read_text())[
                    "resources"
                ],
                [{"url": "related.zip"}],
            )
            self.assertEqual((path / "notes.txt").read_text(), "keep")
            self.assertEqual((nested / "stale.json").read_text(), "keep nested file")

    def test_write_failure_does_not_remove_obsolete_catalog_files(self):
        url = catalog.INDEX_URL + "gml/datalist/KsjTmplt-X.html"
        datasets = [{"id": "current", "source_url": url, "title": "現行データ"}]
        pages = {url: {"links": {}, "resources": [{"url": "current.zip"}]}}
        write_json = catalog.write_json
        for failed_name in ("current.json", "index.json"):
            with (
                self.subTest(failed_name=failed_name),
                tempfile.TemporaryDirectory() as directory,
            ):
                path = Path(directory)
                (path / "stale.json").write_text("previous dataset")

                def fail_write(target, data):
                    if target.name == failed_name:
                        raise OSError("write failed")
                    write_json(target, data)

                with patch.object(catalog, "write_json", side_effect=fail_write):
                    with self.assertRaises(OSError):
                        catalog.write_catalog(path, datasets, pages, {})
                self.assertEqual((path / "stale.json").read_text(), "previous dataset")

    def test_unindexed_history_of_different_product_stays_separate(self):
        base = catalog.INDEX_URL + "gml/datalist/"
        mesh = base + "KsjTmplt-A31b-2025.html"
        old_mesh = base + "KsjTmplt-A31b-v4_0.html"
        river = base + "KsjTmplt-A31a-v4_0.html"
        ambiguous = base + "KsjTmplt-A31-2021.html"
        datasets = [{"id": "mesh", "source_url": mesh, "title": "1次メッシュ"}]
        pages = {
            mesh: {
                "links": {old_mesh: "過年度", river: "旧版", ambiguous: "旧版"},
                "resources": [{"url": "mesh.zip"}],
            },
            old_mesh: {"links": {}, "resources": [{"url": "old-mesh.zip"}]},
            river: {"links": {}, "resources": [{"url": "river.zip"}]},
            ambiguous: {"links": {}, "resources": [{"url": "old.zip"}]},
        }
        with tempfile.TemporaryDirectory() as directory:
            result = catalog.write_catalog(Path(directory), datasets, pages, {})
            data = json.loads((Path(directory) / "mesh.json").read_text())
        self.assertEqual(
            {r["url"] for r in data["resources"]}, {"mesh.zip", "old-mesh.zip"}
        )
        self.assertEqual(len(result["datasets"]), 3)

    def test_sort_controls_in_headers_and_japanese_era(self):
        html = """
        <table><tr><th>地域 ▲ ▼</th><th>年度 ▲ ▼</th><th>取得</th></tr>
        <tr><td>3036</td><td>平成23年</td>
        <td><a href="../data/mesh.zip">取得</a></td></tr></table>
        """
        record = catalog.parse_page(html, catalog.INDEX_URL)["resources"][0]
        self.assertEqual(record["year"], "2011年")
        self.assertEqual(record["region"], "3036")

    def test_legacy_category_without_id(self):
        html = """
        <div class="card-panel blue lighten-1"><span class="white-text">水域</span></div>
        <li class="collection-item"><a href="datalist/old_KsjTmplt-W03.html">水系</a></li>
        """
        self.assertEqual(
            catalog.parse_index(html, catalog.INDEX_URL)[0]["category"], "水域"
        )

    def test_malformed_span_attribute_does_not_drop_downloads(self):
        html = """
        <table><tr><th colspan="3 width=">説明</th></tr></table>
        <a href="../data/L01/test.zip">全国</a>
        """
        self.assertEqual(
            len(catalog.parse_page(html, catalog.INDEX_URL)["resources"]), 1
        )

    def test_index_preserves_categories_and_ignores_comments(self):
        html = """
        <a href="gml/datalist/KsjTmplt-X.html">ランキング</a>
        <span id="collapsible-body__water">水域</span>
        <li class="collection-item"><a href="./gml/datalist/KsjTmplt-W01.html">
        ダム（ポイント）</a><a href="/terms">非商用</a></li>
        <!-- <li class="collection-item"><a href="KsjTmplt-X.html">除外</a></li> -->
        <span id="collapsible-body__transport">交通</span>
        <li class="collection-item"><a href="./gml/datalist/KsjTmplt-N02-2025.html">
        鉄道（ライン）</a></li>
        """
        items = catalog.parse_index(html, catalog.INDEX_URL)
        self.assertEqual([i["category"] for i in items], ["水域", "交通"])
        self.assertEqual(items[0]["title"], "ダム（ポイント）")
        self.assertEqual(items[0]["license"], "非商用")
        self.assertTrue(items[1]["source_url"].endswith("KsjTmplt-N02-2025.html"))

    def test_downloads_keep_rowspan_multiple_formats_and_exact_urls(self):
        html = """
        <table><tr><th>地域</th><th>年度</th><th>形式</th><th>河川</th>
        <th>ファイル名</th><th>ダウンロード</th></tr>
        <tr><td rowspan="2">北海道</td><td rowspan="2">2025年（令和7年）</td>
        <td>SHP</td><td>石狩川</td><td>x.zip</td><td>
        <a onclick="DownLd('3MB','x.zip','../data/special/x.zip',this)">取得</a></td></tr>
        <tr><td>GML</td><td>石狩川</td><td>y.zip</td>
        <td><a href="../data/special/y.zip">取得</a></td></tr></table>
        """
        page = catalog.parse_page(
            html, "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-X.html"
        )
        self.assertEqual(len(page["resources"]), 2)
        first, second = page["resources"]
        self.assertEqual(
            first["url"], "https://nlftp.mlit.go.jp/ksj/gml/data/special/x.zip"
        )
        self.assertEqual(first["year"], "2025年")
        self.assertEqual(second["region"], "北海道")
        self.assertEqual(second["metadata"]["河川"], "石狩川")
        self.assertEqual(second["format"], "GML")

    def test_historical_links_and_unstructured_archives_are_retained(self):
        html = """
        <a href="KsjTmplt-A31-2012.html">過去のデータ</a>
        <a href="/ksj/gml/data/X/national.zip">全国一括</a>
        <a href="/ksj/gml/data/X/national.zip">重複</a>
        <!-- <a href="/ksj/gml/data/X/deleted.zip">削除済み</a> -->
        """
        page = catalog.parse_page(
            html, "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-A31a-2025.html"
        )
        self.assertEqual(len(page["resources"]), 1)
        self.assertEqual(page["resources"][0]["label"], "全国一括")
        self.assertEqual(len(page["links"]), 1)


if __name__ == "__main__":
    unittest.main()
