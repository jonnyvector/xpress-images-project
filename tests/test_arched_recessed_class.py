"""Arched recessed panels are geometry-excluded (they aren't measurable rectangles)."""

from backend.qa.styles_classes import EXCLUDED, style_class
from backend.styles.catalog import STYLES


def test_recessed_panel_arched_is_geometry_excluded():
    assert style_class("recessed_panel_arched") == EXCLUDED


def test_recessed_panel_arched_reuses_recessed_panel_prompts():
    arched = STYLES["recessed_panel_arched"]
    base = STYLES["recessed_panel"]
    assert arched["learn_prompt"] == base["learn_prompt"]
    assert arched["variation_hint"] == base["variation_hint"]
    assert arched["name"] == "Recessed Panel (Arched)"


def test_plain_recessed_panel_still_measurable():
    from backend.qa.styles_classes import FRAME_STANDARD
    assert style_class("recessed_panel") == FRAME_STANDARD
