"""Tests for DoorGenerator._call_with_retry behavior with a mocked client."""

from types import SimpleNamespace

from backend.generator import DoorGenerator


def _fake_response(image: bytes = b"img", signature: bytes = b"sig") -> SimpleNamespace:
    part = SimpleNamespace(thought_signature=signature, inline_data=SimpleNamespace(data=image))
    candidate = SimpleNamespace(content=SimpleNamespace(parts=[part]))
    return SimpleNamespace(candidates=[candidate])


class _FlakyModels:
    """Raises a 429 once, then succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("429 rate limit exceeded")
        return _fake_response()


class _AlwaysRateLimited:
    def __init__(self) -> None:
        self.calls = 0

    def generate_content(self, **_kwargs):
        self.calls += 1
        raise RuntimeError("429 quota exceeded")


def _generator(models) -> DoorGenerator:
    gen = DoorGenerator(api_key="test-key")
    gen.client = SimpleNamespace(models=models)
    gen.RETRY_DELAY = 0  # no real backoff sleep in tests
    return gen


def test_retry_recovers_after_one_429() -> None:
    models = _FlakyModels()
    gen = _generator(models)
    result = gen.generate_variation(
        swatch_image_path=None,
        wood_name="Oak",
        base_signature=b"base-sig",
    )
    assert models.calls == 2
    assert result.error is None
    assert result.image_data == b"img"


def test_retry_exhausts_and_reports_rate_limit() -> None:
    models = _AlwaysRateLimited()
    gen = _generator(models)
    result = gen.generate_variation(
        swatch_image_path=None,
        wood_name="Oak",
        base_signature=b"base-sig",
    )
    assert models.calls == DoorGenerator.MAX_RETRIES
    assert result.image_data is None
    assert "Rate limited" in (result.error or "")
