"""Tests for scripts/update_dosyasaigai_keikai_kuiki.py (to be expanded)."""

from __future__ import annotations

from pathlib import Path

from scripts.update_dosyasaigai_keikai_kuiki import (
    build_collection_structure,
    extract_table_rows,
    main,
    normalize_region,
)
from urllib.error import URLError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Return fixture text for upcoming parser tests."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_fixture_file_exists():
    """Ensure the base fixture exists before detailed parser tests are added."""
    assert (FIXTURES_DIR / "a33_sample.html").exists()


def test_extract_table_rows_from_fixture():
    html = load_fixture("a33_sample.html")
    rows = extract_table_rows(html)

    assert len(rows) == 3
    assert rows[0]["region_raw"] == "全国"
    assert rows[1]["filename"] == "A33-24_01_SHP.zip"
    assert rows[2]["year_display"].startswith("2023")


def test_build_collection_structure_prefers_shp_and_sorts():
    rows = [
        {"year_display": "2024年", "region_raw": "全国", "filename": "A33-24_00_SHP.zip"},
        {"year_display": "2024年（令和6年）", "region_raw": "北海道", "filename": "A33-24_01_SHP.zip"},
        {"year_display": "2024年", "region_raw": "北海道", "filename": "A33-24_01_GML.zip"},
        {"year_display": "2023年（令和5年）", "region_raw": "青森県", "filename": "A33-23_02_GML.zip"},
    ]

    result = build_collection_structure(rows)

    assert list(result.keys()) == ["2024年", "2023年"]
    assert list(result["2024年"].keys())[:2] == ["全国", "北海道"]
    assert result["2024年"]["北海道"] == "A33-24_01_SHP.zip"
    assert result["2023年"]["青森"] == "A33-23_02_GML.zip"


def test_normalize_region_respects_two_character_names():
    assert normalize_region("京都") == "京都"
    assert normalize_region("京都府") == "京都"


def test_html_file_option_bypasses_network(tmp_path, monkeypatch):
    output = tmp_path / "dosyasaigai.json"
    calls: list[str] = []

    def fake_fetch(url: str) -> str:  # pragma: no cover - failure path
        calls.append(url)
        raise AssertionError("fetch_html should not be called when --html-file is set")

    monkeypatch.setattr(
        "scripts.update_dosyasaigai_keikai_kuiki.fetch_html",
        fake_fetch,
    )

    argv = [
        "--html-file",
        str(FIXTURES_DIR / "a33_sample.html"),
        "--url",
        "https://example.invalid",
        "--output",
        str(output),
    ]

    exit_code = main(argv)
    assert exit_code == 0
    assert output.exists()
    assert not calls


def test_main_returns_exit_code_one_on_network_failure(monkeypatch):
    def fake_fetch(url: str) -> str:
        raise URLError("boom")

    monkeypatch.setattr(
        "scripts.update_dosyasaigai_keikai_kuiki.fetch_html",
        fake_fetch,
    )

    assert main(["--url", "https://example.invalid"]) == 1


def test_main_returns_exit_code_two_on_parse_failure(tmp_path):
    empty_html = tmp_path / "empty.html"
    empty_html.write_text("<html></html>", encoding="utf-8")

    assert (
        main(["--html-file", str(empty_html), "--output", str(tmp_path / "out.json")])
        == 2
    )


def test_main_returns_exit_code_three_on_write_failure(monkeypatch, tmp_path):
    def fake_write(data, output_path):
        raise OSError("read-only")

    monkeypatch.setattr(
        "scripts.update_dosyasaigai_keikai_kuiki.write_collection_json",
        fake_write,
    )

    argv = [
        "--html-file",
        str(FIXTURES_DIR / "a33_sample.html"),
        "--output",
        str(tmp_path / "out.json"),
    ]

    assert main(argv) == 3
