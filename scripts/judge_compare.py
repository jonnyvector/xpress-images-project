"""Compare vision models as the QA judge, on a frozen answer key.

Usage (via scripts/judgeeval.sh):
    build                  freeze the answer key (no API calls)
    run <preset> [--limit N]  judge the key with one model (OpenRouter, company key)
    report                 score every model run so far + current app verdicts,
                           write output/.qa/judge_compare/report.html

Scoring weighs both mistakes equally: missed bad images (reject recall) and
false alarms on good ones (false-flag rate) -> balanced accuracy.
"""

import argparse
import html
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.qa.corpus import walk_corpus
from backend.qa.eval import is_holdout
from backend.qa.eval_set import (
    build_eval_set,
    image_id_to_key,
    load_eval_set,
    save_eval_set,
)
from backend.qa.labels import LabelStore
from backend.qa.openrouter_judge import OpenRouterJudge
from backend.qa.styles_classes import style_class
from backend.qa.thumbs import jpeg_data_url, thumbnail_jpeg

PROJECTS = Path("output/.projects")
QA_DIR = Path("output/.qa")
OUT = QA_DIR / "judge_compare"
EVAL_SET = OUT / "eval_set.json"

# preset -> (OpenRouter model, ignore overall door shape, corner close-ups).
# "2" = shape note added; "3" = shape note + corner close-ups.
OPUS, SONNET, GEMINI = (
    "anthropic/claude-opus-5.5",
    "anthropic/claude-sonnet-5.5",
    "google/gemini-3.1-pro-preview",  # the app's current judge model
)
PRESETS = {
    "opus": (OPUS, False, False),
    "opus2": (OPUS, True, False),
    "opus3": (OPUS, True, True),
    "sonnet": (SONNET, False, False),
    "sonnet2": (SONNET, True, False),
    "sonnet3": (SONNET, True, True),
    "haiku": ("anthropic/claude-haiku-5.5", False, False),
    "gemini": (GEMINI, False, False),
    "gemini2": (GEMINI, True, False),
    "gemini3": (GEMINI, True, True),
}
APP = "app"  # verdicts the app already stored (Gemini + geometry + rules)


def _candidates():
    return {c.key: c for c in walk_corpus(PROJECTS, Path("swatches"))}


def cmd_build(args) -> None:
    if EVAL_SET.exists() and not args.rebuild:
        print(
            f"{EVAL_SET} already exists; pass --rebuild to replace it"
            " (earlier model results would then cover a different set)."
        )
        return
    labels = [asdict(label) for label in LabelStore(QA_DIR / "labels.json").all()]
    approvals = next(iter(json.loads((QA_DIR / "approvals.json").read_text()).values()), [])
    items = build_eval_set(_candidates(), labels, approvals, image_id_to_key(PROJECTS))
    save_eval_set(EVAL_SET, items)
    by = {}
    for item in items:
        by[(item.source, item.truth)] = by.get((item.source, item.truth), 0) + 1
    print(f"{len(items)} images frozen to {EVAL_SET}")
    for (source, truth), n in sorted(by.items()):
        print(f"  {source:9} {truth:7} {n}")


def cmd_run(args) -> None:
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY missing from .env (scripts/orkey.sh fetches it).")
    model, ignore_shape, corners = PRESETS[args.preset]
    items = load_eval_set(EVAL_SET)
    if args.keys:
        wanted = set(json.loads(Path(args.keys).read_text()))
        items = [item for item in items if item.key in wanted]
    items = items[: args.limit or None]
    candidates = _candidates()
    judge = OpenRouterJudge(
        key, model, cache_dir=QA_DIR / "verdicts", ignore_shape=ignore_shape, corners=corners
    )
    results_path = OUT / f"{args.preset}.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}

    todo = [item for item in items if item.key not in results]
    print(f"{args.preset} ({model}): {len(todo)} to judge, {len(items) - len(todo)} done")

    def one(item):
        # Hard spend cap: once reached, no new API calls (in-flight ones finish).
        if args.budget and judge.cost_usd >= args.budget:
            return item.key, None
        return item.key, judge.judge(candidates[item.key])

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for key, result in pool.map(one, todo):
            if result is None:
                continue
            results[key] = asdict(result)
            done += 1
            if done % 20 == 0 or done == len(todo):
                results_path.write_text(json.dumps(results))
                print(f"  {done}/{len(todo)}  spent ${judge.cost_usd:.2f}", flush=True)
    results_path.write_text(json.dumps(results))
    errors = sum(1 for r in results.values() if r["verdict"] == "error")
    print(f"done. this run cost ${judge.cost_usd:.2f}; {errors} errors (re-run to retry them)")
    # Errors aren't cached by the judge; drop them so a re-run retries.
    if errors:
        results_path.write_text(
            json.dumps({k: r for k, r in results.items() if r["verdict"] != "error"})
        )


def _app_verdicts() -> dict[str, dict]:
    """What the app's pipeline decided, keyed like the eval set."""
    out: dict[str, dict] = {}
    ids = image_id_to_key(PROJECTS)
    for manifest_path in PROJECTS.glob("*/manifest.json"):
        verdicts = json.loads(manifest_path.read_text()).get("qa_verdicts") or {}
        for image_id, v in verdicts.items():
            if image_id in ids and v.get("qa_status") == "done" and v.get("verdict"):
                flagged = v["verdict"] != "pass"
                out[ids[image_id]] = {
                    "verdict": "fail" if flagged else "pass",
                    "reason": v.get("reason", ""),
                }
    return out


