"""Trust-gate configuration: batch limits, bulk unlock, retry/cost caps.

Owns reading ``backend/qa/trust_config.json`` — the operator-edited knobs of
the graduated-trust pipeline (D-004/D-005/D-009). Read at gate time per
request so edits apply without a restart, and snapshotted into each run
manifest at run start so a mid-run edit never changes a running run's rules.

Fail-safe: any parse/validation problem falls back to the conservative
defaults below (bulk locked, $10 cap) — a broken config file can never
unlock bulk spending.

Not responsible for: enforcing gates (routers) or spend accounting (runs.py).
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from backend.qa.styles_classes import style_class

DEFAULT_TRUST_CONFIG_PATH = Path("backend/qa/trust_config.json")


@dataclass
class TrustConfig:
    small_batch_limit: int = 5
    bulk_unlocked: bool = False
    bulk_unlocked_style_classes: list[str] = field(default_factory=list)
    max_auto_retries: int = 2
    run_cost_cap_usd: float = 10.0
    image_cost_usd: float = 0.134


def load_trust_config(path: Path = DEFAULT_TRUST_CONFIG_PATH) -> TrustConfig:
    """Read the config; ANY problem yields the conservative defaults."""
    try:
        data = json.loads(path.read_text())
        return TrustConfig(
            small_batch_limit=int(data.get("small_batch_limit", 5)),
            bulk_unlocked=bool(data.get("bulk_unlocked", False)),
            bulk_unlocked_style_classes=[
                str(s) for s in data.get("bulk_unlocked_style_classes", [])
            ],
            max_auto_retries=int(data.get("max_auto_retries", 2)),
            run_cost_cap_usd=float(data.get("run_cost_cap_usd", 10.0)),
            image_cost_usd=float(data.get("image_cost_usd", 0.134)),
        )
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return TrustConfig()


def bulk_unlocked_for(config: TrustConfig, door_style: str | None) -> bool:
    """Is Stage C (bulk) unlocked for this project's style-class?"""
    if config.bulk_unlocked:
        return True
    return style_class(door_style) in config.bulk_unlocked_style_classes


def snapshot(config: TrustConfig) -> dict:
    """JSON-serializable copy for run manifests (D-009)."""
    return asdict(config)
