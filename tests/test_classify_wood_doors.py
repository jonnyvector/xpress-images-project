import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "classify_wood_doors",
    Path(__file__).resolve().parents[1] / "scripts" / "classify_wood_doors.py",
)
cwd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cwd)


def test_prompt_names_the_door_and_lists_valid_styles():
    p = cwd.build_prompt("Talbot", "louver-like detailing... 2-1/4\" wide frame")
    assert "Talbot" in p and "louver" in p
    assert "solid_plank" in p and "raised_panel" in p  # enum offered to the model


def test_parse_valid_row():
    row = cwd.parse_spec('{"door_style":"louver","panel":"louver",'
                         '"frame_width_in":2.25,"joint":null,"arched":false,"notes":"louver"}')
    assert row["door_style"] == "louver" and row["frame_width_in"] == 2.25


def test_parse_rejects_bad_style():
    with pytest.raises(ValueError):
        cwd.parse_spec('{"door_style":"not_a_style","panel":"flat","arched":false,"notes":""}')


def test_parse_rejects_bad_panel():
    with pytest.raises(ValueError):
        cwd.parse_spec('{"door_style":"shaker","panel":"weird","arched":false,"notes":""}')


def test_door_styles_excludes_test_styles():
    assert "minimal" not in cwd.DOOR_STYLES
    assert "rtf_minimal" not in cwd.DOOR_STYLES
    assert "shaker" in cwd.DOOR_STYLES


def test_should_skip_preserves_existing_row_by_default():
    assert cwd.should_skip("Newbury", {"Newbury": {}}, force=False) is True


def test_should_skip_reclassifies_with_force():
    assert cwd.should_skip("Newbury", {"Newbury": {}}, force=True) is False


def test_should_skip_new_door_is_never_skipped():
    assert cwd.should_skip("Newbury", {}, force=False) is False
    assert cwd.should_skip("Newbury", {}, force=True) is False
