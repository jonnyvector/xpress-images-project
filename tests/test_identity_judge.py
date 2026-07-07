import json

import pytest

from backend.qa.judge import IDENTITY_PROMPT, IdentityResult, parse_identity
from backend.qa.profile_spec import REGIONS


def _payload(**overrides):
    base = {
        "fact_checks": [{"fact": "panel: flat recess", "holds": True, "observed": "flat recess"}],
        "region_sweep": {r: "matches" for r in REGIONS},
        "defects": [],
        "disqualified": False,
    }
    base.update(overrides)
    return json.dumps(base)


def test_prompt_names_regions_916_and_carveouts():
    for region in REGIONS:
        assert region in IDENTITY_PROMPT
    assert "9:16" in IDENTITY_PROMPT
    assert "grain" in IDENTITY_PROMPT.lower() and "lighting" in IDENTITY_PROMPT.lower()


def test_clean_replica_not_disqualified():
    r = parse_identity("k", _payload())
    assert isinstance(r, IdentityResult)
    assert r.disqualified is False and r.defects == [] and r.verdict == "ok"


def test_failed_fact_disqualifies_even_if_model_says_ok():
    r = parse_identity("k", _payload(
        fact_checks=[{"fact": "panel: flat", "holds": False, "observed": "raised"}],
        disqualified=False,
    ))
    assert r.disqualified is True
    assert any("panel: flat" in d for d in r.defects)


def test_region_difference_disqualifies_and_becomes_defect():
    sweep = {r: "matches" for r in REGIONS}
    sweep["trim_molding"] = "replica adds applied molding; sample has none"
    r = parse_identity("k", _payload(region_sweep=sweep, disqualified=False))
    assert r.disqualified is True
    assert any("applied molding" in d for d in r.defects)


def test_missing_region_is_malformed():
    sweep = {r: "matches" for r in REGIONS[:-1]}  # drop one region
    with pytest.raises(ValueError):
        parse_identity("k", _payload(region_sweep=sweep))


def test_fenced_reply_is_parsed():
    r = parse_identity("k", "```json\n" + _payload() + "\n```")
    assert r.verdict == "ok"
