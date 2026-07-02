"""Tests for the style-class router: door_style -> measurable class | excluded."""

from backend.qa.styles_classes import (
    EXCLUDED,
    FRAME_NARROW,
    FRAME_STANDARD,
    STYLE_CLASSES,
    style_class,
)
from backend.styles.catalog import STYLES


def test_every_catalog_key_is_mapped() -> None:
    # The router is the single routing truth: no catalog key may be unclassified.
    for key in STYLES:
        assert key in STYLE_CLASSES, f"catalog key {key!r} not routed"
    assert set(STYLE_CLASSES) == set(STYLES)


def test_shaker_family_maps_to_frame_standard() -> None:
    for key in ("shaker", "shaker_cope_stick", "shaker_bevel", "drawer_shaker"):
        assert style_class(key) == FRAME_STANDARD


def test_recessed_framed_styles_are_measurable() -> None:
    for key in (
        "recessed_panel",
        "recessed_panel_center_stile",
        "recessed_panel_applied_molding",
        "terracina",
        "graham",
        "hayes",
    ):
        assert style_class(key) in (FRAME_STANDARD, FRAME_NARROW)


def test_skinny_shaker_family_maps_to_frame_narrow() -> None:
    for key in ("mitered_flat_panel", "rtf_drawer_shaker_skinny", "drawer_journey"):
        assert style_class(key) == FRAME_NARROW


def test_slab_bevel_plank_louver_radius_arched_map_to_excluded() -> None:
    for key in (
        "solid_plank",  # slab
        "drawer_solid_plank",  # slab
        "vienna",  # slab veneer
        "rtf_drawer_bevel",  # bevel
        "davenport",  # tongue-and-groove planks
        "louver",  # louver
        "raised_panel_radius",  # radius
        "drawer_raised_panel_radius",  # radius
        "mission",  # cathedral arch
    ):
        assert style_class(key) == EXCLUDED


def test_raised_panel_styles_are_excluded() -> None:
    for key in ("raised_panel", "drawer_raised_panel"):
        assert style_class(key) == EXCLUDED


def test_unknown_and_none_map_to_excluded_failsafe() -> None:
    assert style_class(None) == EXCLUDED
    assert style_class("") == EXCLUDED
    assert style_class("no_such_style") == EXCLUDED


def test_classes_are_the_three_known_names() -> None:
    assert set(STYLE_CLASSES.values()) <= {FRAME_STANDARD, FRAME_NARROW, EXCLUDED}
    # Every measurable class is actually used by at least one catalog key.
    assert FRAME_STANDARD in STYLE_CLASSES.values()
    assert FRAME_NARROW in STYLE_CLASSES.values()
