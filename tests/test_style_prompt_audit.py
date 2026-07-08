"""M4 (lean-conditioning): raised_panel's learn prompt must not cue the bevel
prior (D-004) — the word "bevel" hid in it through 16 failed El Dorado attempts."""
from backend.generator import STYLES


def test_raised_panel_prompt_has_no_bevel_token():
    prompt = STYLES["raised_panel"]["learn_prompt"].lower()
    assert "bevel" not in prompt
    assert "raise" in prompt   # still names the raise itself
