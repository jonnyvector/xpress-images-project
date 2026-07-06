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
