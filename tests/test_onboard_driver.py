"""M4: driver spec table + source resolution + idempotency helpers."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "onboard_rtf", Path(__file__).resolve().parents[1] / "scripts" / "onboard_rtf.py"
)
onboard_rtf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(onboard_rtf)


def test_door_spec_covers_the_five_and_is_well_formed():
    codes = [d["code"] for d in onboard_rtf.DOORS]
    assert codes == ["FR556", "KB732", "DT223", "DP8", "AP768"]
    valid_styles = {"raised_panel", "solid_plank", "recessed_panel", "shaker_bevel"}
    for d in onboard_rtf.DOORS:
        assert d["door_style"] in valid_styles
        assert isinstance(d["notes"], str)  # may be "" — minimal prompt is valid


def test_source_image_resolves_present_and_missing(tmp_path):
    cat = tmp_path / "rtf"
    hero = cat / "FR556-3-4" / "hero"
    hero.mkdir(parents=True)
    (hero / "door.jpg").write_bytes(b"jpeg")
    assert onboard_rtf.source_image("FR556", catalog=cat) == hero / "door.jpg"
    assert onboard_rtf.source_image("NOPE", catalog=cat) is None


class _P:
    def __init__(self, name, sig):
        self.name = name
        self.has_signature = sig
        self.id = "pid-" + name


class _Store:
    def __init__(self, projects):
        self._projects = projects

    def list_projects(self):
        return self._projects


def test_already_onboarded_matches_only_with_signature():
    store = _Store([_P("FR556 Thermofoil Cabinet Door", True)])
    assert onboard_rtf.already_onboarded(store, "FR556") is not None
    # same code but no signature yet → not considered onboarded
    store2 = _Store([_P("FR556 Thermofoil Cabinet Door", False)])
    assert onboard_rtf.already_onboarded(store2, "FR556") is None
    # unrelated project
    store3 = _Store([_P("DR133 Victoria", True)])
    assert onboard_rtf.already_onboarded(store3, "FR556") is None
