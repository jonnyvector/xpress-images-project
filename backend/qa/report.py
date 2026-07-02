"""Render the flagged-images review report."""

import html

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult
from backend.qa.policy import Decision
from backend.qa.sheet import _CSS, _figure

_ORDER = {"needs_human": 0, "regenerate": 1}


def render_review_report(
    items: list[tuple[Candidate, JudgeResult, Decision]],
    thumb_urls: dict[str, dict[str, str]],
) -> str:
    flagged = [it for it in items if it[2].verdict != "pass"]
    passed = len(items) - len(flagged)
    flagged.sort(
        key=lambda it: (_ORDER.get(it[2].verdict, 9), it[0].door_style or "", it[0].key)
    )
    cards: list[str] = []
    for candidate, result, decision in flagged:
        urls = thumb_urls.get(candidate.key, {})
        figs = "".join(
            _figure(urls[role], role)
            for role in ("sample", "img", "swatch")
            if role in urls
        )
        scores = (
            f"layout {result.panel_layout_match} · proportions {result.proportions_match} · "
            f"profile {result.profile_character_match} · realism {result.material_realism} · "
            f"swatch {result.swatch_fidelity}"
        )
        cards.append(
            f'<div class="card reject" data-key="{html.escape(candidate.key)}">'
            f'<div class="imgs">{figs}</div><div class="meta">'
            f"<h3>{html.escape(decision.verdict)} · {html.escape(candidate.project_name)} · "
            f"{html.escape(candidate.wood_name or 'base door')}</h3>"
            f"<div>{html.escape(candidate.door_style or 'unknown style')} · "
            f"{html.escape(candidate.key)}</div>"
            f"<div>{html.escape(scores)}</div>"
            f"<p>{html.escape(decision.reason)}</p></div></div>"
        )
    return (
        "<!doctype html><meta charset=utf-8><title>QA review</title>"
        f"<style>{_CSS}</style><h1>Flagged images</h1>"
        f"<p>{len(flagged)} flagged · {passed} passed (not shown)</p>"
        f'{"".join(cards)}'
    )
