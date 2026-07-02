"""Turn a JudgeResult into pass / regenerate / needs_human. Fail-safe: doubt -> human."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult

DEFAULT_POLICY_PATH = Path("backend/qa/policy_config.json")


@dataclass
class PolicyConfig:
    min_score: int = 4
    untrusted_styles: list[str] = field(default_factory=list)


@dataclass
class Decision:
    key: str
    verdict: str  # "pass" | "regenerate" | "needs_human"
    reason: str


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> PolicyConfig:
    data = json.loads(path.read_text())
    return PolicyConfig(
        min_score=int(data.get("min_score", 4)),
        untrusted_styles=list(data.get("untrusted_styles", [])),
    )


def decide(result: JudgeResult, candidate: Candidate, config: PolicyConfig) -> Decision:
    if candidate.door_style in config.untrusted_styles:
        return Decision(result.key, "needs_human", f"untrusted style: {candidate.door_style}")
    if result.verdict == "error":
        return Decision(result.key, "needs_human", f"judge error: {result.reason}")
    scores = {
        "panel_layout_match": result.panel_layout_match,
        "proportions_match": result.proportions_match,
        "profile_character_match": result.profile_character_match,
        "material_realism": result.material_realism,
        "swatch_fidelity": result.swatch_fidelity,
    }
    low = [f"{name}={value}" for name, value in scores.items() if value < config.min_score]
    if result.verdict == "fail" or low:
        detail = result.reason or "judge fail"
        if low:
            detail += f" (low scores: {', '.join(low)})"
        return Decision(result.key, "regenerate", detail)
    if result.confidence == "low":
        return Decision(result.key, "needs_human", "low judge confidence")
    return Decision(result.key, "pass", result.reason)
