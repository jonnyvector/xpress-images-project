from pathlib import Path

import pytest

from backend.qa.labels import Label, LabelStore


def test_label_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    store = LabelStore(path)
    store.set(Label(key="p1:0:variant:3", verdict="reject", reasons=["geometry_drift"]))
    store.set(Label(key="p1:0:replica:-1", verdict="accept"))

    reloaded = LabelStore(path)
    got = reloaded.get("p1:0:variant:3")
    assert got is not None
    assert got.verdict == "reject"
    assert got.reasons == ["geometry_drift"]
    assert len(reloaded.all()) == 2


def test_label_store_upsert_replaces(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels.json")
    store.set(Label(key="k1", verdict="reject", reasons=["artifacts"]))
    store.set(Label(key="k1", verdict="accept"))
    got = store.get("k1")
    assert got is not None
    assert got.verdict == "accept"
    assert got.reasons == []


def test_label_store_rejects_bad_input(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels.json")
    with pytest.raises(ValueError):
        store.set(Label(key="k", verdict="maybe"))
    with pytest.raises(ValueError):
        store.set(Label(key="k", verdict="reject", reasons=["too_ugly"]))
