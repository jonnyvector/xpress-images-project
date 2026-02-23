"""Streamlit UI for cabinet door image generation with multi-tab support."""

import io
import json
import os
import uuid
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv(override=True)
from PIL import Image

from generator import STYLES, DoorGenerator, add_watermark

# Page config
st.set_page_config(
    page_title="Cabinet Door & Drawer Generator",
    page_icon=":wood:",
    layout="wide",
)

# Responsive CSS for medium-small screens
st.markdown(
    """
    <style>
    /* Stack columns on smaller screens */
    @media (max-width: 1200px) {
        [data-testid="stHorizontalBlock"] {
            flex-direction: column;
        }
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
    }
    /* Reduce padding on smaller screens */
    @media (max-width: 768px) {
        .block-container {
            padding: 1rem !important;
        }
        h1 { font-size: 1.75rem !important; }
        h2 { font-size: 1.25rem !important; }
    }
    /* Swatch grid adjustments */
    @media (max-width: 600px) {
        [data-testid="stImage"] {
            max-width: 100% !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Constants
SWATCHES_DIR = Path("swatches")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers: swatch/wood lookups (unchanged)
# ---------------------------------------------------------------------------


def get_swatch_files() -> list[Path]:
    """Get all image files from the swatches directory."""
    if not SWATCHES_DIR.exists():
        return []
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    return sorted([f for f in SWATCHES_DIR.iterdir() if f.suffix.lower() in extensions])


def load_wood_types() -> dict[str, dict]:
    """Load wood type metadata from JSON file."""
    json_path = SWATCHES_DIR / "wood_types.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def get_wood_description(swatch_path: Path, wood_types: dict[str, dict]) -> str | None:
    """Get description for a wood type by matching swatch filename to JSON key."""
    key = swatch_path.stem.lower().replace("_", "-")
    if key in wood_types:
        return wood_types[key].get("description") or None
    return None


def get_reference_image_by_key(key: str) -> Path | None:
    """Find a reference door image by wood type key in swatches/references/."""
    key_underscore = key.replace("-", "_")
    ref_dir = Path("swatches/references")
    if not ref_dir.exists():
        return None
    for prefix in ("door-", "door_"):
        for k in (key, key_underscore):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                ref_path = ref_dir / f"{prefix}{k}{ext}"
                if ref_path.exists():
                    return ref_path
    return None


def get_reference_image(swatch_path: Path) -> Path | None:
    """Find a reference door image for this wood type in swatches/references/."""
    key = swatch_path.stem.lower().replace("_", "-")
    return get_reference_image_by_key(key)


def get_virtual_wood_types(
    wood_types: dict[str, dict], swatch_files: list[Path]
) -> list[tuple[str, dict]]:
    """Get wood types that have a swatch_key but no swatch file of their own."""
    swatch_stems = {f.stem.lower().replace("_", "-") for f in swatch_files}
    return [
        (key, data)
        for key, data in wood_types.items()
        if data.get("swatch_key") and key not in swatch_stems
    ]


def resolve_swatch_path(swatch_key: str, swatch_files: list[Path]) -> Path | None:
    """Find a swatch file matching a key."""
    for f in swatch_files:
        if f.stem.lower().replace("_", "-") == swatch_key:
            return f
    return None


def swatch_name_from_path(path: Path) -> str:
    """Extract a display name from swatch file path."""
    return path.stem.replace("_", " ").replace("-", " ").title()


def create_zip(results: list[tuple[str, bytes]], door_name: str) -> bytes:
    """Create a ZIP file from generation results."""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for wood_name, image_data in results:
            filename = f"{door_name}_{wood_name.lower().replace(' ', '_')}.png"
            zf.writestr(filename, add_watermark(image_data, wood_name))
    return zip_buffer.getvalue()


# ---------------------------------------------------------------------------
# Session persistence (survives full page reload)
# ---------------------------------------------------------------------------

PERSIST_DIR = OUTPUT_DIR / ".session"


def _save_session() -> None:
    """Persist tab state to disk so it survives page reloads."""
    if "tab_ids" not in st.session_state:
        return
    PERSIST_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "tab_ids": st.session_state.tab_ids,
        "tab_labels": dict(st.session_state.tab_labels),
        "next_tab_number": st.session_state.next_tab_number,
        "tabs": {},
    }

    for tab_id in st.session_state.tab_ids:
        ts = st.session_state.tabs[tab_id]

        # Write binary blobs to individual files
        for blob_key, suffix in [
            ("uploaded_file_bytes", "upload"),
            ("learned_signature", "signature"),
            ("base_door_image", "base_door"),
        ]:
            data = ts.get(blob_key)
            path = PERSIST_DIR / f"{tab_id}_{suffix}.bin"
            if data is not None:
                path.write_bytes(data)
            elif path.exists():
                path.unlink()

        # Write generation result images
        results = ts.get("generation_results", [])
        result_names = []
        for idx, (wood_name, image_data) in enumerate(results):
            (PERSIST_DIR / f"{tab_id}_result_{idx}.bin").write_bytes(image_data)
            result_names.append(wood_name)
        # Clean up stale result files
        stale_idx = len(results)
        while (PERSIST_DIR / f"{tab_id}_result_{stale_idx}.bin").exists():
            (PERSIST_DIR / f"{tab_id}_result_{stale_idx}.bin").unlink()
            stale_idx += 1

        manifest["tabs"][tab_id] = {
            "uploaded_file_name": ts.get("uploaded_file_name"),
            "door_name": ts.get("door_name"),
            "door_style": ts.get("door_style"),
            "product_type": ts.get("product_type", "Cabinet Door"),
            "selected_swatches": ts.get("selected_swatches", []),
            "style_notes": ts.get("style_notes", ""),
            "aspect_ratio": ts.get("aspect_ratio"),
            "result_names": result_names,
            "generation_errors": ts.get("generation_errors", []),
        }

    (PERSIST_DIR / "manifest.json").write_text(json.dumps(manifest))


def _load_session() -> bool:
    """Restore tab state from disk. Returns True if state was restored."""
    manifest_path = PERSIST_DIR / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    tab_ids = manifest.get("tab_ids", [])
    if not tab_ids:
        return False

    st.session_state.tab_ids = tab_ids
    st.session_state.tab_labels = manifest.get("tab_labels", {})
    st.session_state.next_tab_number = manifest.get("next_tab_number", 1)
    st.session_state.tabs = {}

    for tab_id in tab_ids:
        saved = manifest.get("tabs", {}).get(tab_id, {})
        ts = _default_tab_state()

        # Restore scalar fields
        for key in (
            "uploaded_file_name",
            "door_name",
            "door_style",
            "product_type",
            "selected_swatches",
            "style_notes",
            "aspect_ratio",
            "generation_errors",
        ):
            if saved.get(key) is not None:
                ts[key] = saved[key]

        # Restore binary blobs
        for blob_key, suffix in [
            ("uploaded_file_bytes", "upload"),
            ("learned_signature", "signature"),
            ("base_door_image", "base_door"),
        ]:
            path = PERSIST_DIR / f"{tab_id}_{suffix}.bin"
            if path.exists():
                ts[blob_key] = path.read_bytes()

        # Restore generation results
        result_names = saved.get("result_names", [])
        results = []
        for idx, wood_name in enumerate(result_names):
            path = PERSIST_DIR / f"{tab_id}_result_{idx}.bin"
            if path.exists():
                results.append((wood_name, path.read_bytes()))
        ts["generation_results"] = results

        st.session_state.tabs[tab_id] = ts

    return True


def _clear_persisted_session() -> None:
    """Remove all persisted session files."""
    if PERSIST_DIR.exists():
        for f in PERSIST_DIR.iterdir():
            f.unlink(missing_ok=True)
        PERSIST_DIR.rmdir()


# ---------------------------------------------------------------------------
# Tab state management
# ---------------------------------------------------------------------------


def _default_tab_state() -> dict:
    """Return a fresh per-tab state dict."""
    return {
        "learned_signature": None,
        "base_door_image": None,
        "generation_results": [],
        "generation_errors": [],
        "door_name": None,
        "door_style": None,
        "product_type": "Cabinet Door",
        "selected_swatches": [],
        # Cached upload (survives st.rerun widget-tree rebuild)
        "uploaded_file_bytes": None,
        "uploaded_file_name": None,
        # Background generation
        "generation_running": False,
        "generation_future": None,
        # Background learn
        "learn_running": False,
        "learn_future": None,
    }


def add_tab() -> str:
    """Add a new tab and return its ID."""
    tab_id = uuid.uuid4().hex[:8]
    st.session_state.tab_ids.append(tab_id)
    tab_num = st.session_state.next_tab_number
    st.session_state.next_tab_number = tab_num + 1
    st.session_state.tab_labels[tab_id] = f"Door {tab_num}"
    st.session_state.tabs[tab_id] = _default_tab_state()
    return tab_id


def remove_tab(tab_id: str) -> None:
    """Remove a tab by ID (cancel any running futures)."""
    ts = st.session_state.tabs.get(tab_id, {})
    for key in ("generation_future", "learn_future"):
        future = ts.get(key)
        if future and not future.done():
            future.cancel()
    st.session_state.tab_ids.remove(tab_id)
    st.session_state.tab_labels.pop(tab_id, None)
    st.session_state.tabs.pop(tab_id, None)
    # Clean up persisted files for this tab
    if PERSIST_DIR.exists():
        for f in PERSIST_DIR.glob(f"{tab_id}_*"):
            f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Background generation worker (runs in thread — no session state access)
# ---------------------------------------------------------------------------


def _run_generation_worker(
    api_key: str,
    base_signature: bytes,
    door_style: str,
    selections: list[dict],
    aspect_ratio: str = "9:16",
    style_notes: str = "",
) -> tuple[list[tuple[str, bytes]], list[tuple[str, str]]]:
    """Generate variations in a background thread.

    Returns (successful, failed) lists.
    """
    generator = DoorGenerator(api_key=api_key)
    successful: list[tuple[str, bytes]] = []
    failed: list[tuple[str, str]] = []

    def _generate_one(sel: dict) -> tuple[str, object]:
        wood_name = sel["wood_name"]
        result = generator.generate_variation(
            swatch_image_path=sel["swatch_path"],
            wood_name=wood_name,
            base_signature=base_signature,
            wood_description=sel["wood_description"],
            reference_image_path=sel["reference_image"],
            door_style=door_style,
            aspect_ratio=aspect_ratio,
            style_notes=style_notes,
        )
        return wood_name, result

    max_parallel = min(len(selections), 4)
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(_generate_one, sel): sel for sel in selections}
        for future in as_completed(futures):
            wood_name, result = future.result()
            if result.image_data:
                successful.append((wood_name, result.image_data))
            else:
                failed.append((wood_name, result.error or "Unknown error"))

    return successful, failed


def _run_learn_worker(
    api_key: str,
    file_bytes: bytes,
    file_name: str,
    door_style_name: str,
    door_style: str,
    aspect_ratio: str,
) -> object:
    """Learn a door style in a background thread.

    Manages its own temp file lifecycle. Returns a GenerationResult.
    """
    import tempfile

    tmp_path = None
    try:
        suffix = Path(file_name).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        generator = DoorGenerator(api_key=api_key)
        return generator.learn_door_style(
            tmp_path,
            door_style_name=door_style_name,
            door_style=door_style,
            aspect_ratio=aspect_ratio,
        )
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Build the selection list from selected swatch keys
# ---------------------------------------------------------------------------


def _build_selections(selected_swatches: list[str]) -> list[dict]:
    """Build the selections list from selected swatch keys."""
    wood_types = load_wood_types()
    all_swatch_files = get_swatch_files()
    selections: list[dict] = []
    for p in selected_swatches:
        if p.startswith("virtual:"):
            key = p[8:]
            wt = wood_types.get(key, {})
            borrowed = resolve_swatch_path(wt.get("swatch_key", ""), all_swatch_files)
            selections.append(
                {
                    "wood_name": wt.get("name", key),
                    "swatch_path": borrowed,
                    "text_prompt": None,
                    "wood_description": wt.get("description"),
                    "reference_image": None,
                }
            )
        else:
            swatch_path = Path(p)
            # If the stored path doesn't exist, try resolving it as a key
            if not swatch_path.exists():
                # Try the raw value as a key (e.g. "alder-natural")
                key = p.lower().replace("_", "-")
                resolved = resolve_swatch_path(key, all_swatch_files)
                if not resolved:
                    # Also try the stem in case it has a directory prefix
                    resolved = resolve_swatch_path(
                        swatch_path.stem.lower().replace("_", "-"),
                        all_swatch_files,
                    )
                if resolved:
                    swatch_path = resolved
                else:
                    continue  # skip missing swatches
            selections.append(
                {
                    "wood_name": swatch_name_from_path(swatch_path),
                    "swatch_path": swatch_path,
                    "text_prompt": None,
                    "wood_description": get_wood_description(swatch_path, wood_types),
                    "reference_image": None,
                }
            )
    return selections


# ---------------------------------------------------------------------------
# Render a single tab
# ---------------------------------------------------------------------------


def render_tab(tab_id: str, api_key: str) -> None:
    """Render the full workflow for one tab."""
    ts = st.session_state.tabs[tab_id]

    # --- Tab header with close button ---
    if len(st.session_state.tab_ids) > 1:
        hdr_cols = st.columns([4, 1])
        with hdr_cols[1]:
            if st.button("Close Tab", key=f"{tab_id}_close", width="stretch"):
                remove_tab(tab_id)
                st.rerun()

    # Main layout: two columns
    col_left, col_right = st.columns([1, 2])

    with col_left:
        _render_upload_and_learn(tab_id, ts, api_key)
        _render_swatch_selection(tab_id, ts)

    with col_right:
        _render_generation(tab_id, ts, api_key)
        _render_results(tab_id, ts)


# ---------------------------------------------------------------------------
# Step 1: Upload & Learn Style
# ---------------------------------------------------------------------------


def _render_upload_and_learn(tab_id: str, ts: dict, api_key: str) -> None:
    st.header("1. Upload & Learn Style")

    product_type = st.radio(
        "Product type",
        ["Cabinet Door", "Drawer Front"],
        index=0 if ts.get("product_type", "Cabinet Door") == "Cabinet Door" else 1,
        horizontal=True,
        key=f"{tab_id}_product_type_radio",
    )
    ts["product_type"] = product_type
    is_drawer = product_type == "Drawer Front"
    category = "drawer" if is_drawer else "door"
    upload_label = "drawer front" if is_drawer else "door"

    uploaded_door = st.file_uploader(
        f"Choose a {upload_label} image",
        type=["jpg", "jpeg", "png", "webp"],
        key=f"{tab_id}_door_upload",
    )

    # Cache uploaded bytes so they survive st.rerun() widget-tree rebuilds
    if uploaded_door is not None:
        ts["uploaded_file_bytes"] = uploaded_door.getvalue()
        ts["uploaded_file_name"] = uploaded_door.name
    file_bytes = ts["uploaded_file_bytes"]
    file_name = ts["uploaded_file_name"]

    if file_bytes:
        # --- Harvest completed background learn ---
        learn_future: Future | None = ts.get("learn_future")
        if learn_future is not None and learn_future.done():
            try:
                result = learn_future.result()
            except Exception as exc:
                result = None
                st.error(f"Learn failed: {exc}")
            ts["learn_future"] = None
            ts["learn_running"] = False
            if result is not None:
                if result.error:
                    st.error(f"Failed: {result.error}")
                elif result.thought_signature:
                    ts["learned_signature"] = result.thought_signature
                    ts["base_door_image"] = result.image_data
                    # Restore form values from pending snapshots
                    ts["door_name"] = ts.pop("_pending_door_name", ts.get("door_name"))
                    ts["door_style"] = ts.pop("_pending_door_style", ts.get("door_style"))
                    ts["style_notes"] = ts.pop("_pending_style_notes", ts.get("style_notes", ""))
                    ts["aspect_ratio"] = ts.pop(
                        "_pending_aspect_ratio", ts.get("aspect_ratio")
                    )
                    ts["generation_results"] = []
                    ts["generation_errors"] = []
                    st.session_state.tab_labels[tab_id] = ts["door_name"] or "Door"
                    st.success("Style learned!")
                    st.rerun()

        is_learning = ts.get("learn_running", False)

        # --- Show polling fragment while learn is in progress ---
        if is_learning:

            @st.fragment(run_every=3.0)
            def _poll_learn():
                f: Future | None = ts.get("learn_future")
                if f is not None and f.done():
                    st.rerun()
                else:
                    st.info(f"Learning {upload_label} style in the background...")

            _poll_learn()

        st.image(file_bytes, caption=f"Your {upload_label.title()}", width="stretch")
        door_name = st.text_input(
            "Style name",
            value=Path(file_name).stem,
            help="Used for output filenames",
            key=f"{tab_id}_door_name",
        )

        # Style selector filtered by product type
        style_keys = [k for k, v in STYLES.items() if v["category"] == category]
        style_names = [STYLES[k]["name"] for k in style_keys]
        selected_style_idx = st.selectbox(
            "Style type",
            options=range(len(style_keys)),
            format_func=lambda i, _names=style_names: _names[i],
            index=0,
            help=f"Select the type of {upload_label} you're generating",
            key=f"{tab_id}_style_type",
        )
        selected_door_style = style_keys[selected_style_idx]

        style_notes = st.text_area(
            "Style notes (optional)",
            value=ts.get("style_notes", ""),
            help="Describe distinctive structural features to preserve across variations, "
            'e.g. "center stile dividing two recessed panels side by side"',
            key=f"{tab_id}_style_notes",
            height=68,
        )

        # Learn button
        can_learn = bool(api_key and file_bytes) and not is_learning
        learn_btn = st.button(
            f"Learn {upload_label.title()} Style",
            type="primary" if not ts.get("learned_signature") else "secondary",
            disabled=not can_learn,
            width="stretch",
            key=f"{tab_id}_learn_btn",
        )

        if learn_btn and can_learn:
            aspect_ratio = "16:9" if is_drawer else "9:16"

            # Snapshot form values so they survive the rerun
            ts["_pending_door_name"] = door_name
            ts["_pending_door_style"] = selected_door_style
            ts["_pending_style_notes"] = style_notes.strip()
            ts["_pending_aspect_ratio"] = aspect_ratio

            # Submit to shared executor (non-blocking)
            executor: ThreadPoolExecutor = st.session_state.executor
            future = executor.submit(
                _run_learn_worker,
                api_key,
                file_bytes,
                file_name,
                door_name,
                selected_door_style,
                aspect_ratio,
            )
            ts["learn_future"] = future
            ts["learn_running"] = True
            st.rerun()

        if ts.get("learned_signature"):
            st.success(f"{upload_label.title()} style ready for variations")


# ---------------------------------------------------------------------------
# Step 2: Select Wood Types
# ---------------------------------------------------------------------------


def _render_swatch_selection(tab_id: str, ts: dict) -> None:
    st.header("2. Select Wood Types")

    swatch_files = get_swatch_files()
    wood_types = load_wood_types()
    virtual_types = get_virtual_wood_types(wood_types, swatch_files)

    if not swatch_files and not virtual_types:
        st.warning(f"No swatches found. Add wood swatch images to the `{SWATCHES_DIR}` folder.")
        st.info("Supported formats: JPG, PNG, WEBP")
        return

    # Select all / clear buttons
    btn_col1, btn_col2 = st.columns(2)
    all_keys = [str(f) for f in swatch_files] + [f"virtual:{k}" for k, _ in virtual_types]
    if btn_col1.button("Select All", width="stretch", key=f"{tab_id}_select_all"):
        ts["selected_swatches"] = list(all_keys)
        for idx in range(len(swatch_files)):
            st.session_state[f"{tab_id}_swatch_{idx}"] = True
        for key, _ in virtual_types:
            st.session_state[f"{tab_id}_swatch_virtual_{key}"] = True
        st.rerun()
    if btn_col2.button("Clear", width="stretch", key=f"{tab_id}_clear_swatches"):
        ts["selected_swatches"] = []
        for idx in range(len(swatch_files)):
            st.session_state[f"{tab_id}_swatch_{idx}"] = False
        for key, _ in virtual_types:
            st.session_state[f"{tab_id}_swatch_virtual_{key}"] = False
        st.rerun()

    selected_swatches: list[str] = ts.get("selected_swatches", [])

    # Initialize checkbox session state keys on first render
    for idx, swatch in enumerate(swatch_files):
        cb_key = f"{tab_id}_swatch_{idx}"
        if cb_key not in st.session_state:
            st.session_state[cb_key] = str(swatch) in selected_swatches
    for key, _ in virtual_types:
        cb_key = f"{tab_id}_swatch_virtual_{key}"
        if cb_key not in st.session_state:
            st.session_state[cb_key] = f"virtual:{key}" in selected_swatches

    # Display swatches in a grid
    st.markdown("**Available Wood Types:**")
    cols_per_row = 3
    for i in range(0, len(swatch_files), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx < len(swatch_files):
                swatch = swatch_files[idx]
                swatch_key = str(swatch)
                with col:
                    img = Image.open(swatch)
                    st.image(img, width="stretch")
                    selected = st.checkbox(
                        swatch_name_from_path(swatch),
                        key=f"{tab_id}_swatch_{idx}",
                    )
                    if selected and swatch_key not in selected_swatches:
                        selected_swatches.append(swatch_key)
                    elif not selected and swatch_key in selected_swatches:
                        selected_swatches.remove(swatch_key)

    # Display virtual wood types
    if virtual_types:
        st.markdown("**Composite Material Types:**")
        for key, data in virtual_types:
            virtual_key = f"virtual:{key}"
            borrowed_swatch = resolve_swatch_path(data["swatch_key"], swatch_files)
            ref_key = data.get("reference_key", key)
            ref_img = get_reference_image_by_key(ref_key)
            preview_img = ref_img or borrowed_swatch
            t_cols = st.columns([1, 2] if preview_img else [1])
            with t_cols[0]:
                selected = st.checkbox(
                    data["name"],
                    key=f"{tab_id}_swatch_virtual_{key}",
                )
                if selected and virtual_key not in selected_swatches:
                    selected_swatches.append(virtual_key)
                elif not selected and virtual_key in selected_swatches:
                    selected_swatches.remove(virtual_key)
            if preview_img and len(t_cols) > 1:
                with t_cols[1]:
                    st.image(
                        Image.open(preview_img),
                        caption="Reference",
                        width="stretch",
                    )

    ts["selected_swatches"] = selected_swatches
    selected_count = len(selected_swatches)
    total_available = len(swatch_files) + len(virtual_types)
    st.markdown(f"**Selected: {selected_count} / {total_available}**")


# ---------------------------------------------------------------------------
# Step 3: Generate Variations
# ---------------------------------------------------------------------------


def _render_generation(tab_id: str, ts: dict, api_key: str) -> None:
    st.header("3. Generate Variations")

    # --- Harvest completed background generation ---
    future: Future | None = ts.get("generation_future")
    if future is not None and future.done():
        try:
            successful, failed = future.result()
        except Exception as exc:
            successful, failed = [], [("Worker", str(exc))]
        ts["generation_results"] = ts.get("generation_results", []) + successful
        ts["generation_errors"] = ts.get("generation_errors", []) + failed
        ts["generation_future"] = None
        ts["generation_running"] = False

    is_running = ts.get("generation_running", False)

    # --- Show polling fragment while generation is in progress ---
    if is_running:

        @st.fragment(run_every=3.0)
        def _poll_generation():
            f: Future | None = ts.get("generation_future")
            if f is not None and f.done():
                st.rerun()
            else:
                count = len(ts.get("selected_swatches", []))
                st.info(f"Generating {count} variation(s) in the background...")

        _poll_generation()

    has_signature = ts.get("learned_signature") is not None
    has_swatches = bool(ts.get("selected_swatches"))
    can_generate = bool(api_key) and has_signature and has_swatches and not is_running

    if not api_key:
        st.info("Enter your API key in the sidebar")
    elif not has_signature:
        st.info("Learn a style first (Step 1)")
    elif not has_swatches:
        st.info("Select at least one wood type (Step 2)")

    generate_btn = st.button(
        "Generate Variations",
        type="primary",
        disabled=not can_generate,
        width="stretch",
        key=f"{tab_id}_generate_btn",
    )

    if generate_btn and can_generate:
        # Snapshot immutable inputs
        base_signature = ts["learned_signature"]
        door_style = ts.get("door_style", "recessed_panel")
        style_notes = ts.get("style_notes", "")
        selections = _build_selections(ts["selected_swatches"])

        if not selections:
            st.warning("No valid selections to generate.")
            return

        # Submit to shared executor
        executor: ThreadPoolExecutor = st.session_state.executor
        aspect_ratio = ts.get("aspect_ratio", "9:16")
        future = executor.submit(
            _run_generation_worker,
            api_key,
            base_signature,
            door_style,
            selections,
            aspect_ratio,
            style_notes,
        )
        ts["generation_future"] = future
        ts["generation_running"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------


def _render_results(tab_id: str, ts: dict) -> None:
    # Display base image
    if ts.get("base_door_image"):
        is_drawer_result = ts.get("product_type") == "Drawer Front"
        base_label = "Base Drawer Front" if is_drawer_result else "Base Door"
        st.subheader(f"{base_label} (Learned Style)")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(
                add_watermark(ts["base_door_image"]),
                caption="Gemini's interpretation - all variations use this",
                width="stretch",
            )
        st.divider()

    results = ts.get("generation_results", [])
    door_name = ts.get("door_name", "door")

    if results:
        st.subheader(f"Wood Variations ({len(results)})")

        zip_data = create_zip(results, door_name)
        st.download_button(
            "Download All as ZIP" if len(results) > 1 else "Download as ZIP",
            data=zip_data,
            file_name=f"{door_name}_variations.zip",
            mime="application/zip",
            width="stretch",
            key=f"{tab_id}_download_zip",
        )

        cols_per_row = 3
        for i in range(0, len(results), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(results):
                    wood_name, image_data = results[idx]
                    watermarked = add_watermark(image_data, wood_name)
                    with col:
                        st.image(watermarked, caption=wood_name, width="stretch")
                        filename = f"{door_name}_{wood_name.lower().replace(' ', '_')}.png"
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            st.download_button(
                                "Download",
                                data=watermarked,
                                file_name=filename,
                                mime="image/png",
                                key=f"{tab_id}_download_{idx}",
                                width="stretch",
                            )
                        with btn_col2:
                            if st.button(
                                "Discard",
                                key=f"{tab_id}_discard_{idx}",
                                width="stretch",
                            ):
                                ts["generation_results"].pop(idx)
                                st.rerun()

    # Display errors
    if ts.get("generation_errors"):
        with st.expander("Errors", expanded=False):
            for wood_name, error in ts["generation_errors"]:
                st.error(f"**{wood_name}**: {error}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main application."""
    st.title("Cabinet Door & Drawer Generator")
    st.markdown("Generate door and drawer front variations across different wood types")

    # --- Initialize multi-tab session state ---
    if "tab_ids" not in st.session_state:
        st.session_state.executor = ThreadPoolExecutor(max_workers=4)
        if not _load_session():
            st.session_state.tab_ids = []
            st.session_state.tab_labels = {}
            st.session_state.tabs = {}
            st.session_state.next_tab_number = 1
            add_tab()  # start with one default tab

    # --- Sidebar ---
    with st.sidebar:
        st.header("Settings")
        env_api_key = os.environ.get("GEMINI_API_KEY", "")
        ui_api_key = st.text_input(
            "Gemini API Key",
            type="password",
            value=env_api_key,
            help="Your Google Gemini API key. Set GEMINI_API_KEY env var to pre-fill.",
        )
        api_key = ui_api_key or env_api_key
        if api_key and api_key == env_api_key and not ui_api_key:
            st.success("Using API key from environment")
        elif not api_key:
            st.warning("Enter your API key to enable generation")

        st.divider()

        if st.button("Reset All", width="stretch"):
            # Cancel any running futures
            for tid in list(st.session_state.tab_ids):
                for key in ("generation_future", "learn_future"):
                    future = st.session_state.tabs[tid].get(key)
                    if future and not future.done():
                        future.cancel()
            # Clear persisted session and re-initialize
            _clear_persisted_session()
            st.session_state.tab_ids = []
            st.session_state.tab_labels = {}
            st.session_state.tabs = {}
            st.session_state.next_tab_number = 1
            add_tab()
            st.rerun()

    # --- Add New Door button above tabs ---
    if st.button("+ Add New Door", type="secondary"):
        add_tab()
        st.rerun()

    # --- Build tab bar ---
    tab_ids = st.session_state.tab_ids
    labels = [st.session_state.tab_labels[tid] for tid in tab_ids]
    ui_tabs = st.tabs(labels)

    # Render each real tab
    for i, tab_id in enumerate(tab_ids):
        with ui_tabs[i]:
            render_tab(tab_id, api_key)

    # Persist state to disk so it survives page reloads
    _save_session()


if __name__ == "__main__":
    main()
