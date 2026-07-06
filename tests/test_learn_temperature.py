"""M2: learn_door_style gains temperature + style_notes without changing defaults."""

from pathlib import Path

from backend.generator import DoorGenerator


class _FakeClient:
    """Captures the config/contents passed to generate_content."""

    def __init__(self):
        self.captured = {}
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.captured["config"] = config
        self.captured["contents"] = contents

        class _Resp:
            candidates = []

        return _Resp()


def _gen_with_fake():
    gen = DoorGenerator(api_key="x")
    fake = _FakeClient()
    gen.client = fake
    return gen, fake


def _sample(tmp_path) -> Path:
    p = tmp_path / "door.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    return p


def test_default_temperature_is_zero(tmp_path):
    gen, fake = _gen_with_fake()
    gen.learn_door_style(door_image_path=_sample(tmp_path), material_type="rtf")
    assert fake.captured["config"].temperature == 0.0


def test_temperature_reaches_config(tmp_path):
    gen, fake = _gen_with_fake()
    gen.learn_door_style(door_image_path=_sample(tmp_path), temperature=0.4)
    assert fake.captured["config"].temperature == 0.4


def test_style_notes_reach_prompt(tmp_path):
    gen, fake = _gen_with_fake()
    gen.learn_door_style(
        door_image_path=_sample(tmp_path),
        style_notes="ARCHED cathedral top rail.",
    )
    prompt = fake.captured["contents"][0].parts[0].text
    assert "ARCHED cathedral top rail." in prompt


def test_no_style_notes_leaves_no_structural_block(tmp_path):
    gen, fake = _gen_with_fake()
    gen.learn_door_style(door_image_path=_sample(tmp_path))
    prompt = fake.captured["contents"][0].parts[0].text
    assert "STRUCTURAL DETAILS" not in prompt
