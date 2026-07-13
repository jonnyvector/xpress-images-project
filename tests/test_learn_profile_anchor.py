"""learn_door_style profile anchor: parts assembly + framing line, no live API."""
from backend.generator import DoorGenerator, GenerationResult


def _capture_generator(monkeypatch):
    gen = DoorGenerator(api_key="test-key")
    captured = {}

    def fake_call(contents, config, label=""):
        captured["contents"] = contents
        return None, GenerationResult(image_data=None, thought_signature=None, error="stub")

    monkeypatch.setattr(gen, "_call_with_retry", fake_call)
    return gen, captured


def _image_parts(captured):
    return [p for p in captured["contents"][0].parts if p.inline_data is not None]


def _prompt_text(captured):
    return captured["contents"][0].parts[0].text


def test_learn_without_profile_is_unchanged(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    gen.learn_door_style(door_image_path=door)
    assert len(_image_parts(cap)) == 1
    assert "CROSS-SECTION" not in _prompt_text(cap)


def test_learn_with_profile_attaches_drawing_and_framing_line(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    drawing = tmp_path / "3d-profile.jpg"
    drawing.write_bytes(b"\xff\xd8xsec")
    gen.learn_door_style(door_image_path=door, profile_image_path=drawing)
    imgs = _image_parts(cap)
    assert len(imgs) == 2
    assert imgs[1].inline_data.data == b"\xff\xd8xsec"
    text = _prompt_text(cap)
    assert "CROSS-SECTION" in text and "line-art" in text


def test_learn_with_missing_profile_path_behaves_as_none(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    gen.learn_door_style(door_image_path=door,
                         profile_image_path=tmp_path / "missing.jpg")
    assert len(_image_parts(cap)) == 1
    assert "CROSS-SECTION" not in _prompt_text(cap)
