from pathlib import Path

import pytest

from backend.shopify_admin import Variant
from scripts.upload_to_shopify import (
    MatchResult,
    match_files_to_variants,
    normalize_name,
    print_preview,
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
    assert results == [MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id=None)]


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
