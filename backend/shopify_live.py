"""Live Shopify product image status, read through the Shopify CLI.

Replaces the hand-exported product CSV. The CLI (`shopify store execute`) owns
the store login, so this module never sees or stores a token: when the login
lapses, the operator re-runs scripts/shopauth.sh.

Per variant, the image is classified as:
  ai        - an image exported by this tool for THIS variant's wood
  mismatch  - an image exported by this tool, but of another variant's wood
  photo     - any other image (supplier photography, older PNGs)
  none      - no image
Exports are named f"{project.name}_{wood}.png" (routers/projects_media.py), so
"ends with this variant's wood name" identifies them. Measured on the live
store (Oct 2026): 3,810 ai, 70 mismatch, 11,802 photo, 5,642 none.

Read-only: the query has no mutations and the CLI runs without
--allow-mutations, so the CLI itself refuses any write.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

STORE_DOMAIN = "bcr-cabinets.myshopify.com"
ADMIN_PRODUCTS_URL = f"https://admin.shopify.com/store/{STORE_DOMAIN.split('.')[0]}/products"
SNAPSHOT_FILENAME = "shopify_live.json"
# Option names that hold the wood/colour in this store, in priority order.
WOOD_OPTION_NAMES = ("Wood Type", "Color")

# 100 products x 250 variants per page stays under Shopify's query cost limit.
PRODUCTS_QUERY = """
query Products($after: String) {
  products(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      handle
      title
      status
      variantsCount { count }
      variants(first: 250) {
        nodes { title selectedOptions { name value } image { url } }
      }
    }
  }
}
"""

_UUID_SUFFIX = re.compile(r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Tool-specific tails after the wood name: "(New Sample)" swatches and " (2)" dedupe.
_EXPORT_TAIL = re.compile(r"(_new_sample)?(_\d+)?$")


class ShopifyCliError(Exception):
    """The Shopify CLI failed. needs_auth=True means re-run scripts/shopauth.sh."""

    def __init__(self, message: str, needs_auth: bool = False):
        super().__init__(message)
        self.needs_auth = needs_auth


Runner = Callable[[str, dict], dict]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _image_stem(url: str) -> tuple[str, str]:
    """Normalized filename stem and lowercase extension of a Shopify CDN URL."""
    name = urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
    base, _, ext = name.rpartition(".")
    base = _UUID_SUFFIX.sub("", base)  # Shopify's dedupe suffix on re-uploads
    return _EXPORT_TAIL.sub("", _norm(base)), ext.lower()


# Words that differ between the tool's swatch names and the store's option
# values ("Red Oak Rift" vs "Red Oak Rift Sawn", "MDF Panel w/ ...").
_FILLER_WORDS = {"w", "sawn"}


def _wood_tokens(text: str) -> list[str]:
    text = re.sub(r"\([^)]*\)", " ", text)  # "949W White (Smooth)" -> "949W White"
    return [t for t in _norm(text).split("_") if t and t not in _FILLER_WORDS]


def _names_wood(stem: str, wood: str) -> bool:
    """True when the filename ends with the wood's words, in any order.

    Order-free because names differ ("Birch Natural" vs natural_birch).
    """
    wood_tokens = _wood_tokens(wood)
    stem_tokens = [t for t in stem.split("_") if t and t not in _FILLER_WORDS]
    n = len(wood_tokens)
    return n > 0 and len(stem_tokens) >= n and set(stem_tokens[-n:]) == set(wood_tokens)


def classify_image(url: str | None, own_values: list[str], product_values: list[str]) -> str:
    """Classify one variant image as ai / mismatch / photo / none (see module doc)."""
    if not url:
        return "none"
    stem, ext = _image_stem(url)
    if ext != "png":
        return "photo"
    if any(_names_wood(stem, v) for v in own_values):
        return "ai"
    if any(_names_wood(stem, v) for v in product_values):
        return "mismatch"
    return "photo"


def _wood_of(options: list[dict]) -> str:
    by_name = {o["name"]: o["value"] for o in options}
    for name in WOOD_OPTION_NAMES:
        if name in by_name:
            return by_name[name]
    return options[0]["value"] if options else ""


def summarize_product(node: dict) -> dict:
    """One product's per-wood AI image status.

    A wood counts as done only when every variant of it (e.g. each front style)
    has its own AI image. `fully_imaged` keeps the CSV loader's meaning for
    coverage: every wood is done.
    """
    variants = node["variants"]["nodes"]
    # Only the first 250 variants are fetched; never call a cut-off product done.
    truncated = (node.get("variantsCount") or {}).get("count", 0) > len(variants)
    # Only wood values: a front style ("Routed") or size must never make an image count.
    product_values = sorted({_wood_of(v["selectedOptions"]) for v in variants})
    statuses: dict[str, list[str]] = {}
    for v in variants:
        url = (v.get("image") or {}).get("url")
        wood = _wood_of(v["selectedOptions"])
        statuses.setdefault(wood, []).append(classify_image(url, [wood], product_values))

    ai_woods = [w for w, s in statuses.items() if all(x == "ai" for x in s)]
    mismatched = [w for w, s in statuses.items() if "mismatch" in s]
    # A wood showing another wood's image is reported once, as mismatched.
    missing = [w for w in statuses if w not in ai_woods and w not in mismatched]
    return {
        "handle": node["handle"],
        "title": node["title"],
        "status": node.get("status", "ACTIVE"),
        "wood_count": len(statuses),
        "ai_wood_count": len(ai_woods),
        "missing_woods": missing,
        "mismatched_woods": mismatched,
        "fully_imaged": bool(statuses) and not truncated and len(ai_woods) == len(statuses),
    }


def run_cli(query: str, variables: dict, store: str = STORE_DOMAIN) -> dict:
    """Run one read-only GraphQL query through `shopify store execute`."""
    exe = shutil.which("shopify")
    if exe is None:
        raise ShopifyCliError("Shopify CLI not found. Install it: npm install -g @shopify/cli")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        try:
            proc = subprocess.run(
                [
                    exe,
                    "store",
                    "execute",
                    "--store",
                    store,
                    "--no-input",
                    "--json",
                    "--output-file",
                    str(out),
                    "--query",
                    query,
                    "--variables",
                    json.dumps(variables),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise ShopifyCliError("Shopify CLI timed out after 120s") from exc
        if proc.returncode == 0 and out.exists():
            try:
                return json.loads(out.read_text())
            except ValueError as exc:
                raise ShopifyCliError(f"Shopify CLI returned unreadable output: {exc}") from exc
    raise _cli_error(proc.stdout + "\n" + proc.stderr)


# The CLI's own wording when its store login is missing or lapsed. Kept narrow
# so cost/throttle errors mentioning "token" aren't mistaken for a lapsed login.
_AUTH_PHRASES = (
    "no stored app authentication",
    "shopify store auth",
    "token has expired",
    "token expired",
    "re-authenticate",
)


def _cli_error(output: str) -> ShopifyCliError:
    """Turn the CLI's JSON error line (or raw text) into a ShopifyCliError."""
    message = output.strip()[-500:] or "Shopify CLI failed with no output"
    next_steps = ""
    for line in output.splitlines():
        try:
            err = json.loads(line).get("error")
        except (ValueError, AttributeError):
            continue
        if isinstance(err, dict):
            message = err.get("message") or message
            next_steps = " ".join(str(step) for step in err.get("nextSteps") or [])
            break
    lowered = f"{message} {next_steps}".lower()
    needs_auth = any(phrase in lowered for phrase in _AUTH_PHRASES)
    return ShopifyCliError(message, needs_auth=needs_auth)


