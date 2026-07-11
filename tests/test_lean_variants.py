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


# --- M2: worker plumbing -----------------------------------------------------


import backend.worker as worker  # noqa: E402


class _StubGen:
    """Captures the kwargs each generation branch receives."""
    def __init__(self):
        self.variation_kwargs = None
        self.reference_kwargs = None

    def generate_variation(self, **kw):
        self.variation_kwargs = kw
        return "variation-result"

    def generate_variation_from_reference(self, **kw):
        self.reference_kwargs = kw
        return "reference-result"


def _sel(**over):
    sel = {"wood_name": "Maple Select", "swatch_path": None,
           "wood_description": "pale", "reference_image": None, "hex": None,
           "rtf_finish": None}
    sel.update(over)
    return sel


def test_generate_for_selection_forwards_lean():
    gen = _StubGen()
    worker._generate_for_selection(
        gen, _sel(), base_signature=b"sig", door_style="shaker_bevel",
        variation_hint="styled hint", aspect_ratio="9:16", style_notes="",
        corner_style="sharp", material_type="wood",
        use_base_door_reference=False, lean=True,
    )
    assert gen.variation_kwargs["lean"] is True


def test_generate_for_selection_reference_branch_ignores_lean():
    gen = _StubGen()
    worker._generate_for_selection(
        gen, _sel(reference_image="ref.jpg"), base_signature=b"sig",
        door_style="shaker_bevel", variation_hint="styled hint",
        aspect_ratio="9:16", style_notes="", corner_style="sharp",
        material_type="wood", use_base_door_reference=True, lean=True,
    )
    assert gen.reference_kwargs is not None
    assert "lean" not in gen.reference_kwargs      # branch untouched
    assert gen.variation_kwargs is None


def _mode_project(tmp_path, mode):
    store = ProjectStore(persist_dir=tmp_path / f"projects_{mode}")
    p = store.create(name=f"Door {mode}", product_type="Cabinet Door",
                     material_type="wood")
    store.update(p.id, variant_hint_mode=mode, has_signature=True,
                 learned_signature=b"sig",
                 selected_swatches=["swatches/wood/maple_select.jpg"])
    return store, store.get(p.id)


def test_start_generation_resolves_mode(tmp_path, monkeypatch):
    calls = {}

    def fake_submit(fn, *args):
        calls.setdefault("runs", []).append(args)

    monkeypatch.setattr(worker, "_executor",
                        type("E", (), {"submit": staticmethod(fake_submit)})())
    for mode, expected in (("lean", True), ("styled", False)):
        store, p = _mode_project(tmp_path, mode)
        worker.start_generation(store, p, "key")
        assert calls["runs"][-1][-1] is expected, mode   # lean is the last arg


def test_run_generation_logs_resolved_mode(tmp_path, capsys):
    store, p = _mode_project(tmp_path, "lean")
    worker._run_generation(store, p.id, "key", b"sig", "shaker_bevel", [],
                           "9:16", "", lean=True)
    out = capsys.readouterr().out
    assert f"[variants {p.id}] hint=lean" in out
    worker._run_generation(store, p.id, "key", b"sig", "shaker_bevel", [],
                           "9:16", "notes here", lean=False)
    out = capsys.readouterr().out
    assert f"[variants {p.id}] hint=styled notes=present" in out


# --- M2: variant_wave --topup helpers ---------------------------------------


import importlib.util  # noqa: E402


def _load_wave():
    spec = importlib.util.spec_from_file_location(
        "variant_wave", Path(__file__).resolve().parents[1] / "scripts" / "variant_wave.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubApprovals:
    def __init__(self, approved_ids):
        self._ids = approved_ids

    def for_project(self, pid):
        class A:
            def __init__(self, image_id):
                self.image_id = image_id
                self.kind = "variant"
                self.verdict = "approved"
        return [A(i) for i in self._ids]


class _StubRecord:
    def __init__(self, image_id, wood_name):
        self.image_id = image_id
        self.wood_name = wood_name


class _StubProject:
    def __init__(self, results, swatches):
        self.id = "p1"
        self.results = results
        self.selected_swatches = swatches
        self.door_style = "shaker_bevel"
        self.material_type = "wood"


def test_approved_wood_names_and_topup_selection():
    wave = _load_wave()
    swatches = ["swatches/wood/maple_select.jpg", "swatches/wood/cherry_natural.jpg"]
    project = _StubProject(
        results=[_StubRecord("img1", "Maple Select"), _StubRecord("img2", "Cherry Natural")],
        swatches=swatches,
    )
    approvals = _StubApprovals({"img1"})          # only Maple approved
    approved = wave.approved_wood_names(project, approvals)
    assert approved == {"Maple Select"}
    missing = wave.topup_swatch_paths(project, approved)
    assert len(missing) == 1
    assert "cherry_natural" in str(missing[0])    # only the unapproved wood
