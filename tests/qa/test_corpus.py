from pathlib import Path

from backend.qa.corpus import walk_corpus


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