def score(items, results: dict[str, dict]) -> dict:
    rejects = [i for i in items if i.truth == "reject" and i.key in results]
    accepts = [i for i in items if i.truth == "accept" and i.key in results]
    flagged = lambda i: results[i.key]["verdict"] != "pass"  # noqa: E731 (error counts as flagged)
    caught = sum(flagged(i) for i in rejects)
    false_flags = sum(flagged(i) for i in accepts)
    recall = caught / len(rejects) if rejects else 0.0
    ffr = false_flags / len(accepts) if accepts else 0.0
    return {
        "judged": len(rejects) + len(accepts),
        "rejects": len(rejects),
        "caught": caught,
        "accepts": len(accepts),
        "false_flags": false_flags,
        "reject_recall": recall,
        "false_flag_rate": ffr,
        "balanced_accuracy": (recall + 1 - ffr) / 2,
        "errors": sum(1 for i in rejects + accepts if results[i.key]["verdict"] == "error"),
    }


def _thumb(path: Path, edge: int = 260) -> str:
    try:
        return jpeg_data_url(thumbnail_jpeg(path, edge, quality=80))
    except OSError:
        return ""


def cmd_report(_args) -> None:
    items = load_eval_set(EVAL_SET)
    runs = {APP: _app_verdicts()}
    for preset in PRESETS:
        path = OUT / f"{preset}.json"
        if path.exists():
            runs[preset] = json.loads(path.read_text())

    rows = []
    print(f"{'model':8} {'judged':>6} {'caught bad':>12} {'false alarms':>13} {'balanced':>9}")
    for name, results in runs.items():
        s = score(items, results)
        rows.append((name, s))
        print(
            f"{name:8} {s['judged']:6} {s['caught']:5}/{s['rejects']:<4} ({s['reject_recall']:.0%})"
            f" {s['false_flags']:4}/{s['accepts']:<4} ({s['false_flag_rate']:.0%})"
            f" {s['balanced_accuracy']:8.0%}"
        )
    by_class: dict[str, dict] = {}
    candidates = _candidates()
    for name, results in runs.items():
        groups: dict[str, list] = {}
        for item in items:
            groups.setdefault(style_class(candidates[item.key].door_style), []).append(item)
        by_class[name] = {cls: score(group, results) for cls, group in sorted(groups.items())}
    (OUT / "report.json").write_text(
        json.dumps({"overall": dict(rows), "by_style_class": by_class}, indent=1)
    )
    _write_html(items, runs, rows, candidates)
    print(f"report: {OUT / 'report.html'}")


def _write_html(items, runs, rows, candidates) -> None:
    models = [name for name, _ in rows]
    table = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{s['judged']}</td>"
        f"<td>{s['caught']}/{s['rejects']} ({s['reject_recall']:.0%})</td>"
        f"<td>{s['false_flags']}/{s['accepts']} ({s['false_flag_rate']:.0%})</td>"
        f"<td><b>{s['balanced_accuracy']:.0%}</b></td></tr>"
        for n, s in rows
    )
    cards = []
    for item in items:
        verdicts = {m: runs[m].get(item.key) for m in models}
        wrong = [
            m
            for m, r in verdicts.items()
            if r is not None and (r["verdict"] != "pass") != (item.truth == "reject")
        ]
        if not wrong:
            continue
        c = candidates[item.key]
        lines = "".join(
            f"<li class={'bad' if m in wrong else 'ok'}><b>{html.escape(m)}</b>: "
            f"{html.escape(r['verdict'])} — {html.escape(r.get('reason', ''))}</li>"
            for m, r in verdicts.items()
            if r is not None
        )
        split = " · holdout" if is_holdout(item.project_id) else ""
        sample = _thumb(c.sample_path) if c.sample_path else ""
        wood = html.escape(c.wood_name or "replica")
        cards.append(
            f"<div class=card><div class=imgs><img src='{sample}' title=sample>"
            f"<img src='{_thumb(c.image_path)}' title=generated></div>"
            f"<div class=meta><b>{html.escape(c.project_name)}</b> · {wood}"
            f" · {html.escape(c.door_style or '?')}{split}<br>"
            f"You: <b class={item.truth}>{item.truth}</b> ({item.source}"
            f"{': ' + ', '.join(item.reasons) if item.reasons else ''})"
            f"<ul>{lines}</ul><code>{html.escape(item.key)}</code></div></div>"
        )
    page = f"""<!doctype html><meta charset=utf-8><title>Judge comparison</title>
<style>body{{font:14px system-ui;margin:24px;max-width:1300px}}table{{border-collapse:collapse}}
td,th{{padding:4px 12px;border-bottom:1px solid #ddd;text-align:left}}
.card{{display:flex;gap:12px;border:1px solid #ddd;border-radius:8px;padding:8px;margin:8px 0}}
.imgs img{{height:260px;margin-right:4px;background:#eee}}.bad{{color:#b91c1c}}.ok{{color:#15803d}}
b.reject{{color:#b91c1c}}b.accept{{color:#15803d}}code{{color:#888;font-size:11px}}</style>
<h1>Judge comparison</h1><p>{len(items)} images. Left image = sample photo, right = generated.
Balanced = average of "caught bad" and "didn't flag good".</p>
<table><tr><th>model</th><th>judged</th><th>caught bad</th><th>false alarms</th>
<th>balanced</th></tr>{table}</table>
<h2>Disagreements with you ({len(cards)})</h2>{"".join(cards)}"""
    (OUT / "report.html").write_text(page)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    build = sub.add_parser("build")
    build.add_argument("--rebuild", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("preset", choices=sorted(PRESETS))
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--keys", help="JSON list of eval-set keys to judge (default: all)")
    run.add_argument("--budget", type=float, default=0, help="stop new calls once this many USD")
    run.add_argument("--workers", type=int, default=6)
    sub.add_parser("report")
    args = parser.parse_args()
    {"build": cmd_build, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
