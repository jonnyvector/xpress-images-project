"""Concurrency + retry-accounting tests for ProjectStore result writes."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend.state import ProjectStore


def test_record_result_is_atomic_under_concurrency(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")

    n = 50
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(
                store.record_result,
                project.id,
                f"wood_{i}",
                image_data=b"img",
            )
            for i in range(n)
        ]
        for f in futures:
            assert f.result() is True

    refreshed = store.get(project.id)
    assert refreshed is not None
    # No lost updates: every write counted, every result present.
    assert refreshed.generation_completed == n
    assert len(refreshed.results) == n
    assert {wn for wn, _ in refreshed.results} == {f"wood_{i}" for i in range(n)}


def test_record_result_errors_and_advance_flag(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")

    assert store.record_result(project.id, "Oak", error="boom") is True
    # advance=False must not bump the completed counter (top-level failures).
    assert store.record_result(project.id, "Generation", error="fatal", advance=False) is True

    refreshed = store.get(project.id)
    assert refreshed is not None
    assert refreshed.generation_completed == 1
    assert ("Oak", "boom") in refreshed.errors
    assert ("Generation", "fatal") in refreshed.errors


def test_record_result_returns_false_when_project_gone(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    assert store.record_result("nope", "Oak", image_data=b"x") is False


def test_retry_failure_then_success_leaves_no_stale_error(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    # Seed an existing successful result to retry in place.
    store.record_result(project.id, "Oak", image_data=b"old")

    # First retry fails -> records an error for "Oak".
    store.record_retry_result(project.id, 0, "Oak", error="Retry failed")
    mid = store.get(project.id)
    assert mid is not None
    assert ("Oak", "Retry failed") in mid.errors

    # Second retry succeeds -> replaces result, clears the stale error.
    store.record_retry_result(project.id, 0, "Oak", image_data=b"new")
    final = store.get(project.id)
    assert final is not None
    assert final.results[0] == ("Oak", b"new")
    assert all(wn != "Oak" for wn, _ in final.errors)


def test_finish_retry_clears_index(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.update(project.id, retrying_indices=[2])

    store.finish_retry(project.id, 2)
    refreshed = store.get(project.id)
    assert refreshed is not None
    assert 2 not in refreshed.retrying_indices
