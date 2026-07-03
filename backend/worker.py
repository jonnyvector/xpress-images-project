"""Background generation worker."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from backend.generator import DoorGenerator
from backend.qa.qa_lane import RegenContext, get_qa_lane
from backend.qa.trust_config import load_trust_config, snapshot
from backend.runs import RunManifest
from backend.selections import build_selections
from backend.state import new_image_id
from backend.styles.catalog import STYLES

if TYPE_CHECKING:
    from backend.state import ProjectState, ProjectStore

_executor = ThreadPoolExecutor(max_workers=4)

# Semaphore matches executor workers — intentional: this is the per-app
# concurrency cap for Gemini API calls, independent of the outer executor
# which could grow if start_generation is called concurrently across projects.
_api_semaphore = threading.Semaphore(4)


RTF_WOODGRAIN_DOOR_REFERENCE = Path("swatches/references/rtf-woodgrain-reference.jpg")


def _is_drawer_product(project: ProjectState) -> bool:
    return project.product_type == "Drawer Front"


# Near-white threshold: every RGB channel this light or lighter counts as
# low-contrast. White Supermatte (FAF9F5), 949W (F8F8F6), Feather (FEFEF9) all
# clear it; mid-tones and greys do not.
_NEAR_WHITE_MIN_CHANNEL = 0xDC


def _swatch_min_channel(swatch_path) -> int | None:
    """Darkest RGB channel of the swatch's mean color, or None if unreadable."""
    try:
        from PIL import Image

        with Image.open(swatch_path) as im:
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
        return min(r, g, b)
    except Exception:
        return None


def _needs_geometry_anchor(sel: dict, material_type: str) -> bool:
    """Whether this selection should attach the replica as a geometry reference.

    White-on-white RTF collapses the tiered/recessed profile to a raised panel:
    with near-zero luminance contrast the signature/prompt conditioning is too
    weak, and the raised-panel prior wins (validated 2026-07-03). Attaching the
    approved replica image restores geometry independent of color contrast.

    Scoped to near-white RTF only — darker colors don't need it, and a white
    replica reference could leak lightness into a saturated target. Uses the hex
    when present, else falls back to the swatch's actual mean luminance so
    non-hex whites (e.g. Velvet White) still anchor.
    """
    if material_type != "rtf":
        return False
    hexv = sel.get("hex")
    if hexv and len(hexv) >= 6:
        try:
            r, g, b = (int(hexv[i : i + 2], 16) for i in (0, 2, 4))
            return min(r, g, b) >= _NEAR_WHITE_MIN_CHANNEL
        except ValueError:
            pass  # malformed hex — fall back to the swatch pixels
    mn = _swatch_min_channel(sel.get("swatch_path"))
    return mn is not None and mn >= _NEAR_WHITE_MIN_CHANNEL


