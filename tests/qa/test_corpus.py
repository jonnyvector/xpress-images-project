from pathlib import Path

from backend.qa.corpus import walk_corpus

JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"\x00" * 32


def test_walk_corpus_enumerates_current_and_versions(
    projects_dir: Path, swatches_dir: Path
) -> None:
    candidates = walk_corpus(projects_dir, swatches_dir)
    by_key = {c.key for c in candidates}
    # abc123 current: replica + 2 variants; v1: replica + 1 variant; def456: 1 variant.
    assert by_key == {
        "abc123:0:replica:-1",
        "abc123:0:variant:0",
        "abc123:0:variant:1",
        "abc123:1:replica:-1",
        "abc123:1:variant:0",
        "def456:0:variant:0",
    }


def test_presumed_verdicts(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    assert candidates["abc123:0:variant:0"].presumed == "accept"
    assert candidates["abc123:1:variant:0"].presumed == "reject"


def test_sample_and_swatch_resolution(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    cherry = candidates["abc123:0:variant:0"]
    assert cherry.wood_name == "Cherry Natural"
    assert cherry.sample_path is not None and cherry.sample_path.name == "upload.bin"
    assert cherry.swatch_path is not None and cherry.swatch_path.name == "cherry_natural.jpg"
    # Walnut Select has no swatch image on disk -> None, not an error.
    walnut = candidates["abc123:0:variant:1"]
    assert walnut.swatch_path is None
    # def456 has no upload.bin -> sample_path None, still enumerated.
    assert candidates["def456:0:variant:0"].sample_path is None


def test_malformed_result_names_json_degrades_to_empty(
    projects_dir: Path, swatches_dir: Path
) -> None:
    # A version with a corrupt result_names.json must not abort the whole walk.
    v2 = projects_dir / "abc123" / "versions" / "v2"
    v2.mkdir()
    (v2 / "result_names.json").write_text("not json")
    (v2 / "result_0.bin").write_bytes(JPEG)
    (v2 / "base_door.bin").write_bytes(JPEG)
    candidates = walk_corpus(projects_dir, swatches_dir)  # must not raise
    by_key = {c.key for c in candidates}
    # v2 variants are skipped (names unknown), but its replica and all other
    # candidates are still enumerated.
    assert "abc123:2:replica:-1" in by_key
    assert "abc123:2:variant:0" not in by_key
    assert "abc123:0:variant:0" in by_key
    assert "def456:0:variant:0" in by_key


def test_swatch_resolution_is_case_insensitive_and_display_name_based(
    projects_dir: Path, swatches_dir: Path
) -> None:
    # Real swatch files often preserve display-name casing (e.g. Walnut_Select.jpg)
    # while slugs are lowercase-hyphenated. Matching must not depend on a
    # case-insensitive filesystem.
    (swatches_dir / "wood" / "Walnut_Select.jpg").write_bytes(JPEG)
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    walnut = candidates["abc123:0:variant:1"]
    assert walnut.swatch_path is not None
    assert walnut.swatch_path.name == "Walnut_Select.jpg"
