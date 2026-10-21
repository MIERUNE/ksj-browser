#!/usr/bin/env python3
"""国土数値情報の公式一覧・旧版を収集する（Python 3.9、標準ライブラリ）。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from urllib.parse import unquote, urldefrag, urljoin, urlsplit

INDEX_URL = "https://nlftp.mlit.go.jp/ksj/"
INDEXES = {
    "現行形式": INDEX_URL,
    "JPGIS1.0（XML）": urljoin(INDEX_URL, "jpgis/jpgis_datalist.html"),
    "旧統一フォーマット（シェープ・XML）": urljoin(INDEX_URL, "gmlold/index.html"),
    "旧統一フォーマット（TXT・CSV）": urljoin(INDEX_URL, "old/old_datalist.html"),
}
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
DOWNLOAD_SUFFIXES = {".zip", ".lzh", ".csv", ".tif", ".tiff", ".geojson", ".gpkg"}
YEAR_KEYS = {"年", "年度", "データ基準年度", "データ作成年度", "データ基準年"}
REGION_TERMS = ("地域", "都道府県", "メッシュコード", "メッシュ番号")
ERA_START = {"明治": 1867, "大正": 1911, "昭和": 1925, "平成": 1988, "令和": 2018}
FETCH_LOCK = threading.Lock()
CHALLENGE_MARKER = "アクセスの増加を検知しました"


class Element:
    """必要な範囲のHTML木。コメントとスクリプトの文字列はリンクとして解釈しない。"""

    def __init__(self, tag="", attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []
        self.parts = []

    def walk(self, tag=None):
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            yield from child.walk(tag)

    def text(self):
        return re.sub(
            r"\s+",
            " ",
            "".join(
                part.text() if isinstance(part, Element) else part
                for part in self.parts
            ),
        ).strip()

    def ancestor(self, tag):
        node = self.parent
        while node is not None:
            if node.tag == tag:
                return node
            node = node.parent
        return None


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.current = self.root
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        # 公式の旧HTMLには終了タグが省略された表がある。
        if tag in {"td", "th", "tr", "li"}:
            target = {"td", "th"} if tag in {"td", "th"} else {tag}
            node = self.current
            while node.parent is not None:
                if node.tag in target:
                    self.current = node.parent
                    break
                if node.tag in {"table", "ul", "ol"}:
                    break
                node = node.parent
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        self.current.parts.append(element)
        if tag == "br":
            self.current.parts.append(" ")
        if tag not in VOID_TAGS:
            self.current = element

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        if self.current.tag not in {"script", "style"}:
            self.current.parts.append(data)


def absolute_url(base, href):
    return urldefrag(urljoin(base, href.strip()))[0]


def page_id(url):
    path = urlsplit(url).path
    return re.sub(
        r"[^a-zA-Z0-9_-]", "_", path.removeprefix("/ksj/").removesuffix(".html")
    )


def series_key(url):
    """年度だけを取り除く。G04-a/c/d等の別製品は区別する。"""
    return re.sub(r"-(?:19|20)\d{2}(?=\.html$)", "", url)


def product_key(url):
    """年度と仕様バージョン以外の識別子を保持する（A31aとA31b等）。"""
    return re.sub(r"-(?:(?:19|20)\d{2}|v\d+(?:_\d+)*)(?=\.html$)", "", url)


def related_title(title, url, page_count):
    """複数仕様をまとめた旧製品を代表年度の仕様だけで説明しない。"""
    title = re.sub(r"^国土数値情報\s*[|｜]?\s*", "", title).strip()
    if page_count > 1:
        title = re.sub(r"[（(][^）)]*[）)]", "", title)
        title += "（過年度・複数仕様）"
    identifier = Path(urlsplit(product_key(url)).path).stem.replace("KsjTmplt-", "")
    return f"{title or identifier} [{identifier}]"


def parse_index(html, source_url):
    category = "各種統計"
    datasets = []
    seen = set()
    for element in Document(html).root.walk():
        is_category_panel = (
            element.tag == "span"
            and element.parent
            and "card-panel" in element.parent.attrs.get("class", "")
            and "lighten-1" in element.parent.attrs.get("class", "")
        )
        if (
            element.attrs.get("id", "").startswith("collapsible-body__")
            or is_category_panel
        ):
            category = re.sub(
                r"^\d+\.\s*", "", element.text().replace("arrow_drop_down", "")
            ).strip()
        if element.tag != "a" or "KsjTmplt-" not in element.attrs.get("href", ""):
            continue
        parent = element.ancestor("li")
        if parent is None or "collection-item" not in parent.attrs.get("class", ""):
            continue
        url = absolute_url(source_url, element.attrs["href"])
        if url in seen:
            continue
        seen.add(url)
        siblings = list(parent.walk("a"))
        datasets.append(
            {
                "id": page_id(url),
                "title": element.text(),
                "category": category,
                "source_url": url,
                "license": " / ".join(a.text() for a in siblings if a is not element),
            }
        )
    return datasets


def cell_span(cell, attribute):
    match = re.match(r"\s*(\d+)", cell.attrs.get(attribute) or "1")
    return max(1, int(match.group(1))) if match else 1


def table_rows(table):
    """rowspan/colspanを展開し、各セルと列名を対応させる。"""
    pending = {}
    headers = []
    for row in table.walk("tr"):
        if row.ancestor("table") is not table:
            continue
        cells = {}
        for col, (cell, remaining) in list(pending.items()):
            cells[col] = cell
            if remaining > 1:
                pending[col] = (cell, remaining - 1)
            else:
                del pending[col]
        col = 0
        own_cells = [c for c in row.children if c.tag in {"td", "th"}]
        for cell in own_cells:
            while col in cells:
                col += 1
            colspan = cell_span(cell, "colspan")
            rowspan = cell_span(cell, "rowspan")
            for offset in range(colspan):
                cells[col + offset] = cell
                if rowspan > 1:
                    pending[col + offset] = (cell, rowspan - 1)
            col += colspan
        ordered = [cells[k] for k in sorted(cells)]
        if own_cells and all(c.tag == "th" for c in own_cells):
            headers = [re.sub(r"\s*[▲▼△▽]\s*", "", c.text()).strip() for c in ordered]
        yield (
            row,
            {
                headers[i] if i < len(headers) else f"項目{i + 1}": cell.text()
                for i, cell in enumerate(ordered)
                if cell.text() and not any(cell.walk("a"))
            },
        )


def download_urls(element, source_url):
    href = element.attrs.get("href", "")
    candidates = [href] if href else []
    onclick = element.attrs.get("onclick", "")
    if re.search(r"DownL[do]", onclick, re.I):
        quoted = re.findall(r"""['"]([^'"]+)['"]""", onclick)
        # ファイル名引数をURLと誤認しない。パス指定を優先。
        candidates.extend(v for v in quoted if "/" in v)
    return [
        absolute_url(source_url, value)
        for value in candidates
        if Path(urlsplit(value.strip()).path).suffix.lower() in DOWNLOAD_SUFFIXES
    ]


def normalize_year(value):
    match = re.search(r"(?:19|20)\d{2}", value)
    if match:
        return match.group() + "年"
    match = re.search(r"(明治|大正|昭和|平成|令和)(元|\d+)年", value)
    if match:
        number = 1 if match.group(2) == "元" else int(match.group(2))
        return f"{ERA_START[match.group(1)] + number}年"
    return value or "年度記載なし"


def first_value(metadata, match):
    """列名が条件を満たす最初のセル値。該当列がなければ空文字。"""
    return next((value for key, value in metadata.items() if match(key)), "")


def parse_page(html, source_url):
    if CHALLENGE_MARKER in html:
        raise ValueError(f"公開元の画像認証が必要です: {source_url}")
    document = Document(html).root
    metadata_by_row = {}
    for table in document.walk("table"):
        metadata_by_row.update(table_rows(table))
    resources = {}
    links = {}
    for element in document.walk():
        href = element.attrs.get("href", "")
        if "KsjTmplt-" in href and urlsplit(href).path.endswith(".html"):
            url = absolute_url(source_url, href)
            if urlsplit(url).hostname == urlsplit(INDEX_URL).hostname:
                links[url] = element.text()
        for url in download_urls(element, source_url):
            if url in resources:
                continue
            metadata = metadata_by_row.get(element.ancestor("tr"), {})
            filename = unquote(Path(urlsplit(url).path).name)
            resources[url] = {
                "url": url,
                "filename": filename,
                "label": element.text() or filename,
                "year": normalize_year(first_value(metadata, YEAR_KEYS.__contains__)),
                "region": first_value(
                    metadata, lambda key: any(term in key for term in REGION_TERMS)
                ),
                "format": first_value(metadata, lambda key: "形式" in key),
                "metadata": metadata,
                "source_url": source_url,
            }
    published_years = {
        normalize_year(element.attrs.get("value", ""))[:4]
        for element in document.walk("input")
        if element.attrs.get("name") == "year"
    }
    scripts = [
        absolute_url(source_url, element.attrs["src"])
        for element in document.walk("script")
        if re.search(r"/tokei_data\d{4}\.js$", element.attrs.get("src", ""))
        and (
            not published_years
            or re.search(r"(\d{4})\.js$", element.attrs["src"]).group(1)
            in published_years
        )
    ]
    title = next((e.text() for e in document.walk("title")), "")
    return {
        "source_url": source_url,
        "title": title,
        "resources": list(resources.values()),
        "links": links,
        "scripts": scripts,
    }


def parse_script_data(javascript, source_url):
    """公式のJSON配列だけを読む。JavaScriptは実行しない。"""
    match = re.search(r"\b(?:const|let|var)\s+\w+\s*=\s*(\[)", javascript)
    if not match:
        raise ValueError(f"配布一覧のJSON配列がありません: {source_url}")
    rows, _ = json.JSONDecoder().raw_decode(javascript[match.start(1) :])
    resources = []
    for row in rows:
        resources.append(
            {
                "url": absolute_url(source_url, row["dl"]),
                "filename": row["file"],
                "label": row["city"],
                "year": normalize_year(row["year"]),
                "region": row["pref"],
                "municipality": row["city"],
                "format": row["data"],
                "metadata": {
                    "都道府県": row["pref"],
                    "市区町村": row["city"],
                    "市区町村コード": row["citycode"],
                    "年度": row["year"],
                    "形式": row["data"],
                    "測地系": row["CS"],
                    "ファイル容量": row["filecapacity"],
                },
                "source_url": source_url,
            }
        )
    return resources


def fetch_page(url, cache_dir, refresh=False, request_delay=1.0):
    """curlの証明書検証と再試行を使う。HTMLのみ保存し、配布ZIPは取得しない。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".html")
    if refresh or not path.exists():
        # 解析は並行でも、公式サイトへの通信は間隔を空けて直列化する。
        with FETCH_LOCK:
            time.sleep(request_delay)
            result = subprocess.run(
                [
                    "curl",
                    "-L",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--retry",
                    "2",
                    "--max-time",
                    "90",
                    url,
                ],
                capture_output=True,
                check=True,
            )
        raw = result.stdout
        if CHALLENGE_MARKER.encode() in raw:
            raise ValueError(f"公開元の画像認証が必要です: {url}")
        path.write_bytes(raw)
    else:
        raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp932", "euc_jp"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"HTMLの文字コードを判別できません: {url}")