def fetch_products(runner: Runner = run_cli) -> list[dict]:
    """Every product in the store, summarized, following pagination."""
    products: list[dict] = []
    after: str | None = None
    while True:
        result = runner(PRODUCTS_QUERY, {"after": after})
        page = result.get("products") if isinstance(result, dict) else None
        if not isinstance(page, dict):
            detail = result.get("errors") if isinstance(result, dict) else result
            raise ShopifyCliError(f"Unexpected Shopify response: {str(detail)[:300]}")
        products.extend(summarize_product(n) for n in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return products
        after = page["pageInfo"]["endCursor"]


def drop_archived(products: list[dict]) -> list[dict]:
    """Archived listings aren't on the storefront, whatever their images."""
    return [p for p in products if p.get("status") != "ARCHIVED"]


def save_snapshot(data_dir: Path, products: list[dict]) -> dict:
    """Write atomically (same pattern as signoff.save_signoff)."""
    snapshot = {"fetched_at": datetime.now(UTC).isoformat(), "products": products}
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f)
        os.replace(tmp, data_dir / SNAPSHOT_FILENAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return snapshot


def load_snapshot(data_dir: Path) -> dict | None:
    """The last saved live snapshot, or None if never synced or unreadable."""
    path = data_dir / SNAPSHOT_FILENAME
    try:
        snapshot = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("products"), list):
        return None
    return snapshot
