"""Render the calibration labeling contact sheets (static HTML + tiny JS)."""

import html
import json

from backend.qa.corpus import Candidate
from backend.qa.labels import REASONS, Label, LabelStore


def parse_label_post(raw: bytes) -> Label:
    """Parse a ``POST /label`` request body into a Label.

    Raises ``json.JSONDecodeError`` on malformed JSON and ``KeyError`` on missing
    fields; verdict/reason validation happens in ``LabelStore.set``.
    """
    data = json.loads(raw)
    return Label(key=data["key"], verdict=data["verdict"], reasons=data.get("reasons", []))

_CSS = """
body{font-family:system-ui;background:#141414;color:#eee;margin:0;padding:16px}
a{color:#8ab4f8}
.card{display:flex;gap:12px;border:3px solid #444;border-radius:8px;padding:10px;margin:12px 0}
.card.accept{border-color:#2e7d32}
.card.reject{border-color:#c62828}
.card img{max-height:360px;border-radius:4px;background:#000}
.imgs{display:flex;gap:8px;align-items:flex-start}
.imgs figure{margin:0;text-align:center;font-size:12px;color:#aaa}
.meta{min-width:240px}
.reasons label{display:block;font-size:13px;margin:2px 0}
button{padding:6px 14px;margin:4px 6px 4px 0;cursor:pointer;border-radius:4px;border:0}
.b-accept{background:#2e7d32;color:#fff}
.b-reject{background:#c62828;color:#fff}
.savebar{position:sticky;top:0;background:#141414;padding:8px 0;z-index:2}
"""

_JS = """
async function post(key, verdict, reasons){
  for (let attempt = 0; attempt < 3; attempt++){
    try {
      const r = await fetch('/label', {method:'POST',
        body: JSON.stringify({key: key, verdict: verdict, reasons: reasons})});
      if (r.status === 204) return true;
    } catch (e) { /* retry */ }
    await new Promise(res => setTimeout(res, 200 * (attempt + 1)));
  }
  return false;
}
function reasonsOf(card){
  return Array.from(card.querySelectorAll('input:checked')).map(i => i.value);
}
function saveMsg(text){
  const el = document.getElementById('savemsg');
  if (el) el.textContent = text;
}
async function setLabel(btn, verdict){
  const card = btn.closest('.card');
  card.classList.remove('accept', 'reject');
  card.classList.add(verdict);
  card.dataset.explicit = '1';
  const ok = await post(card.dataset.key, verdict, verdict === 'reject' ? reasonsOf(card) : []);
  saveMsg(ok ? '' : 'SAVE FAILED for ' + card.dataset.key + ' — click the button again');
}
async function saveAll(){
  let failed = 0;
  for (const card of document.querySelectorAll('.card')){
    const verdict = card.classList.contains('reject') ? 'reject' : 'accept';
    const ok = await post(card.dataset.key, verdict, verdict === 'reject' ? reasonsOf(card) : []);
    if (ok) card.dataset.explicit = '1'; else failed++;
  }
  saveMsg(failed ? failed + ' card(s) FAILED to save — click Save all again'
                 : 'All cards on page saved.');
}
"""


def _figure(url: str, caption: str) -> str:
    escaped_caption = html.escape(caption)
    return (
        f'<figure><img src="{html.escape(url)}" loading="lazy">'
        f"<figcaption>{escaped_caption}</figcaption></figure>"
    )


def render_project_sheet(
    project_name: str,
    candidates: list[Candidate],
    labels: LabelStore,
    thumb_urls: dict[str, dict[str, str]],
) -> str:
    cards: list[str] = []
    for c in candidates:
        label = labels.get(c.key)
        state = label.verdict if label else c.presumed
        checked = set(label.reasons) if label else set()
        urls = thumb_urls.get(c.key, {})
        figs: list[str] = []
        if "sample" in urls:
            figs.append(_figure(urls["sample"], "sample"))
        if "img" in urls:
            figs.append(_figure(urls["img"], c.kind))
        if "swatch" in urls:
            figs.append(_figure(urls["swatch"], "swatch"))
        reason_boxes = "".join(
            f'<label><input type="checkbox" value="{r}"'
            f'{" checked" if r in checked else ""}> {r}</label>'
            for r in REASONS
        )
        title = f"{c.kind} · {c.wood_name or 'base door'}"
        if c.version:
            title += f" · archived v{c.version}"
        no_sample = "" if c.sample_path else "<div>⚠ no sample photo on file</div>"
        cards.append(
            f'<div class="card {state}" data-key="{html.escape(c.key)}">'
            f'<div class="imgs">{"".join(figs)}</div>'
            f'<div class="meta"><h3>{html.escape(title)}</h3>{no_sample}'
            f'<button class="b-accept" onclick="setLabel(this, \'accept\')">Accept</button>'
            f'<button class="b-reject" onclick="setLabel(this, \'reject\')">Reject</button>'
            f'<div class="reasons">{reason_boxes}</div></div></div>'
        )
    return (
        f"<!doctype html><meta charset=utf-8><title>{html.escape(project_name)}</title>"
        f"<style>{_CSS}</style><script>{_JS}</script>"
        f'<div class="savebar"><a href="index.html">← index</a> '
        f"<h2 style=\"display:inline\">{html.escape(project_name)}</h2> "
        f'<button onclick="saveAll()">Save all on page</button> <span id="savemsg"></span></div>'
        f'{"".join(cards)}'
    )


def render_index(projects: list[tuple[str, str, int, int]]) -> str:
    rows = "".join(
        f'<li><a href="project_{html.escape(pid)}.html">{html.escape(name)}</a>'
        f" — {labeled} / {total} labeled</li>"
        for pid, name, labeled, total in projects
    )
    return (
        "<!doctype html><meta charset=utf-8><title>QA labeling</title>"
        f"<style>{_CSS}</style><h1>Calibration labeling</h1>"
        "<p>Current results default to <b>accept</b>, archived versions to <b>reject</b>. "
        'Flip the exceptions, tick reasons on rejects, then "Save all on page".</p>'
        f"<ul>{rows}</ul>"
    )
