from dataclasses import dataclass, field

from backend.palette import compute_gap, distinct_generated, full_palette


@dataclass
class FakeRecord:
    wood_name: str


@dataclass
class FakeProject:
    results: list = field(default_factory=list)


def test_full_palette_is_sorted_and_nonempty():
    palette = full_palette("rtf")
    assert palette == sorted(palette)
    assert len(palette) > 30


def test_distinct_generated_collapses_duplicate_attempts():
    project = FakeProject(results=[
        FakeRecord("Bisque"), FakeRecord("Bisque"), FakeRecord("Niagara"),
    ])
    assert distinct_generated(project) == {"Bisque", "Niagara"}


def test_distinct_generated_empty_project():
    assert distinct_generated(FakeProject()) == set()


def test_compute_gap_lists_missing_colours():
    project = FakeProject(results=[FakeRecord("Bisque")])
    gap = compute_gap("rtf", excluded=[], project=project)
    assert gap["generated"] == 1
    assert gap["expected"] == len(full_palette("rtf"))
    assert "Bisque" not in gap["missing"]
    assert len(gap["missing"]) == gap["expected"] - 1


def test_excluded_colours_shrink_expected_and_never_appear_missing():
    palette = full_palette("rtf")
    excluded = palette[:2]
    project = FakeProject(results=[])
    gap = compute_gap("rtf", excluded=excluded, project=project)
    assert gap["expected"] == len(palette) - 2
    assert all(c not in gap["missing"] for c in excluded)
    assert gap["excluded"] == sorted(excluded)


def test_generated_colour_outside_palette_is_ignored_not_counted_twice():
    project = FakeProject(results=[FakeRecord("Not A Real Colour")])
    gap = compute_gap("rtf", excluded=[], project=project)
    assert gap["generated"] == 0
    assert len(gap["missing"]) == gap["expected"]


def test_no_project_yields_everything_missing():
    gap = compute_gap("rtf", excluded=[], project=None)
    assert gap["generated"] == 0
    assert len(gap["missing"]) == gap["expected"]
