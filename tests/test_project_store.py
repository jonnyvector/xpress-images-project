from pathlib import Path

from backend.state import TRASH_DIRNAME, ProjectStore


def test_project_store_create_update_upload_delete(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)

    project = store.create(name="Door 1", product_type="Cabinet Door", material_type="wood")
    assert project.name == "Door 1"
    assert store.get(project.id) is not None

    updated = store.update(project.id, name="Door A")
    assert updated is not None
    assert updated.name == "Door A"

    ok = store.save_upload(project.id, "upload.png", b"abc")
    assert ok is True
    assert store.get_upload_bytes(project.id) == b"abc"

    deleted = store.delete(project.id)
    assert deleted is True
    assert store.get(project.id) is None


def test_delete_moves_project_to_trash_instead_of_erasing(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.save_upload(project.id, "upload.png", b"irreplaceable")

    assert store.delete(project.id) is True

    assert not (tmp_path / project.id).exists()
    trashed = list((tmp_path / TRASH_DIRNAME).iterdir())
    assert len(trashed) == 1
    assert trashed[0].name.startswith(f"{project.id}-")
    assert (trashed[0] / "manifest.json").exists()
    assert (trashed[0] / "upload.bin").read_bytes() == b"irreplaceable"


def test_trashed_projects_do_not_reload(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.delete(project.id)

    reloaded = ProjectStore(persist_dir=tmp_path)
    assert reloaded.get(project.id) is None
    assert reloaded.list_projects() == []


def test_repeat_delete_of_same_id_keeps_both_copies(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    first = store.create(name="Door 1", product_type="Cabinet Door")
    store.delete(first.id)

    # Same id can recur across a restore or a hand-made project dir; the second
    # delete must not clobber the first trashed copy.
    (tmp_path / first.id).mkdir()
    (tmp_path / first.id / "manifest.json").write_text("{}")
    store._projects[first.id] = first
    store.delete(first.id)

    assert len(list((tmp_path / TRASH_DIRNAME).iterdir())) == 2
