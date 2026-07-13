from pathlib import Path

from backend.state import ProjectStore


def test_profile_spec_round_trips_through_manifest(tmp_path: Path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Talbot", product_type="Cabinet Door", material_type="wood")
    assert store.get(p.id).profile_spec is None

    facts = ["panel: louver slats, tight pitch", "trim_molding: none"]
    store.update(p.id, profile_spec=facts)

    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.profile_spec == facts


def test_profile_image_path_roundtrips_and_defaults_none(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="El Dorado", product_type="Cabinet Door", material_type="wood")
    assert p.profile_image_path is None

    store.update(p.id, profile_image_path="/catalog/El Dorado/profile/3d-profile.jpg")
    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.profile_image_path == "/catalog/El Dorado/profile/3d-profile.jpg"
