import json
from types import SimpleNamespace

import pytest

from backend.qa.judge import IDENTITY_PROMPT, IdentityResult, judge_replica_identity, parse_identity
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


class FakeClient:
    def __init__(self, text):
        self.calls, self._text = [], text
        self.models = self

    def generate_content(self, *, model, contents):
        self.calls.append(contents)
        return SimpleNamespace(text=self._text)


def test_judge_without_drawing_prompt_and_parts_unchanged():
    fake = FakeClient(_payload())
    judge_replica_identity(fake, b"\xff\xd8src", b"\xff\xd8rep", ["panel: flat"])
    parts = fake.calls[0][0].parts
    assert sum(1 for p in parts if p.inline_data is not None) == 2
    assert "CROSS-SECTION" not in parts[-1].text


def test_judge_with_drawing_inserts_it_between_sample_and_replica():
    fake = FakeClient(_payload())
    judge_replica_identity(fake, b"\xff\xd8src", b"\xff\xd8rep", [],
                           profile_bytes=b"\x89PNGxsec")
    parts = fake.calls[0][0].parts
    imgs = [p for p in parts if p.inline_data is not None]
    assert len(imgs) == 3
    assert imgs[0].inline_data.data == b"\xff\xd8src"      # sample stays FIRST
    assert imgs[1].inline_data.data == b"\x89PNGxsec"      # drawing in the middle
    assert imgs[2].inline_data.data == b"\xff\xd8rep"      # replica stays LAST image
    assert "CROSS-SECTION" in parts[-1].text


def test_xsection_placeholder_collapses_cleanly_when_empty():
    p = IDENTITY_PROMPT.format(facts="- f", xsection="")
    # Original paragraph spacing must survive an empty block (byte-identical rule).
    assert "bullnose (fully rounded).\n\nProfile geometry is where" in p
    assert "CROSS-SECTION" not in p
