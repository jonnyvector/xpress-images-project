import json
from pathlib import Path

import pytest

# Minimal JPEG header so magic-byte sniffing sees a JPEG.
JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"\x00" * 32


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    root = tmp_path / ".projects"
    d = root / "abc123"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "name": "Shaker Maple",
                "door_style": "shaker",
                "result_names": ["Cherry Natural", "Walnut Select"],
            }
        )
    )
    (d / "upload.bin").write_bytes(JPEG)
    (d / "base_door.bin").write_bytes(JPEG)
    (d / "result_0.bin").write_bytes(JPEG)
    (d / "result_1.bin").write_bytes(JPEG)
    v1 = d / "versions" / "v1"
    v1.mkdir(parents=True)
    (v1 / "base_door.bin").write_bytes(JPEG)
    (v1 / "result_0.bin").write_bytes(JPEG)
    (v1 / "result_names.json").write_text(json.dumps(["Cherry Natural"]))
    (v1 / "meta.json").write_text(
        json.dumps(
            {"version": 1, "created_at": "2026-01-01T00:00:00+00:00", "door_style": "shaker"}
        )
    )
    # A project with no upload.bin (real case: e.g. project c81e6ddf).
    d2 = root / "def456"
    d2.mkdir()
    (d2 / "manifest.json").write_text(
        json.dumps({"id": "def456", "name": "Durango", "result_names": ["Walnut Select"]})
    )
    (d2 / "result_0.bin").write_bytes(JPEG)
    return root


@pytest.fixture
def swatches_dir(tmp_path: Path) -> Path:
    root = tmp_path / "swatches"
    (root / "wood").mkdir(parents=True)
    (root / "wood_types.json").write_text(
        json.dumps(
            {
                "cherry-natural": {"name": "Cherry Natural", "description": ""},
                "walnut-select": {"name": "Walnut Select", "description": ""},
            }
        )
    )
    (root / "rtf_types.json").write_text("{}")
    # Note: underscore filename while slug uses hyphens — mirrors the real swatches/ dir.
    (root / "wood" / "cherry_natural.jpg").write_bytes(JPEG)
    return root
