from pathlib import Path

import pytest

from backend.shopify_admin import Variant
from scripts.upload_to_shopify import (
    MatchResult,
    find_ambiguous_variants,
    match_files_to_variants,
    normalize_name,
    print_preview,
    read_shopify_credentials,
    resolve_material_type,
)


def test_normalize_name_strips_and_casefolds():
    assert normalize_name("  Bisque ") == normalize_name("bisque")


def test_match_files_to_variants_matches_case_and_whitespace_insensitively():
    wood_types = {"bisque": {"name": "Bisque"}}
    files = [Path("proj_bisque.png")]
    variants = [Variant(id="gid://shopify/ProductVariant/1", option_value="  bisque ")]
    results = match_files_to_variants(files, wood_types, variants)
    assert results == [
        MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id="gid://shopify/ProductVariant/1")
    ]


def test_match_files_to_variants_flags_unmatched():
    wood_types = {"bisque": {"name": "Bisque"}}
    files = [Path("proj_bisque.png")]
    variants = [Variant(id="gid://shopify/ProductVariant/1", option_value="Frosty White")]
    results = match_files_to_variants(files, wood_types, variants)
    assert results == [
        MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id=None)
    ]


def test_match_files_to_variants_excludes_duplicate_option_values():
    wood_types = {"bisque": {"name": "Bisque"}}
    files = [Path("proj_bisque.png")]
    variants = [
        Variant(id="gid://shopify/ProductVariant/1", option_value="Bisque"),
        Variant(id="gid://shopify/ProductVariant/2", option_value="  bisque "),
    ]
    results = match_files_to_variants(files, wood_types, variants)
    assert results == [
        MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id=None)
    ]


def test_find_ambiguous_variants_groups_duplicates():
    variants = [
        Variant(id="gid://shopify/ProductVariant/1", option_value="Bisque"),
        Variant(id="gid://shopify/ProductVariant/2", option_value="  bisque "),
        Variant(id="gid://shopify/ProductVariant/3", option_value="Frosty White"),
    ]
    groups = find_ambiguous_variants(variants)
    assert len(groups) == 1
    assert {v.id for v in groups[0]} == {
        "gid://shopify/ProductVariant/1",
        "gid://shopify/ProductVariant/2",
    }


def test_print_preview_reports_ambiguous_count(capsys):
    matches = [MatchResult(path=Path("a.png"), wood_name="Bisque", variant_id=None)]
    ambiguous_groups = [
        [
            Variant(id="gid://shopify/ProductVariant/1", option_value="Bisque"),
            Variant(id="gid://shopify/ProductVariant/2", option_value="  bisque "),
        ]
    ]
    print_preview(matches, ambiguous_groups)
    out = capsys.readouterr().out
    assert "Ambiguous (skipped) (2)" in out


def test_resolve_material_type_finds_category(tmp_path):
    (tmp_path / "thermofoil_cabinet_doors.csv").write_text(
        "Title,Net Sales,Qty\nAR756 Thermofoil Cabinet Door,1000,10\n"
    )
    assert resolve_material_type("AR756 Thermofoil Cabinet Door", data_dir=tmp_path) == "rtf"


def test_resolve_material_type_raises_when_not_found(tmp_path):
    with pytest.raises(SystemExit):
        resolve_material_type("Nonexistent Product", data_dir=tmp_path)


def test_print_preview_lists_matched_and_unmatched(capsys):
    matches = [
        MatchResult(path=Path("a.png"), wood_name="Bisque", variant_id="gid://shopify/ProductVariant/1"),
        MatchResult(path=Path("b.png"), wood_name="Unknown", variant_id=None),
    ]
    print_preview(matches)
    out = capsys.readouterr().out
    assert "Matched (1)" in out
    assert "a.png -> Bisque" in out
    assert "Unmatched (1)" in out
    assert "b.png -> Unknown" in out


def test_read_shopify_credentials_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPIFY_STORE_DOMAIN", raising=False)
    monkeypatch.delenv("SHOPIFY_ADMIN_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here to load
    with pytest.raises(SystemExit):
        read_shopify_credentials()


def test_read_shopify_credentials_returns_env_values(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_API_TOKEN", "shpat_test")
    monkeypatch.chdir(tmp_path)
    domain, token = read_shopify_credentials()
    assert domain == "test-store.myshopify.com"
    assert token == "shpat_test"
