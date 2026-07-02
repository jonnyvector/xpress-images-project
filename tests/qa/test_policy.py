from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult
from backend.qa.policy import PolicyConfig, decide, load_policy


def _candidate(
    style: str | None = "shaker", sample_path: Path | None = Path("sample.bin")
) -> Candidate:
    return Candidate(
        key="p:0:variant:0", project_id="p", project_name="P", door_style=style,
        version=0, kind="variant", index=0, wood_name="Cherry Natural",
        image_path=Path("x.bin"), sample_path=sample_path, swatch_path=None, presumed="accept",
    )


def _result(**overrides: object) -> JudgeResult:
    base = dict(
        key="p:0:variant:0", panel_layout_match=5, proportions_match=5,
        profile_character_match=5, material_realism=5, swatch_fidelity=5,
        artifacts=[], verdict="pass", confidence="high", reason="ok",
    )
    base.update(overrides)
    return JudgeResult(**base)  # type: ignore[arg-type]


CONFIG = PolicyConfig(min_score=4, untrusted_styles=["applied_molding"])


def test_high_confidence_pass() -> None:
    assert decide(_result(), _candidate(), CONFIG).verdict == "pass"


def test_fail_verdict_regenerates() -> None:
    d = decide(_result(verdict="fail", reason="stiles wider"), _candidate(), CONFIG)
    assert d.verdict == "regenerate"
    assert "stiles wider" in d.reason


def test_low_score_regenerates_even_if_judge_said_pass() -> None:
    d = decide(_result(proportions_match=3), _candidate(), CONFIG)
    assert d.verdict == "regenerate"


def test_low_confidence_pass_needs_human() -> None:
    d = decide(_result(confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_error_needs_human() -> None:
    d = decide(_result(verdict="error", confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_untrusted_style_needs_human_regardless() -> None:
    d = decide(_result(), _candidate(style="applied_molding"), CONFIG)
    assert d.verdict == "needs_human"


def test_no_sample_photo_needs_human_even_on_perfect_pass() -> None:
    d = decide(_result(), _candidate(sample_path=None), CONFIG)
    assert d.verdict == "needs_human"
    assert "sample" in d.reason.lower()


def test_load_policy_default_file() -> None:
    config = load_policy(Path("backend/qa/policy_config.json"))
    assert config.min_score >= 1
