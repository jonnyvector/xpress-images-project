"""Serve the calibration labeling UI.

Usage:
    uv run python scripts/qa_label.py [--port 8777] [--project PROJECT_ID]

Builds a static site under output/.qa/site/ (thumbnails cached across runs), then serves
it locally. Accept/Reject clicks persist immediately to output/.qa/labels.json.
"""

import argparse
import json
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.qa.corpus import Candidate, walk_corpus
from backend.qa.labels import Label, LabelStore
from backend.qa.sheet import render_index, render_project_sheet
from backend.qa.thumbs import export_thumb

QA_DIR = Path("output/.qa")
SITE_DIR = QA_DIR / "site"
THUMBS_DIR = SITE_DIR / "thumbs"


def build_site(candidates: list[Candidate], labels: LabelStore) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    by_project: dict[str, list[Candidate]] = {}
    names: dict[str, str] = {}
    for c in candidates:
        by_project.setdefault(c.project_id, []).append(c)
        names[c.project_id] = c.project_name

    index_rows: list[tuple[str, str, int, int]] = []
    for pid, cands in sorted(by_project.items(), key=lambda kv: names[kv[0]].lower()):
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
        page = render_project_sheet(names[pid], cands, labels, thumb_urls)
        (SITE_DIR / f"project_{pid}.html").write_text(page)
        labeled = sum(1 for c in cands if labels.get(c.key) is not None)
        index_rows.append((pid, names[pid], labeled, len(cands)))
    (SITE_DIR / "index.html").write_text(render_index(index_rows))


class LabelHandler(SimpleHTTPRequestHandler):
    store: LabelStore  # set on the class before serving

    def do_POST(self) -> None:  # noqa: N802 (stdlib API name)
        if self.path != "/label":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length))
        self.store.set(
            Label(key=data["key"], verdict=data["verdict"], reasons=data.get("reasons", []))
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: object) -> None:  # keep the terminal quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--project", help="rebuild/serve only this project id")
    args = parser.parse_args()

    labels = LabelStore(QA_DIR / "labels.json")
    candidates = walk_corpus(Path("output/.projects"), Path("swatches"))
    if args.project:
        candidates = [c for c in candidates if c.project_id == args.project]
    print(f"Building site for {len(candidates)} images (thumbnails cached across runs)...")
    build_site(candidates, labels)

    LabelHandler.store = labels
    handler = partial(LabelHandler, directory=str(SITE_DIR))
    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"Labeling UI: http://127.0.0.1:{args.port}/index.html  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
