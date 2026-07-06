from backend.wood_specs import WoodSpec, learn_notes, load_wood_specs


def _write(tmp_path, data):
    import json
    p = tmp_path / "wood_door_specs.json"
    p.write_text(json.dumps(data))
    return p


def test_load_parses_rows(tmp_path):
    p = _write(tmp_path, {
        "Newbury": {"door_style": "shaker", "panel": "flat", "frame_width_in": 2.0,
                    "joint": "miter", "arched": False, "notes": "skinny shaker"},
        "Tacoma": {"door_style": "solid_plank", "panel": "slab", "frame_width_in": None,
                   "joint": None, "arched": False, "notes": "solid plank"},
    })
    specs = load_wood_specs(p)
    assert specs["Newbury"] == WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker")
    assert specs["Tacoma"].frame_width_in is None
    assert specs["Tacoma"].door_style == "solid_plank"


def test_missing_file_is_empty(tmp_path):
    assert load_wood_specs(tmp_path / "nope.json") == {}


def test_learn_notes_includes_exact_frame_width():
    note = learn_notes(WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker"))
    assert "2" in note and "inch" in note.lower()
    # no frame width -> no frame sentence
    assert "frame is exactly" not in learn_notes(
        WoodSpec("solid_plank", "slab", None, None, False, "plank"))
