"""Near-white RTF colors attach the approved replica as a geometry anchor.

White-on-white collapses the tiered recessed profile to a raised panel because
the signature/prompt signal is too weak at near-zero luminance contrast; the
replica image restores geometry independent of color. Scoped to near-white RTF
only (darker colors don't need it; a white replica could lighten a saturated
target).
"""

from backend.worker import _needs_geometry_anchor


def test_pure_white_rtf_triggers_anchor():
    for hexv in ("FAF9F5", "F8F8F6", "FEFEF9", "FFFFFF"):
        assert _needs_geometry_anchor({"hex": hexv}, "rtf"), hexv


def test_midtone_and_dark_rtf_do_not_trigger():
    for hexv in ("8B5A2B", "3C3C3C", "C0A080", "DBDBDB"):
        assert not _needs_geometry_anchor({"hex": hexv}, "rtf")


def test_non_rtf_never_triggers():
    assert not _needs_geometry_anchor({"hex": "FAF9F5"}, "wood")


def test_non_hex_white_falls_back_to_swatch_luminance(tmp_path):
    from PIL import Image

    white = tmp_path / "velvet-white.png"
    Image.new("RGB", (4, 4), (254, 255, 249)).save(white)
    assert _needs_geometry_anchor({"swatch_path": white}, "rtf")

    dark = tmp_path / "walnut.png"
    Image.new("RGB", (4, 4), (70, 45, 20)).save(dark)
    assert not _needs_geometry_anchor({"swatch_path": dark}, "rtf")


def test_no_hex_and_no_swatch_does_not_trigger():
    assert not _needs_geometry_anchor({"swatch_path": None}, "rtf")


def test_missing_or_bad_hex_does_not_trigger():
    assert not _needs_geometry_anchor({"hex": None}, "rtf")
    assert not _needs_geometry_anchor({}, "rtf")
    assert not _needs_geometry_anchor({"hex": "xyz"}, "rtf")
    assert not _needs_geometry_anchor({"hex": "FFF"}, "rtf")
