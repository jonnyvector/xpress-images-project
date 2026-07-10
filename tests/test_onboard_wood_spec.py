import importlib.util
from pathlib import Path

from backend.wood_specs import WoodSpec

_spec = importlib.util.spec_from_file_location(
    "onboard_wood", Path(__file__).resolve().parents[1] / "scripts" / "onboard_wood.py")
onboard_wood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(onboard_wood)


def test_door_spec_uses_spec_file_not_folder():
    specs = {"Tacoma": WoodSpec("solid_plank", "slab", None, None, False, "plank"),
             "Newbury": WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker")}
    style, notes = onboard_wood.door_spec("Tacoma", specs)
    assert style == "solid_plank"       # folder says raised-panel; spec wins
    assert notes == ""                  # no frame width -> no note
    style2, notes2 = onboard_wood.door_spec("Newbury", specs)
    assert style2 == "shaker"
    assert "2 inches" in notes2


def test_door_spec_missing_entry_returns_none_style():
    style, notes = onboard_wood.door_spec("Unlisted", {})
    assert style is None and notes == ""


def test_canonical_name_matches_spec_key_case_insensitively():
    specs = {"Indiana": WoodSpec("shaker_bevel", "flat", None, "cope", False, ""),
             "El Dorado": WoodSpec("raised_panel", "raised", None, "miter", False, "")}
    # lowercase roster name (built from a lowercase project name) resolves to
    # the spec's canonical casing — the 2026-07-09 casing gremlin.
    assert onboard_wood.canonical_name("indiana", specs) == "Indiana"
    assert onboard_wood.canonical_name("EL DORADO", specs) == "El Dorado"
    # already canonical or genuinely absent -> returned unchanged
    assert onboard_wood.canonical_name("Indiana", specs) == "Indiana"
    assert onboard_wood.canonical_name("Unlisted", specs) == "Unlisted"


def test_select_doors_only_returns_single():
    assert onboard_wood.select_doors(["A", "B"], only="A") == ["A"]


def test_select_doors_list_splits_and_trims():
    assert onboard_wood.select_doors(["A", "B", "C"], doors="A, C") == ["A", "C"]


def test_select_doors_all_returns_every_spec_name_sorted():
    assert onboard_wood.select_doors(["B", "A", "C"], all_=True) == ["A", "B", "C"]


def test_select_doors_requires_exactly_one_selector():
    import pytest
    with pytest.raises(SystemExit):
        onboard_wood.select_doors(["A"])                       # none given
    with pytest.raises(SystemExit):
        onboard_wood.select_doors(["A"], only="A", all_=True)  # two given


def test_select_doors_dedupes_preserving_order():
    assert onboard_wood.select_doors([], doors="A, B, A") == ["A", "B"]


def test_select_doors_empty_after_split_errors():
    import pytest
    with pytest.raises(SystemExit):
        onboard_wood.select_doors([], doors=" , ")  # non-empty but no real names


def _fake_catalog(tmp_path, with_profile=True):
    d = tmp_path / "raised-panel" / "El Dorado"
    (d / "hero").mkdir(parents=True)
    (d / "hero" / "door.jpg").write_bytes(b"hero")
    if with_profile:
        (d / "profile").mkdir()
        (d / "profile" / "3d-profile.jpg").write_bytes(b"xsec")
    return tmp_path


def test_resolve_profile_finds_drawing(tmp_path):
    cat = _fake_catalog(tmp_path)
    p = onboard_wood.resolve_profile("El Dorado", catalog=cat)
    assert p is not None and p.read_bytes() == b"xsec"


def test_resolve_profile_missing_returns_none(tmp_path):
    cat = _fake_catalog(tmp_path, with_profile=False)
    assert onboard_wood.resolve_profile("El Dorado", catalog=cat) is None


def test_resolve_profile_prefix_match_like_dylan_7_8(tmp_path):
    d = tmp_path / "raised-panel" / "Dylan-7-8"
    (d / "profile").mkdir(parents=True)
    (d / "profile" / "3d-profile.jpg").write_bytes(b"xsec")
    assert onboard_wood.resolve_profile("Dylan", catalog=tmp_path) is not None


def test_resolve_hero_still_works_with_catalog_override(tmp_path):
    cat = _fake_catalog(tmp_path)
    p = onboard_wood.resolve("El Dorado", catalog=cat)
    assert p is not None and p.read_bytes() == b"hero"
