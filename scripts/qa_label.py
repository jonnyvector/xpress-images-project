"""Serve the calibration labeling UI.

Usage:
    uv run python scripts/qa_label.py [--port 8777] [--project PROJECT_ID]

Builds a static site under output/.qa/site/ (thumbnails cached across runs), then serves
it locally. Accept/Reject clicks persist immediately to output/.qa/labels.json.
"""

import argparse
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.qa.corpus import Candidate, walk_corpus
from backend.qa.labels import LabelStore
from backend.qa.sheet import parse_label_post, render_index, render_project_sheet
from backend.qa.thumbs import export_thumb

QA_DIR = Path("output/.qa")
SITE_DIR = QA_DIR / "site"
THUMBS_DIR = SITE_DIR / "thumbs"


def _thumb_urls_for(cands: list[Candidate]) -> dict[str, dict[str, str]]:
    thumb_urls: dict[str, dict[str, str]] = {}
    for c in cands:
        urls: dict[str, str] = {}
        for role, src in (("img", c.image_path), ("sample", c.sample_path),
                          ("swatch", c.swatch_path)):
            if src is None:
                continue
            thumb = export_thumb(src, THUMBS_DIR)
            if thumb is not None:
                urls[role] = f"thumbs/{thumb.name}"
        thumb_urls[c.key] = urls
    return thumb_urls


def build_site(candidates: list[Candidate], labels: LabelStore) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    by_project: dict[str, list[Candidate]] = {}
    names: dict[str, str] = {}
    for c in candidates:
        by_project.setdefault(c.project_id, []).append(c)
        names[c.project_id] = c.project_name

    index_rows: list[tuple[str, str, int, int]] = []
    for pid, cands in sorted(by_project.items(), key=lambda kv: names[kv[0]].lower()):
        page = render_project_sheet(names[pid], cands, labels, _thumb_urls_for(cands))
        (SITE_DIR / f"project_{pid}.html").write_text(page)
        labeled = sum(1 for c in cands if labels.get(c.key) is not None)
        index_rows.append((pid, names[pid], labeled, len(cands)))
    (SITE_DIR / "index.html").write_text(render_index(index_rows))


def _stratified(pool: list[Candidate], n: int) -> list[Candidate]:
    """Round-robin across door styles for a diverse, deterministic pick."""
    by_style: dict[str, list[Candidate]] = {}
    for c in pool:
        by_style.setdefault(c.door_style or "unknown", []).append(c)
    for group in by_style.values():
        group.sort(key=lambda c: c.key)
    groups = sorted(by_style.values(), key=len, reverse=True)
    picked: list[Candidate] = []
    while len(picked) < n and any(groups):
        for group in groups:
            if group and len(picked) < n:
                picked.append(group.pop(0))
    return picked


def curate_sample(candidates: list[Candidate], target: int) -> list[Candidate]:
    """Small calibration subset: only sample-photo candidates, half presumed
    rejects (scarce, valuable) and half presumed accepts, spread across styles."""
    judgeable = [c for c in candidates if c.sample_path is not None]
    rejects = [c for c in judgeable if c.presumed == "reject"]
    accepts = [c for c in judgeable if c.presumed == "accept"]
    half = target // 2
    picked_rejects = _stratified(rejects, half)
    return picked_rejects + _stratified(accepts, target - len(picked_rejects))


def build_sample_site(sampled: list[Candidate], labels: LabelStore, page_size: int = 30) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    chunks = [sampled[i : i + page_size] for i in range(0, len(sampled), page_size)]
    index_rows: list[tuple[str, str, int, int]] = []
    for n, chunk in enumerate(chunks, 1):
        name = f"Calibration sample — page {n} of {len(chunks)}"
        page = render_project_sheet(name, chunk, labels, _thumb_urls_for(chunk))
        (SITE_DIR / f"project_sample-{n}.html").write_text(page)
        labeled = sum(1 for c in chunk if labels.get(c.key) is not None)
        index_rows.append((f"sample-{n}", name, labeled, len(chunk)))
    (SITE_DIR / "index.html").write_text(render_index(index_rows))


class LabelHandler(SimpleHTTPRequestHandler):
    store: LabelStore  # set on the class before serving
    store_lock = threading.Lock()  # ThreadingHTTPServer: serialize store writes

    def do_POST(self) -> None:  # noqa: N802 (stdlib API name)
        if self.path != "/label":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            with self.store_lock:
                self.store.set(parse_label_post(raw))
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            self.send_error(400, str(exc))
            return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: object) -> None:  # keep the terminal quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--project", help="rebuild/serve only this project id")
    parser.add_argument(
        "--sample", type=int, default=0,
        help="serve a curated calibration subset of ~N images instead of all projects",
    )
    args = parser.parse_args()

    labels = LabelStore(QA_DIR / "labels.json")
    candidates = walk_corpus(Path("output/.projects"), Path("swatches"))
    if args.project:
        candidates = [c for c in candidates if c.project_id == args.project]
    if args.sample:
        sampled = curate_sample(candidates, args.sample)
        print(f"Building curated sample of {len(sampled)} images...")
        build_sample_site(sampled, labels)
    else:
        print(f"Building site for {len(candidates)} images (thumbnails cached across runs)...")
        build_site(candidates, labels)

    LabelHandler.store = labels
    handler = partial(LabelHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Labeling UI: http://127.0.0.1:{args.port}/index.html  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
