"""Live Shopify product image status, read through the Shopify CLI.

Replaces the hand-exported product CSV. The CLI (`shopify store execute`) owns
the store login, so this module never sees or stores a token: when the login
lapses, the operator re-runs scripts/shopauth.sh.

A product is fully imaged when every variant has an image and no image is
reused across many variants. Old supplier photos sit on 4-27 variants of a
product; AI images are one per variant, or occasionally shared by a pair of
look-alike options (MDF Panel w/ Maple Paint Grade Frame + Maple Paint Grade,
Satin White + Satin Antique White). Measured on the live store (Oct 2026):
every reused image is on exactly 2 variants or on 4+. Shopify's dedupe suffix
on re-uploads is ignored, so one photo uploaded twice still counts as reused.

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
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

STORE_DOMAIN = "bcr-cabinets.myshopify.com"
ADMIN_PRODUCTS_URL = f"https://admin.shopify.com/store/{STORE_DOMAIN.split('.')[0]}/products"
SNAPSHOT_FILENAME = "shopify_live.json"

# 100 products x 250 variants per page stays under Shopify's query cost limit.
PRODUCTS_QUERY = """
query Products($after: String) {
  products(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      handle
      title
      status
      variantsCount { count }
      variants(first: 250) {
        nodes { id title selectedOptions { name value } image { url } }
      }
    }
  }
}
"""

# More variants than this on one image file marks it as an old shared photo.
MAX_VARIANTS_PER_IMAGE = 3

_UUID_SUFFIX = re.compile(r"_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ShopifyCliError(Exception):
    """The Shopify CLI failed. needs_auth=True means re-run scripts/shopauth.sh."""

    def __init__(self, message: str, needs_auth: bool = False):
        super().__init__(message)
        self.needs_auth = needs_auth


Runner = Callable[[str, dict], dict]


def _image_file(url: str | None) -> str | None:
    """Image filename without Shopify's re-upload suffix, or None if no image."""
    if not url:
        return None
    name = urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
    base, dot, ext = name.rpartition(".")
    if not dot:
        base, ext = name, ""
    return f"{_UUID_SUFFIX.sub('', base).lower()}.{ext.lower()}"


def numeric_id(gid: str | None) -> str:
    """'gid://shopify/ProductVariant/123' -> '123' (the id ShopifyQL reports use)."""
    return (gid or "").rsplit("/", 1)[-1]


def image_state(file: str | None, uses: Counter) -> str:
    """'own' (an AI image), 'shared' (old photo on many variants) or 'none'."""
    if not file:
        return "none"
    return "shared" if uses[file] > MAX_VARIANTS_PER_IMAGE else "own"


def summarize_product(node: dict) -> dict:
    """One product's variant image status (see module doc)."""
    variants = node["variants"]["nodes"]
    # Only the first 250 variants are fetched; never call a cut-off product done.
    truncated = (node.get("variantsCount") or {}).get("count", 0) > len(variants)
    urls = [(v.get("image") or {}).get("url") for v in variants]
    files = [_image_file(url) for url in urls]
    uses = Counter(f for f in files if f)
    states = [image_state(f, uses) for f in files]
    missing = [v["title"] for v, st in zip(variants, states, strict=True) if st == "none"]
    shared = [v["title"] for v, st in zip(variants, states, strict=True) if st == "shared"]
    own = states.count("own")
    return {
        "id": numeric_id(node.get("id")),
        "handle": node["handle"],
        "title": node["title"],
        "status": node.get("status", "ACTIVE"),
        "variant_count": len(variants),
        "own_image_count": own,
        "missing_variants": missing,
        "shared_variants": shared,
        "fully_imaged": bool(variants) and not truncated and own == len(variants),
        "variants": [
            {
                "id": numeric_id(v.get("id")),
                "title": v["title"],
                "options": {o["name"]: o["value"] for o in v.get("selectedOptions") or []},
                "image_url": url,
                "image_state": st,
            }
            for v, url, st in zip(variants, urls, states, strict=True)
        ],
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


SALES_DAYS = 365
# ShopifyQL rows are capped by LIMIT; the whole store is ~8k variant rows a year.
_SALES_LIMIT = 50000
SALES_QUERY = """
query Sales($q: String!) {
  shopifyqlQuery(query: $q) { tableData { rows } parseErrors }
}
"""


def fetch_sales(runner: Runner = run_cli) -> dict:
    """Units and net sales per variant and per product over the last year.

    Needs the read_reports scope. Product totals include variants that have
    since been deleted, so they can exceed the sum of today's variants.
    """
    ql = (
        "FROM sales SHOW net_items_sold, net_sales "
        "GROUP BY product_id, product_variant_id "
        f"SINCE -{SALES_DAYS}d UNTIL today LIMIT {_SALES_LIMIT}"
    )
    result = runner(SALES_QUERY, {"q": ql})
    data = result.get("shopifyqlQuery") if isinstance(result, dict) else None
    if not isinstance(data, dict) or data.get("parseErrors") or not data.get("tableData"):
        detail = (data or {}).get("parseErrors") if isinstance(data, dict) else result
        raise ShopifyCliError(f"Unexpected Shopify sales response: {str(detail)[:300]}")
    rows = data["tableData"]["rows"]
    if len(rows) >= _SALES_LIMIT:
        raise ShopifyCliError("Shopify sales report hit its row limit; totals would be short.")
    by_variant: dict[str, list[float]] = {}
    by_product: dict[str, list[float]] = {}
    for row in rows:
        units, net = int(float(row.get("net_items_sold") or 0)), float(row.get("net_sales") or 0)
        keyed = ((row.get("product_variant_id"), by_variant), (row.get("product_id"), by_product))
        for key, totals in keyed:
            if key and key != "0":
                entry = totals.setdefault(str(key), [0, 0.0])
                entry[0] += units
                entry[1] += net
    return {"days": SALES_DAYS, "by_variant": by_variant, "by_product": by_product}


def drop_archived(products: list[dict]) -> list[dict]:
    """Archived listings aren't on the storefront, whatever their images."""
    return [p for p in products if p.get("status") != "ARCHIVED"]


def save_snapshot(
    data_dir: Path,
    products: list[dict],
    sales: dict | None = None,
    sales_error: str | None = None,
) -> dict:
    """Write atomically (same pattern as signoff.save_signoff)."""
    snapshot = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "products": products,
        "sales": sales,
        "sales_error": sales_error,
    }
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


_snapshot_cache: dict[Path, tuple[tuple[int, int], dict]] = {}


def load_snapshot(data_dir: Path) -> dict | None:
    """The last saved live snapshot, or None if never synced or unreadable.

    Memoized on the file's mtime and size: save_snapshot replaces the file
    atomically, so any new save is a new key. Callers must not mutate it.
    """
    path = data_dir / SNAPSHOT_FILENAME
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = _snapshot_cache.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        snapshot = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("products"), list):
        return None
    _snapshot_cache[path] = (stamp, snapshot)
    return snapshot
