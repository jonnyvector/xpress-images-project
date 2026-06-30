"""Tests for filename → wood-name extraction heuristics."""

from backend.filename_parsing import extract_wood_name

WOOD_TYPES = {
    "white-oak": {"name": "White Oak"},
    "alabaster": {"name": "Alabaster"},
    "red-oak-select": {"name": "Red Oak Select"},
}


def test_exact_key_match() -> None:
    assert extract_wood_name("white-oak", WOOD_TYPES) == "White Oak"


def test_trailing_version_number_stripped() -> None:
    assert extract_wood_name("white-oak (2)", WOOD_TYPES) == "White Oak"


def test_model_code_prefix_then_color() -> None:
    assert extract_wood_name("DR1-df-slab_alabaster", WOOD_TYPES) == "Alabaster"


def test_trailing_rtf_suffix_ignored() -> None:
    assert extract_wood_name("KB732_alabaster_rtf", WOOD_TYPES) == "Alabaster"


def test_prefix_match_resolves_longer_key() -> None:
    assert extract_wood_name("red-oak-select", WOOD_TYPES) == "Red Oak Select"


def test_unknown_falls_back_to_titlecased_stem() -> None:
    assert extract_wood_name("mystery_finish", WOOD_TYPES) == "Mystery Finish"