def _generate_for_selection(
    generator: DoorGenerator,
    sel: dict,
    *,
    base_signature: bytes | None,
    door_style: str,
    variation_hint: str,
    aspect_ratio: str,
    style_notes: str,
    corner_style: str,
    material_type: str,
    use_base_door_reference: bool,
):
    """Dispatch a single selection to the correct generator call.

    Owns the reference-vs-signature branch shared by batch generation and
    single-result retry, so the two call sites can't drift apart.
    """
    wood_name = sel["wood_name"]
    if use_base_door_reference and sel.get("reference_image"):
        return generator.generate_variation_from_reference(
            reference_image_path=sel["reference_image"],
            swatch_image_path=sel["swatch_path"],
            wood_name=wood_name,
            variation_hint=variation_hint,
            wood_description=sel["wood_description"],
            aspect_ratio=aspect_ratio,
            corner_style=corner_style,
        )
    return generator.generate_variation(
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
    run: RunManifest | None = None,
) -> None:
    """Run generation in background thread, updating ProjectState incrementally.

    Identity binds at submission: each selection carries a pre-assigned
    ``image_id`` (from the run manifest's planned entries), so results and
    verdicts reference the right image regardless of completion order.
    """
    try:
        generator = DoorGenerator(api_key=api_key, model=gemini_model)
        style = STYLES.get(door_style, {})
        variation_hint = style.get("variation_hint", "")

        def _generate_one(sel: dict) -> tuple[str, object]:
            if run is not None:
                run.submit()  # counted before the API call — cap authority
            with _api_semaphore:
                result = _generate_for_selection(
                    generator,
                    sel,
                    base_signature=base_signature,
                    door_style=door_style,
                    variation_hint=variation_hint,
                    aspect_ratio=aspect_ratio,
                    style_notes=style_notes,
                    corner_style=corner_style,
                    material_type=material_type,
                    use_base_door_reference=use_base_door_reference,
                )
            return sel["wood_name"], result

        max_parallel = min(len(selections), 4)
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            futures = {pool.submit(_generate_one, sel): sel for sel in selections}
            for future in as_completed(futures):
                sel = futures[future]
                image_id = sel.get("image_id")
                try:
                    wood_name, result = future.result()
                    record = store.record_result(
                        project_id,
                        wood_name,
                        image_data=result.image_data,
                        error=result.error,
                        image_id=image_id,
                    )
                    if not record:
                        return
                    if result.image_data is not None:
                        stored_id = image_id or getattr(record, "image_id", "")
                        regen = None
                        if run is not None:
                            run.record_attempt(
                                image_id=stored_id, wood_name=wood_name, attempt=0,
                            )
                            # Regen closure owns generator params + semaphore,
                            # so the QA lane never learns generation internals.
                            def _attempt(sel=sel):
                                with _api_semaphore:
                                    return _generate_for_selection(
                                        generator,
                                        sel,
                                        base_signature=base_signature,
                                        door_style=door_style,
                                        variation_hint=variation_hint,
                                        aspect_ratio=aspect_ratio,
                                        style_notes=style_notes,
                                        corner_style=corner_style,
                                        material_type=material_type,
                                        use_base_door_reference=use_base_door_reference,
                                    )

                            regen = RegenContext(
                                run=run,
                                generate=_attempt,
                                wood_name=wood_name,
                                attempt_ids=[stored_id],
                            )
                        get_qa_lane().enqueue(
                            store, project_id, stored_id, api_key,
                            kind="variant", swatch_path=sel.get("swatch_path"),
                            regen=regen,
                        )
                except Exception as exc:
                    if not store.record_result(
                        project_id, sel["wood_name"], error=str(exc)
                    ):
                        return
    except Exception as exc:
        # Catch any top-level error so status always gets set to done
        store.record_result(project_id, "Generation", error=str(exc), advance=False)
    finally:
        # Always mark done, even on crash
        if run is not None:
            run.finish("done")
        store.update(project_id, generation_status="done")


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
            # New replica image = new identity: approvals/verdicts of the old
            # replica must never carry over to an image nobody has reviewed.
            project.base_image_id = new_image_id()
            project.results = []
            project.qa_verdicts = {}
            project.errors = []
            project.generation_status = "idle"
            project.generation_completed = 0
            project.generation_total = 0
            project.signature_version = 0
            project.learning_status = "done"
            project.learning_error = None
        store.save(project_id)
        if project.learning_status == "done" and project.base_image_id:
            # New replica: judge it (sample-reference, advisory) right away.
            get_qa_lane().enqueue(
                store, project_id, project.base_image_id, api_key, kind="replica"
            )
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
    aspect_ratio: str | None = None,
) -> None:
    """Kick off background learning for a project.

    ``aspect_ratio`` overrides the product-type default for doors that
    aren't the usual 9:16 shape (operator finding: FC712 is ~2:3).
    """
    is_drawer = _is_drawer_product(project)
    if aspect_ratio is None:
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
            result = _generate_for_selection(
                generator,
                selection,
                base_signature=base_signature,
                door_style=door_style,
                variation_hint=variation_hint,
                aspect_ratio=aspect_ratio,
                style_notes=style_notes,
                corner_style=corner_style,
                material_type=material_type,
                use_base_door_reference=use_base_door_reference,
            )
        record = store.record_retry_result(
            project_id,
            idx,
            wood_name,
            image_data=result.image_data,
            error=result.error,
        )
        if result.image_data is not None and hasattr(record, "image_id"):
            get_qa_lane().enqueue(
                store, project_id, record.image_id, api_key,
                kind="variant", swatch_path=selection.get("swatch_path"),
            )
    except Exception as exc:
        store.record_retry_result(project_id, idx, selection["wood_name"], error=str(exc))
    finally:
        store.finish_retry(project_id, idx)


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
                (project.results[idx].wood_name,
                 "No base door image available — please re-learn the door style.")
            )
            store.save(project.id)
            return
    elif not project.learned_signature:
        project.errors.append(
            (project.results[idx].wood_name,
             "No thought signature available — please re-learn the door style.")
        )
        store.save(project.id)
        return

    wood_name = project.results[idx].wood_name

    # Try to find the matching swatch in selected_swatches
    selection = None
    for swatch_key in project.selected_swatches:
        selections = build_selections(
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
    # Near-white RTF: anchor geometry on the replica (signature path, not the
    # temp-0.0 from-reference path) so white-on-white keeps the recessed profile.
    elif (
        selection.get("reference_image") is None
        and base_door_path.exists()
        and _needs_geometry_anchor(selection, project.material_type)
    ):
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

    selections = build_selections(
        project.selected_swatches, door_style=door_style, material_type=project.material_type,
    )
    if not selections:
        return

    # Inject base door image path for reference-based styles
    if use_ref:
        for sel in selections:
            sel["reference_image"] = base_door_path
    # Near-white RTF: anchor geometry on the replica (signature path) so
    # white-on-white keeps the recessed profile instead of collapsing to raised.
    elif base_door_path.exists():
        for sel in selections:
            if sel.get("reference_image") is None and _needs_geometry_anchor(
                sel, project.material_type
            ):
                sel["reference_image"] = base_door_path

    # Identity at submission (D-006): every planned image gets its id before
    # any API call, recorded in the run manifest for crash-safe accounting.
    for sel in selections:
        sel["image_id"] = new_image_id()
    run = RunManifest.create(
        OUTPUT_DIR / ".projects" / project.id,
        planned=[(sel["wood_name"], sel["image_id"]) for sel in selections],
        # Snapshot at run start (D-009): mid-run config edits never change
        # a running run's retry/cap rules.
        config=snapshot(load_trust_config()),
    )

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
        run,
    )
