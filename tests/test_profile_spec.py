import json

import pytest

from backend.qa.profile_spec import (
    EXTRACT_PROMPT,
    REGIONS,
    parse_facts,
    profile_facts_note,
)


def test_regions_are_the_seven_anatomy_keys_in_order():
    assert REGIONS == (
        "outside_edge", "stiles_rails", "joints_corners", "inside_edge",
        "panel", "trim_molding", "top_rail_arch",
    )


def test_extract_prompt_names_every_region_and_scale_rule():
    for region in REGIONS:
        assert region in EXTRACT_PROMPT
    assert "9:16" in EXTRACT_PROMPT
    assert "never an absolute count" in EXTRACT_PROMPT


def test_parse_facts_accepts_fenced_json():
    text = '```json\n{"facts": ["outside_edge: square, eased", "panel: flat recess"]}\n```'
    assert parse_facts(text) == ["outside_edge: square, eased", "panel: flat recess"]


def test_parse_facts_rejects_empty_and_oversized():
    with pytest.raises(ValueError):
        parse_facts('{"facts": []}')
    with pytest.raises(ValueError):
        parse_facts('{"facts": [""]}')
    with pytest.raises(ValueError):
        parse_facts(json.dumps({"facts": ["f"] * 13}))  # valid JSON, >12 facts
    with pytest.raises(ValueError):
        parse_facts('{"nope": 1}')


def test_profile_facts_note_single_line_and_empty():
    note = profile_facts_note(["panel: flat recess", "frame: 2.25in flat"])
    assert "\n" not in note
    assert "panel: flat recess" in note and "frame: 2.25in flat" in note
    assert profile_facts_note([]) == ""
