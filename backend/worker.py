"""Background generation worker."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from backend.generator import DoorGenerator
from backend.materials import (
    get_swatch_files,
    load_material_types,
    normalize_material_key,
    resolve_swatch_path,
    swatch_name_from_path,
)
from backend.styles.catalog import STYLES

if TYPE_CHECKING:
    from backend.state import ProjectState, ProjectStore

_executor = ThreadPoolExecutor(max_workers=4)

# Semaphore matches executor workers — intentional: this is the per-app
# concurrency cap for Gemini API calls, independent of the outer executor
# which could grow if start_generation is called concurrently across projects.
_api_semaphore = threading.Semaphore(4)


# Styles where the product is a single flat surface (no separate frame and panel).
# These use flat_panel_description from wood_types.json when available.
FLAT_PANEL_STYLES = {"vienna", "solid_plank", "drawer_solid_plank", "rtf_drawer_bevel"}

RTF_WOODGRAIN_DOOR_REFERENCE = Path("swatches/references/rtf-woodgrain-reference.jpg")


def _is_drawer_product(project: ProjectState) -> bool:
    return project.product_type == "Drawer Front"


def _get_material_description(
    swatch_path: Path,
    material_types: dict[str, dict],
    door_style: str | None = None,
) -> str | None:
    key = normalize_material_key(swatch_path.stem)
    wt = material_types.get(key)
    if not wt:
        return None
    # Use flat-panel-specific description when the style has no frame+panel
    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
        return wt["flat_panel_description"]
    return wt.get("description") or None


def _build_selections(
    selected_swatches: list[str],
    door_style: str | None = None,
    material_type: str = "wood",
) -> list[dict]:
    """Build the selections list from selected swatch keys (ported from app.py)."""
    wood_types = load_material_types(material_type)
    all_swatch_files = get_swatch_files(material_type)
    selections: list[dict] = []
    for p in selected_swatches:
        if p.startswith("virtual:"):
            key = p[8:]
            wt = wood_types.get(key, {})
            borrowed = resolve_swatch_path(wt.get("swatch_key", ""), all_swatch_files)
            desc = (
                _get_material_description(borrowed, wood_types, door_style)
                if borrowed
                else wt.get("description")
            )
            selections.append(
                {
                    "wood_name": wt.get("name", key),
                    "swatch_path": borrowed,
                    "wood_description": desc,
                    "reference_image": None,
                }
            )
        else:
            swatch_path = Path(p)
            # If the stored value doesn't exist as a file, resolve it as a key
            if not swatch_path.exists():
                key = normalize_material_key(p)
                # Check if it's a virtual wood type (has swatch_key in wood_types.json)
                wt = wood_types.get(key, {})
                if wt.get("swatch_key"):
                    borrowed = resolve_swatch_path(wt["swatch_key"], all_swatch_files)
                    desc = wt.get("description")
                    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
                        desc = wt["flat_panel_description"]
                    selections.append(
                        {
                            "wood_name": wt.get("name", key),
                            "swatch_path": borrowed,
                            "wood_description": desc,
                            "reference_image": None,
                        }
                    )
                    continue
                # Description-only entry (no swatch_key, no physical file)
                if wt.get("description") and not resolve_swatch_path(key, all_swatch_files):
                    desc = wt.get("description")
                    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
                        desc = wt["flat_panel_description"]
                    selections.append(
                        {
                            "wood_name": wt.get("name", key),
                            "swatch_path": None,
                            "wood_description": desc,
                            "reference_image": None,
                        }
                    )
                    continue
                resolved = resolve_swatch_path(key, all_swatch_files)
                if not resolved:
                    resolved = resolve_swatch_path(
                        normalize_material_key(swatch_path.stem),
                        all_swatch_files,
                    )
                if resolved:
                    swatch_path = resolved
                else:
                    continue  # skip missing swatches
            key_lookup = normalize_material_key(swatch_path.stem)
            wt = wood_types.get(key_lookup, {})
            selections.append(
                {
                    "wood_name": wt.get("name", swatch_name_from_path(swatch_path)),
                    "swatch_path": swatch_path,
                    "wood_description": _get_material_description(
                        swatch_path, wood_types, door_style,
                    ),
                    "reference_image": None,
                    "hex": wt.get("hex"),
                    "rtf_finish": wt.get("finish"),
                }
            )
    return selections


def _run_generation(
    store: ProjectStore,
    project_id: str,
    api_key: str,
    base_signature: bytes | None,
    door_style: str,
    selections: list[dict],
    aspect_ratio: str,
    style_notes: str,
    corner_style: str = "sharp",
    material_type: str = "wood",
    gemini_model: str | None = None,
    use_base_door_reference: bool = False,
) -> None:
    """Run generation in background thread, updating ProjectState incrementally."""
    try:
        generator = DoorGenerator(api_key=api_key, model=gemini_model)
        style = STYLES.get(door_style, {})
        variation_hint = style.get("variation_hint", "")

        def _generate_one(sel: dict) -> tuple[str, object]:
            wood_name = sel["wood_name"]
            with _api_semaphore:
                if use_base_door_reference and sel.get("reference_image"):
                    result = generator.generate_variation_from_reference(
                        reference_image_path=sel["reference_image"],
                        swatch_image_path=sel["swatch_path"],
                        wood_name=wood_name,
                        variation_hint=variation_hint,
                        wood_description=sel["wood_description"],
                        aspect_ratio=aspect_ratio,
                        corner_style=corner_style,
                    )
                else:
                    result = generator.generate_variation(
                        swatch_image_path=sel["swatch_path"],
                        wood_name=wood_name,
                        base_signature=base_signature,
                        wood_description=sel["wood_description"],
                        reference_image_path=sel["reference_image"],
                        door_style=door_style,
                        aspect_ratio=aspect_ratio,
                        style_notes=style_notes,
                        corner_style=corner_style,
                        material_type=material_type,
                        hex_color=sel.get("hex"),
                        rtf_finish=sel.get("rtf_finish"),
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
    corner_style: str = "sharp",
    material_type: str = "wood",
    gemini_model: str | None = None,
    learn_in_maple: bool = False,
) -> None:
    """Run learn_door_style in background thread."""
    temp_path = OUTPUT_DIR / f"temp_learn_{project_id}.png"
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(upload_bytes)

        generator = DoorGenerator(api_key=api_key, model=gemini_model)
        with _api_semaphore:
            result = generator.learn_door_style(
                door_image_path=temp_path,
                door_style_name=door_style_name,
                door_style=door_style,
                aspect_ratio=aspect_ratio,
                corner_style=corner_style,
                material_type=material_type,
                learn_in_maple=learn_in_maple,
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
    *,
    learn_in_maple: bool = False,
) -> None:
    """Kick off background learning for a project."""
    is_drawer = _is_drawer_product(project)
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
        project.corner_style,
        project.material_type,
        project.gemini_model,
        learn_in_maple,
    )


def _run_retry(
    store: ProjectStore,
    project_id: str,
    api_key: str,
    idx: int,
    base_signature: bytes | None,
    door_style: str,
    selection: dict,
    aspect_ratio: str,
    style_notes: str,
    corner_style: str = "sharp",
    material_type: str = "wood",
    gemini_model: str | None = None,
    use_base_door_reference: bool = False,
) -> None:
    """Re-generate a single variation in-place."""
    try:
        generator = DoorGenerator(api_key=api_key, model=gemini_model)
        wood_name = selection["wood_name"]
        style = STYLES.get(door_style, {})
        variation_hint = style.get("variation_hint", "")
        with _api_semaphore:
            if use_base_door_reference and selection.get("reference_image"):
                result = generator.generate_variation_from_reference(
                    reference_image_path=selection["reference_image"],
                    swatch_image_path=selection["swatch_path"],
                    wood_name=wood_name,
                    variation_hint=variation_hint,
                    wood_description=selection["wood_description"],
                    aspect_ratio=aspect_ratio,
                    corner_style=corner_style,
                )
            else:
                result = generator.generate_variation(
                    swatch_image_path=selection["swatch_path"],
                    wood_name=wood_name,
                    base_signature=base_signature,
                    wood_description=selection["wood_description"],
                    reference_image_path=selection["reference_image"],
                    door_style=door_style,
                    aspect_ratio=aspect_ratio,
                    style_notes=style_notes,
                    corner_style=corner_style,
                    material_type=material_type,
                    hex_color=selection.get("hex"),
                    rtf_finish=selection.get("rtf_finish"),
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
    is_drawer = _is_drawer_product(project)
    aspect_ratio = "16:9" if is_drawer else "9:16"
    door_style = project.door_style or "recessed_panel"

    style = STYLES.get(door_style, {})
    use_ref = bool(style.get("use_base_door_reference"))
    base_door_path = OUTPUT_DIR / ".projects" / project.id / "base_door.bin"

    if use_ref:
        if not base_door_path.exists():
            project.errors.append(
                (project.results[idx][0],
                 "No base door image available — please re-learn the door style.")
            )
            store.save(project.id)
            return
    elif not project.learned_signature:
        project.errors.append(
            (project.results[idx][0],
             "No thought signature available — please re-learn the door style.")
        )
        store.save(project.id)
        return

    wood_name = project.results[idx][0]

    # Try to find the matching swatch in selected_swatches
    selection = None
    for swatch_key in project.selected_swatches:
        selections = _build_selections(
            [swatch_key], door_style=door_style, material_type=project.material_type,
        )
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

    # Inject base door reference for opted-in styles
    if use_ref:
        selection["reference_image"] = base_door_path

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
        project.corner_style,
        project.material_type,
        project.gemini_model,
        use_ref,
    )


def start_generation(
    store: ProjectStore,
    project: ProjectState,
    api_key: str,
) -> None:
    """Kick off background generation for a project."""
    is_drawer = _is_drawer_product(project)
    aspect_ratio = "16:9" if is_drawer else "9:16"
    door_style = project.door_style or "recessed_panel"

    style = STYLES.get(door_style, {})
    use_ref = bool(style.get("use_base_door_reference"))

    # For reference-based styles, check for base_door.bin instead of signature
    base_door_path = OUTPUT_DIR / ".projects" / project.id / "base_door.bin"
    if use_ref:
        if not base_door_path.exists():
            project.errors = [
                ("Generation", "No base door image available — please learn the door style first.")
            ]
            project.generation_status = "done"
            store.save(project.id)
            return
    elif not project.learned_signature:
        project.errors = [
            ("Generation", "No thought signature available — please learn the door style first.")
        ]
        project.generation_status = "done"
        store.save(project.id)
        return

    selections = _build_selections(
        project.selected_swatches, door_style=door_style, material_type=project.material_type,
    )
    if not selections:
        return

    # Inject base door image path for reference-based styles
    if use_ref:
        for sel in selections:
            sel["reference_image"] = base_door_path

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
        project.corner_style,
        project.material_type,
        project.gemini_model,
        use_ref,
    )
