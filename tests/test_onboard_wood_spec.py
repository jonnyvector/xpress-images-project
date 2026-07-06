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