def crawl(cache_dir, workers=2, refresh=False, retry_failed=False, request_delay=1.0):
    datasets = []
    pages = {}
    errors = {}
    for edition, url in INDEXES.items():
        items = parse_index(fetch_page(url, cache_dir, refresh, request_delay), url)
        if not items:
            raise ValueError(f"一覧からデータセットを取得できません: {url}")
        for item in items:
            item["edition"] = edition
        datasets.extend(items)
    pending = {item["source_url"] for item in datasets}

    def fetch(url):
        try:
            html = fetch_page(url, cache_dir, refresh, request_delay)
            if retry_failed and CHALLENGE_MARKER in html:
                html = fetch_page(url, cache_dir, True, request_delay)
            page = parse_page(html, url)
            for script in page["scripts"]:
                rows = parse_script_data(
                    fetch_page(script, cache_dir, refresh, request_delay), url
                )
                page["resources"].extend(rows)
            return url, page, None
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            return url, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while pending:
            batch = sorted(pending)
            pending = set()
            for url, page, error in pool.map(fetch, batch):
                if error:
                    errors[url] = error
                else:
                    pages[url] = page
                    pending.update(page["links"])
                print(
                    f"取得済み {len(pages)} / エラー {len(errors)}: {url}", flush=True
                )
            pending.difference_update(pages)
            pending.difference_update(errors)
    return datasets, pages, errors


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_catalog(destination, datasets, pages, errors, allow_incomplete=False):
    """収集結果をデータセットごとに分割する。失敗結果では既存索引を上書きしない。"""
    if errors and not allow_incomplete:
        raise ValueError(
            f"{len(errors)}ページの取得に失敗しました: {json.dumps(errors, ensure_ascii=False)}"
        )
    pages = dict(pages)
    for url, error in errors.items():
        pages[url] = {"resources": [], "links": {}, "error": error}
    destination.mkdir(parents=True, exist_ok=True)
    index = []

    def emit(item, urls):
        """代表ページ（source_url）の配布ファイルを優先して重複を除き、索引へ追加する。"""
        resources = {}
        for url in sorted(urls, key=lambda u: (u != item["source_url"], u)):
            for resource in pages[url]["resources"]:
                resources.setdefault(resource["url"], resource)
        issues = {url: errors[url] for url in urls if url in errors}
        write_json(
            destination / f"{item['id']}.json",
            {
                **item,
                "pages": sorted(urls),
                "resources": list(resources.values()),
                "issues": issues,
            },
        )
        index.append(
            {
                **item,
                "resource_count": len(resources),
                "page_count": len(urls),
                "issues": issues,
            }
        )

    assigned = set()
    indexed_series = {series_key(item["source_url"]) for item in datasets}
    for item in datasets:
        # 同じデータ識別子の旧版のみ辿る。別データへの参照リンクは混ぜない。
        urls = set()
        pending = {item["source_url"]}
        while pending:
            url = pending.pop()
            if url in urls:
                continue
            urls.add(url)
            pending.update(
                link
                for link in pages[url]["links"]
                if product_key(link) == product_key(item["source_url"])
                and (
                    series_key(link) == series_key(item["source_url"])
                    or series_key(link) not in indexed_series
                )
            )
        assigned.update(urls)
        emit(item, urls)
    # 一覧から直接リンクされない製品は、同じ識別子の過年度をまとめて独立表示。
    related = {}
    for url in sorted(set(pages) - assigned):
        related.setdefault(product_key(url), []).append(url)
    for urls in related.values():
        url = max(
            urls,
            key=lambda value: (
                re.search(r"-(?:19|20)\d{2}(?=\.html$)", value) is not None,
                value,
            ),
        )
        emit(
            {
                "id": page_id(url),
                "title": related_title(pages[url].get("title", ""), url, len(urls)),
                "category": "関連データ・旧版",
                "edition": "関連データ",
                "source_url": url,
                "license": "",
            },
            urls,
        )
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": INDEXES,
        "dataset_count": len(datasets),
        "page_count": len(pages),
        "resource_count": len(
            {r["url"] for p in pages.values() for r in p["resources"]}
        ),
        "datasets": index,
        "errors": errors,
        "pages": {
            url: {
                "resource_count": len(page["resources"]),
                "scripts": page.get("scripts", []),
            }
            for url, page in sorted(pages.items())
            if url not in errors
        },
    }
    write_json(destination / "index.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/ksj-catalog"))
    parser.add_argument("--output", type=Path, default=Path("ksj/catalog"))
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="利用者が画像認証を完了した後、認証画面のキャッシュを再取得する",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="取得失敗を明示した未完了カタログを出力する（通常更新には使用しない）",
    )
    args = parser.parse_args()
    if args.workers < 1 or args.request_delay < 0:
        parser.error("workersは1以上、request-delayは0以上を指定してください")
    datasets, pages, errors = crawl(
        args.cache_dir,
        args.workers,
        args.refresh,
        args.retry_failed,
        args.request_delay,
    )
    manifest = write_catalog(
        args.output, datasets, pages, errors, args.allow_incomplete
    )
    status = f"未完了（{len(errors)}ページ未取得）" if errors else "完了"
    print(
        f"{status}: {manifest['dataset_count']}項目 / {manifest['page_count']}ページ / "
        f"{manifest['resource_count']}配布ファイル"
    )


if __name__ == "__main__":
    main()
