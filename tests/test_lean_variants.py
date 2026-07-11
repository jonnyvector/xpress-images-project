"""lean-variants M1/M2: variant_hint_mode persistence + generate_variation lean
flag (bare hint). Fake-client pattern from test_learn_temperature.py."""
import json
from pathlib import Path

from backend.generator import LEAN_VARIATION_HINT, DoorGenerator
from backend.state import ProjectStore
from backend.styles.catalog import STYLES

BARE = "Preserve the exact door structure from before. Change only the wood material."


# --- persistence -------------------------------------------------------------


def test_variant_hint_mode_roundtrips(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Mitchell", product_type="Cabinet Door", material_type="wood")
    assert p.variant_hint_mode == "styled"
    store.update(p.id, variant_hint_mode="lean")
    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.variant_hint_mode == "lean"


def test_old_manifest_without_key_loads_styled(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Old Door", product_type="Cabinet Door", material_type="wood")
    manifest = tmp_path / p.id / "manifest.json"
    data = json.loads(manifest.read_text())
    data.pop("variant_hint_mode", None)   # simulate a pre-plan manifest
    manifest.write_text(json.dumps(data))
    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.variant_hint_mode == "styled"


# --- generator lean flag -----------------------------------------------------


class _FakeClient:
    def __init__(self):
        self.captured = {}
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.captured["contents"] = contents
        self.captured["config"] = config

        class _Resp:
            candidates = []

        return _Resp()


def _gen_with_fake():
    gen = DoorGenerator(api_key="x")
    gen.client = _FakeClient()
    return gen, gen.client


def _swatch(tmp_path) -> Path:
    p = tmp_path / "swatch.jpg"
    p.write_bytes(b"\xff\xd8fake")
    return p


def _variation(gen, tmp_path, **kw):
    return gen.generate_variation(
        swatch_image_path=_swatch(tmp_path),
        wood_name="Maple Select",
        base_signature=b"sig-bytes",
        wood_description="pale straw",
        reference_image_path=None,
        door_style="shaker_bevel",
        aspect_ratio="9:16",
        corner_style="sharp",
        material_type="wood",
        **kw,
    )


def _prompt(fake):
    return fake.captured["contents"][0].parts[1].text  # part 0 = signature


def test_lean_variation_hint_has_no_geometry_claims():
    assert LEAN_VARIATION_HINT == BARE
    assert "stiles" not in LEAN_VARIATION_HINT.lower()
    assert "width" not in LEAN_VARIATION_HINT.lower()


def test_lean_true_swaps_hint_only(tmp_path):
    gen, fake = _gen_with_fake()
    _variation(gen, tmp_path, lean=True, style_notes="frame exactly 2.25 inches")
    prompt = _prompt(fake)
    assert LEAN_VARIATION_HINT in prompt
    assert "tiniest eased bevel" not in prompt          # styled hint gone
    assert "STRUCTURAL DETAILS: frame exactly 2.25 inches" in prompt


def test_lean_false_is_byte_identical_to_today(tmp_path):
    gen, fake = _gen_with_fake()
    _variation(gen, tmp_path, style_notes="")
    styled_prompt = _prompt(fake)
    assert STYLES["shaker_bevel"]["variation_hint"] in styled_prompt
    assert LEAN_VARIATION_HINT not in styled_prompt


def test_lean_keeps_swatch_and_signature_parts(tmp_path):
    gen, fake = _gen_with_fake()
    _variation(gen, tmp_path, lean=True)
    parts = fake.captured["contents"][0].parts
    assert parts[0].thought_signature == b"sig-bytes"   # signature first
    assert any(p.inline_data is not None for p in parts)  # swatch part intact
    assert fake.captured["config"].temperature == 0.3
