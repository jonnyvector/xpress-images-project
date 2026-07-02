"""Read-only walker over output/.projects: enumerate generated images + references."""

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Candidate:
    key: str  # "{project_id}:{version}:{kind}:{index}"
    project_id: str
    project_name: str
    door_style: str | None
    version: int  # 0 = current, N = versions/vN
    kind: str  # "replica" | "variant"
    index: int  # -1 for replica
    wood_name: str | None
    image_path: Path
    sample_path: Path | None  # upload.bin, may be missing
    swatch_path: Path | None
    presumed: str  # "accept" (current) | "reject" (archived version)


def _swatch_index(swatches_dir: Path) -> dict[str, Path]:
    """Map lowercased display name -> swatch image path, tolerant of filename drift."""
    index: dict[str, Path] = {}
    for json_name, img_subdir in (("wood_types.json", "wood"), ("rtf_types.json", "rtf")):
        types_path = swatches_dir / json_name
        if not types_path.exists():
            continue
        try:
            types = json.loads(types_path.read_text())
        except json.JSONDecodeError:
            continue
        for slug, info in types.items():
            name = str(info.get("name", slug)).lower()
            for filename in (
                f"{slug.replace('-', '_')}.jpg",
                f"{slug}.jpg",
                f"{slug}-new.png",
                f"{slug.replace('-', '_')}.png",
                f"{slug}.png",
            ):
                path = swatches_dir / img_subdir / filename
                if path.exists():
                    index[name] = path
                    break
    return index


def walk_corpus(projects_dir: Path, swatches_dir: Path) -> list[Candidate]:
    swatch_by_name = _swatch_index(swatches_dir)
    candidates: list[Candidate] = []
    if not projects_dir.exists():
        return candidates
    for d in sorted(projects_dir.iterdir()):
        manifest_path = d / "manifest.json"
        if not d.is_dir() or not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        pid = manifest.get("id", d.name)
        name = manifest.get("name", d.name)
        style = manifest.get("door_style")
        upload = d / "upload.bin"
        sample = upload if upload.exists() else None
        candidates.extend(
            _version_candidates(
                d,
                version=0,
                presumed="accept",
                pid=pid,
                name=name,
                style=style,
                sample=sample,
                result_names=manifest.get("result_names", []),
                swatch_by_name=swatch_by_name,
            )
        )
        versions_dir = d / "versions"
        if not versions_dir.exists():
            continue
        for vdir in sorted(versions_dir.iterdir()):
            if not vdir.is_dir() or not vdir.name.startswith("v") or not vdir.name[1:].isdigit():
                continue
            names_path = vdir / "result_names.json"
            result_names = json.loads(names_path.read_text()) if names_path.exists() else []
            vstyle = style
            meta_path = vdir / "meta.json"
            if meta_path.exists():
                with contextlib.suppress(json.JSONDecodeError):
                    vstyle = json.loads(meta_path.read_text()).get("door_style", style)
            candidates.extend(
                _version_candidates(
                    vdir,
                    version=int(vdir.name[1:]),
                    presumed="reject",
                    pid=pid,
                    name=name,
                    style=vstyle,
                    sample=sample,
                    result_names=result_names,
                    swatch_by_name=swatch_by_name,
                )
            )
    return candidates


def _version_candidates(
    base: Path,
    *,
    version: int,
    presumed: str,
    pid: str,
    name: str,
    style: str | None,
    sample: Path | None,
    result_names: list[str],
    swatch_by_name: dict[str, Path],
) -> list[Candidate]:
    out: list[Candidate] = []
    replica = base / "base_door.bin"
    if replica.exists():
        out.append(
            Candidate(
                key=f"{pid}:{version}:replica:-1",
                project_id=pid,
                project_name=name,
                door_style=style,
                version=version,
                kind="replica",
                index=-1,
                wood_name=None,
                image_path=replica,
                sample_path=sample,
                swatch_path=None,
                presumed=presumed,
            )
        )
    for idx, wood_name in enumerate(result_names):
        rpath = base / f"result_{idx}.bin"
        if not rpath.exists():
            continue
        out.append(
            Candidate(
                key=f"{pid}:{version}:variant:{idx}",
                project_id=pid,
                project_name=name,
                door_style=style,
                version=version,
                kind="variant",
                index=idx,
                wood_name=wood_name,
                image_path=rpath,
                sample_path=sample,
                swatch_path=swatch_by_name.get(wood_name.lower()),
                presumed=presumed,
            )
        )
    return out
