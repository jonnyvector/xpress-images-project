"""M2 (lean-conditioning): lean flag on the learn path + assembled-prompt
observability. Generator tests stub _call_with_retry (the network boundary);
worker tests stub DoorGenerator.learn_door_style and use a real ProjectStore.
"""
import pytest

import backend.worker as worker
from backend.generator import STYLES, DoorGenerator, GenerationResult
from backend.state import ProjectStore

LEAN_TEXT = STYLES["rtf_minimal"]["learn_prompt"]


def _capture_generator(monkeypatch):
    gen = DoorGenerator(api_key="test-key")
    captured = {}

    def fake_call(contents, config, label=""):
        captured["contents"] = contents
        return None, GenerationResult(image_data=None, thought_signature=None, error="stub")

    monkeypatch.setattr(gen, "_call_with_retry", fake_call)
    return gen, captured


def _prompt(captured):
    return captured["contents"][0].parts[0].text


def _image_parts(captured):
    return [p for p in captured["contents"][0].parts if p.inline_data is not None]


@pytest.fixture
def door(tmp_path):
    p = tmp_path / "door.jpg"
    p.write_bytes(b"\xff\xd8hero")
    return p


def test_lean_swaps_style_prompt_only(door, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    gen.learn_door_style(door_image_path=door, door_style="raised_panel", lean=True)
    text = _prompt(cap)
    assert text.startswith(LEAN_TEXT)
    assert "bevel" not in text.lower()          # raised_panel prose gone
    assert "OUTER CORNERS" in text              # corner block retained
    assert "CRITICAL DIMENSIONS" in text        # dimensions block retained


def test_lean_retains_material_block_for_rtf(door, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    gen.learn_door_style(door_image_path=door, door_style="raised_panel",
                         material_type="rtf", lean=True)
    assert "Rigid Thermofoil" in _prompt(cap)


def test_lean_retains_image_parts_and_anchor(door, tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    drawing = tmp_path / "3d-profile.jpg"
    drawing.write_bytes(b"\xff\xd8xsec")
    gen.learn_door_style(door_image_path=door, door_style="raised_panel",
                         lean=True, profile_image_path=drawing)
    imgs = _image_parts(cap)
    assert len(imgs) == 2 and imgs[1].inline_data.data == b"\xff\xd8xsec"


def test_default_lean_false_keeps_style_prompt(door, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    gen.learn_door_style(door_image_path=door, door_style="raised_panel")
    assert _prompt(cap).startswith(
        STYLES["raised_panel"]["learn_prompt"][:40])


def test_generation_result_carries_assembled_prompt(door, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    styled = gen.learn_door_style(door_image_path=door, door_style="raised_panel")
    assert styled.prompt == _prompt(cap)   # even on the error path
    assert styled.prompt.startswith(STYLES["raised_panel"]["learn_prompt"][:40])
    lean = gen.learn_door_style(door_image_path=door, door_style="raised_panel",
                                lean=True)
    assert lean.prompt.startswith(LEAN_TEXT)


# --- worker: sidecar + label threading -------------------------------------


def _stub_learn(monkeypatch, result):
    def fake(self, **kw):
        return result
    monkeypatch.setattr(DoorGenerator, "learn_door_style", fake)


def _project(tmp_path):
    store = ProjectStore(persist_dir=tmp_path / "projects")
    p = store.create(name="Testy", product_type="Cabinet Door", material_type="wood")
    return store, p


def test_run_learn_writes_prompt_sidecar_and_layer_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "output")
    _stub_learn(monkeypatch, GenerationResult(
        image_data=None, thought_signature=None, error="stub",
        prompt="ASSEMBLED PROMPT TEXT"))
    store, p = _project(tmp_path)
    worker._run_learn(store, p.id, "key", b"src", "raised_panel", "Testy", "9:16",
                      lean=True, attempt_label="attempt2")
    sidecars = list((tmp_path / "output" / ".onboard" / "prompts" / p.id).glob(
        "attempt2-*.txt"))
    assert len(sidecars) == 1
    assert sidecars[0].read_text() == "ASSEMBLED PROMPT TEXT"
    out = capsys.readouterr().out
    assert "style=lean" in out and "notes=empty" in out and "anchor=no" in out


def test_run_learn_sidecar_failure_does_not_fail_learn(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "output")
    _stub_learn(monkeypatch, GenerationResult(
        image_data=None, thought_signature=None, error="stub", prompt="P"))
    monkeypatch.setattr(worker, "_write_prompt_sidecar",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    store, p = _project(tmp_path)
    worker._run_learn(store, p.id, "key", b"src", "raised_panel", "Testy", "9:16",
                      attempt_label="attempt0")   # must not raise
    assert store.get(p.id).learning_status == "error"  # from the stub result, not the sidecar


def test_start_learning_threads_lean_and_label(tmp_path, monkeypatch):
    calls = {}

    def fake_submit(fn, *args):
        calls["args"] = args
        return None

    monkeypatch.setattr(worker, "_executor", type("E", (), {"submit": staticmethod(fake_submit)})())
    store, p = _project(tmp_path)
    worker.start_learning(store, p, "key", b"src", lean=True, attempt_label="attempt3")
    assert True in calls["args"] and "attempt3" in calls["args"]
