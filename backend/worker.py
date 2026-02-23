"""Background generation worker."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from backend.generator import DoorGenerator

if TYPE_CHECKING:
    from backend.state import ProjectState, ProjectStore

SWATCHES_DIR = Path("swatches")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

_executor = ThreadPoolExecutor(max_workers=4)

# Global semaphore to limit concurrent Gemini API calls across all projects.
# Prevents rate-limiting (429s) when multiple tabs generate simultaneously.
_api_semaphore = threading.Semaphore(4)


def _get_swatch_files() -> list[Path]:
    if not SWATCHES_DIR.exists():
        return []
    return sorted([f for f in SWATCHES_DIR.iterdir() if f.suffix.lower() in EXTENSIONS])


def _load_wood_types() -> dict[str, dict]:
    json_path = SWATCHES_DIR / "wood_types.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def _resolve_swatch_path(swatch_key: str, swatch_files: list[Path]) -> Path | None:
    for f in swatch_files:
        if f.stem.lower().replace("_", "-") == swatch_key:
            return f
    return None


def _swatch_name_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


def _get_wood_description(swatch_path: Path, wood_types: dict[str, dict]) -> str | None:
    key = swatch_path.stem.lower().replace("_", "-")
    if key in wood_types:
        return wood_types[key].get("description") or None
    return None


def _get_reference_image_by_key(key: str) -> Path | None:
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


def _build_selections(selected_swatches: list[str]) -> list[dict]:
    """Build the selections list from selected swatch keys (ported from app.py)."""
    wood_types = _load_wood_types()
    all_swatch_files = _get_swatch_files()
    selections: list[dict] = []
    for p in selected_swatches:
        if p.startswith("virtual:"):
            key = p[8:]
            wt = wood_types.get(key, {})
            borrowed = _resolve_swatch_path(wt.get("swatch_key", ""), all_swatch_files)
            selections.append(
                {
                    "wood_name": wt.get("name", key),
                    "swatch_path": borrowed,
                    "wood_description": wt.get("description"),
                    "reference_image": None,
                }
            )
        else:
            swatch_path = Path(p)
            # If the stored value doesn't exist as a file, resolve it as a key
            if not swatch_path.exists():
                key = p.lower().replace("_", "-")
                # Check if it's a virtual wood type (has swatch_key in wood_types.json)
                wt = wood_types.get(key, {})
                if wt.get("swatch_key"):
                    borrowed = _resolve_swatch_path(wt["swatch_key"], all_swatch_files)
                    ref_key = wt.get("reference_key", key)
                    selections.append(
                        {
                            "wood_name": wt.get("name", key),
                            "swatch_path": borrowed,
                            "wood_description": wt.get("description"),
                            "reference_image": None,
                        }
                    )
                    continue
                resolved = _resolve_swatch_path(key, all_swatch_files)
                if not resolved:
                    resolved = _resolve_swatch_path(
                        swatch_path.stem.lower().replace("_", "-"),
                        all_swatch_files,
                    )
                if resolved:
                    swatch_path = resolved
                else:
                    continue  # skip missing swatches
            selections.append(
                {
                    "wood_name": _swatch_name_from_path(swatch_path),
                    "swatch_path": swatch_path,
                    "wood_description": _get_wood_description(swatch_path, wood_types),
                    "reference_image": None,
                }
            )
    return selections


def _run_generation(
    store: ProjectStore,
    project_id: str,
    api_key: str,
    base_signature: bytes,
    door_style: str,
    selections: list[dict],
    aspect_ratio: str,
    style_notes: str,
) -> None:
    """Run generation in background thread, updating ProjectState incrementally."""
    try:
        generator = DoorGenerator(api_key=api_key)

        def _generate_one(sel: dict) -> tuple[str, object]:
            wood_name = sel["wood_name"]
            with _api_semaphore:
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
                try:
                    wood_name, result = future.result()
                    project = store.get(project_id)
                    if project is None:
                        return
                    if result.image_data:
                        project.results.append((wood_name, result.image_data))
                    else:
                        project.errors.append(
                            (wood_name, result.error or "Unknown error")
                        )
                    project.generation_completed += 1
                    store.save(project_id)
                except Exception as exc:
                    project = store.get(project_id)
                    if project is None:
                        return
                    sel = futures[future]
                    project.errors.append((sel["wood_name"], str(exc)))
                    project.generation_completed += 1
                    store.save(project_id)
    except Exception as exc:
        # Catch any top-level error so status always gets set to done
        project = store.get(project_id)
        if project is not None:
            project.errors.append(("Generation", str(exc)))
            store.save(project_id)
    finally:
        # Always mark done, even on crash
        project = store.get(project_id)
        if project is not None:
            project.generation_status = "done"
            store.save(project_id)


OUTPUT_DIR = Path("output")


def _run_learn(
    store: ProjectStore,
    project_id: str,
    api_key: str,
    upload_bytes: bytes,
    door_style: str,
    door_style_name: str,
    aspect_ratio: str,
) -> None:
    """Run learn_door_style in background thread."""
    temp_path = OUTPUT_DIR / f"temp_learn_{project_id}.png"
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(upload_bytes)

        generator = DoorGenerator(api_key=api_key)
        with _api_semaphore:
            result = generator.learn_door_style(
                door_image_path=temp_path,
                door_style_name=door_style_name,
                door_style=door_style,
                aspect_ratio=aspect_ratio,
            )

        project = store.get(project_id)
        if project is None:
            return

        if result.error:
            project.learning_status = "error"
            project.learning_error = result.error
        elif result.thought_signature:
            # Archive current signature before overwriting (re-learn)
            if project.has_signature and project.learned_signature:
                store.archive_current_version(project_id)
                # Re-fetch project after archive (version_count updated)
                project = store.get(project_id)
                if project is None:
                    return
            project.learned_signature = result.thought_signature
            project.has_signature = True
            project.base_door_image = result.image_data
            project.results = []
            project.errors = []
            project.generation_status = "idle"
            project.generation_completed = 0
            project.generation_total = 0
            project.signature_version = 0
            project.learning_status = "done"
            project.learning_error = None
        store.save(project_id)
    except Exception as exc:
        project = store.get(project_id)
        if project is not None:
            project.learning_status = "error"
            project.learning_error = str(exc)
            store.save(project_id)
    finally:
        temp_path.unlink(missing_ok=True)


def start_learning(
    store: ProjectStore,
    project: ProjectState,
    api_key: str,
    upload_bytes: bytes,
) -> None:
    """Kick off background learning for a project."""
    is_drawer = project.product_type == "Drawer Front"
    aspect_ratio = "16:9" if is_drawer else "9:16"
    door_style = project.door_style or "recessed_panel"

    project.learning_status = "running"
    project.learning_error = None
    store.save(project.id)

    _executor.submit(
        _run_learn,
        store,
        project.id,
        api_key,
        upload_bytes,
        door_style,
        project.name,
        aspect_ratio,
    )


def _run_retry(
    store: ProjectStore,
    project_id: str,
    api_key: str,
    idx: int,
    base_signature: bytes,
    door_style: str,
    selection: dict,
    aspect_ratio: str,
    style_notes: str,
) -> None:
    """Re-generate a single variation in-place."""
    try:
        generator = DoorGenerator(api_key=api_key)
        wood_name = selection["wood_name"]
        with _api_semaphore:
            result = generator.generate_variation(
                swatch_image_path=selection["swatch_path"],
                wood_name=wood_name,
                base_signature=base_signature,
                wood_description=selection["wood_description"],
                reference_image_path=selection["reference_image"],
                door_style=door_style,
                aspect_ratio=aspect_ratio,
                style_notes=style_notes,
            )
        project = store.get(project_id)
        if project is None:
            return
        if result.image_data:
            project.results[idx] = (wood_name, result.image_data)
        else:
            project.errors.append((wood_name, result.error or "Retry failed"))
    except Exception as exc:
        project = store.get(project_id)
        if project is None:
            return
        project.errors.append((selection["wood_name"], str(exc)))
    finally:
        project = store.get(project_id)
        if project is not None:
            if idx in project.retrying_indices:
                project.retrying_indices.remove(idx)
            store.save(project_id)


def start_retry(
    store: ProjectStore,
    project: ProjectState,
    idx: int,
    api_key: str,
) -> None:
    """Kick off a single-result retry."""
    wood_name = project.results[idx][0]

    # Try to find the matching swatch in selected_swatches
    selection = None
    for swatch_key in project.selected_swatches:
        selections = _build_selections([swatch_key])
        for sel in selections:
            if sel["wood_name"] == wood_name:
                selection = sel
                break
        if selection:
            break

    # Fallback: build a minimal selection from the wood name
    if selection is None:
        selection = {
            "wood_name": wood_name,
            "swatch_path": None,
            "wood_description": None,
            "reference_image": None,
        }

    is_drawer = project.product_type == "Drawer Front"
    aspect_ratio = "16:9" if is_drawer else "9:16"
    door_style = project.door_style or "recessed_panel"

    project.retrying_indices.append(idx)
    store.save(project.id)

    _executor.submit(
        _run_retry,
        store,
        project.id,
        api_key,
        idx,
        project.learned_signature,
        door_style,
        selection,
        aspect_ratio,
        project.style_notes,
    )


def start_generation(
    store: ProjectStore,
    project: ProjectState,
    api_key: str,
) -> None:
    """Kick off background generation for a project."""
    selections = _build_selections(project.selected_swatches)
    if not selections:
        return

    is_drawer = project.product_type == "Drawer Front"
    aspect_ratio = "16:9" if is_drawer else "9:16"
    door_style = project.door_style or "recessed_panel"

    # Keep all existing results — new ones append alongside them
    project.errors = []
    project.generation_status = "running"
    project.generation_completed = 0
    project.generation_total = len(selections)
    store.save(project.id)

    _executor.submit(
        _run_generation,
        store,
        project.id,
        api_key,
        project.learned_signature,
        door_style,
        selections,
        aspect_ratio,
        project.style_notes,
    )
