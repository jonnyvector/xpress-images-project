from pathlib import Path

from backend.state import ProjectStore


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
