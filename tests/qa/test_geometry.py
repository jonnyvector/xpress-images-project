"""Tests for the deterministic geometry measurement core.

Synthetic fixtures are rendered with Pillow at EXACT known ratios, overlaid
with procedural grain (low-frequency vertical streaks + gaussian noise, fixed
seed) and round-tripped through JPEG before measurement, so ground truth is
exact by construction while the input is realistically noisy.
"""

import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from backend.qa.geometry import (
    GeometryConfig,
    GeometryReport,
    _match_boundaries,
    _measure_image,
    _strong_unmatched,
    measure,
)

FRAME_GRAY = 120
PANEL_GRAY = 180
BG = 247

FIXTURES = Path(__file__).parent / "fixtures" / "geometry"
needs_fixtures = pytest.mark.skipif(
    not FIXTURES.exists(), reason="real-photo fixtures not exported (M4 spike)"
)


def build_door(
    path: Path,
    *,
    stile: float = 0.12,
    rail: float = 0.10,
    dw: int = 1200,
    dh: int = 1500,
    margin: float = 0.08,
    seed: int = 0,
    center_stile: bool = False,
    panel_left_shift: float = 0.0,
    jpeg_quality: int = 85,
    grain: bool = True,
) -> dict[str, float]:
    """Render a framed door with exact ratios + grain + JPEG. Return ground truth.

    Returns normalized (fraction-of-door) ground-truth boundaries: the inner
    edges of the stiles (left/right) and rails (top/bottom).
    """
    rng = np.random.default_rng(seed)
    mw = int(dw * margin)
    mh = int(dh * margin)
    width = dw + 2 * mw
    height = dh + 2 * mh
    img = np.full((height, width), float(BG))
    x0, y0 = mw, mh
    img[y0 : y0 + dh, x0 : x0 + dw] = FRAME_GRAY
    sw = int(round(stile * dw))
    rw = int(round(rail * dh))
    shift = int(round(panel_left_shift * dw))
    px0 = x0 + sw - shift
    px1 = x0 + dw - sw - shift
    py0 = y0 + rw
    py1 = y0 + dh - rw
    img[py0:py1, px0:px1] = PANEL_GRAY
    if center_stile:
        cx = x0 + dw // 2
        half = max(2, sw // 2)
        img[py0:py1, cx - half : cx + half] = FRAME_GRAY
    if grain:
        xs = np.arange(width)
        streak = 8.0 * np.sin(2 * np.pi * xs / (width / 6.0))
        img += streak[None, :]
        img += rng.normal(0.0, 4.0, size=img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    Image.fromarray(img, mode="L").save(path, format="JPEG", quality=jpeg_quality)
    return {
        "left": (sw - shift) / dw,
        "right": (dw - sw - shift) / dw,
        "top": rw / dh,
        "bottom": (dh - rw) / dh,
    }


def _config() -> GeometryConfig:
    return GeometryConfig(
        measurable_styles=["frame_standard", "frame_narrow"],
        drift_thresholds={"frame_standard": 0.015, "frame_narrow": 0.02},
    )


# --- accuracy ----------------------------------------------------------------


def test_recovers_ratios_within_tolerance(tmp_path: Path) -> None:
    gt = build_door(tmp_path / "d.jpg", stile=0.12, rail=0.10, seed=7)
    m = _measure_image(tmp_path / "d.jpg", _config())
    assert m.ok, m.reason
    assert len(m.v_boundaries) == 2
    assert len(m.h_boundaries) == 2
    assert abs(m.v_boundaries[0] - gt["left"]) <= 0.005
    assert abs(m.v_boundaries[1] - gt["right"]) <= 0.005
    assert abs(m.h_boundaries[0] - gt["top"]) <= 0.005
    assert abs(m.h_boundaries[1] - gt["bottom"]) <= 0.005


def test_identical_geometry_is_ok_high_confidence(tmp_path: Path) -> None:
    build_door(tmp_path / "ref.jpg", seed=1)
    build_door(tmp_path / "cand.jpg", seed=2)  # same ratios, different grain
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k1", _config(), "frame_standard")
    assert rep.status == "ok"
    assert rep.confidence == "high"
    assert rep.max_delta <= 0.005
    assert rep.unmatched_boundaries == 0


# --- distortion detection ----------------------------------------------------


@pytest.mark.parametrize("delta", [0.02, 0.03])
def test_stile_widening_detected(tmp_path: Path, delta: float) -> None:
    build_door(tmp_path / "ref.jpg", stile=0.12, seed=1)
    build_door(tmp_path / "cand.jpg", stile=0.12 + delta, seed=2)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert rep.status == "drift"
    assert rep.max_delta > 0.015
    assert "stile" in rep.detail


def test_rail_widening_detected(tmp_path: Path) -> None:
    build_door(tmp_path / "ref.jpg", rail=0.10, seed=1)
    build_door(tmp_path / "cand.jpg", rail=0.13, seed=2)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert rep.status == "drift"
    assert "rail" in rep.detail


def test_panel_shift_detected(tmp_path: Path) -> None:
    build_door(tmp_path / "ref.jpg", seed=1)
    build_door(tmp_path / "cand.jpg", panel_left_shift=0.03, seed=2)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert rep.status == "drift"
    assert rep.max_delta > 0.015


def test_added_center_boundary_is_unmatched_not_folded(tmp_path: Path) -> None:
    build_door(tmp_path / "ref.jpg", seed=1)
    build_door(tmp_path / "cand.jpg", center_stile=True, seed=2)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    # A center stile adds interior boundaries with no reference match: they are
    # counted, not folded into the frame-width deltas.
    assert rep.unmatched_boundaries >= 1
    assert rep.max_delta <= 0.01
    # The added structure must never be a confident clean pass.
    assert not (rep.status == "ok" and rep.confidence == "high")


def test_single_extra_boundary_high_confidence_is_drift(tmp_path: Path) -> None:
    # One added boundary (count diff 1) stays high-confidence -> unmatched->drift.
    ref = [0.15, 0.85]
    cand = [0.15, 0.55, 0.85]
    deltas, unmatched = _match_boundaries(ref, cand, gap=0.05)
    assert unmatched == 1
    assert max(deltas) <= 0.001


# --- DP boundary matching (direct) -------------------------------------------


def test_dp_spurious_peak_does_not_cascade() -> None:
    ref = [0.2, 0.4, 0.6, 0.8]
    cand = [0.2, 0.4, 0.5, 0.6, 0.8]  # 0.5 is spurious
    deltas, unmatched = _match_boundaries(ref, cand, gap=0.05)
    assert unmatched == 1
    assert len(deltas) == 4
    assert max(deltas) <= 0.001  # real boundaries still matched exactly


def test_dp_unmatched_strong_boundary_counted_separately() -> None:
    ref = [0.15, 0.85]
    cand = [0.15, 0.5, 0.85]
    deltas, unmatched = _match_boundaries(ref, cand, gap=0.05)
    assert unmatched == 1
    assert max(deltas) <= 0.001


# --- error paths -------------------------------------------------------------


def test_geo001_unreadable_file(tmp_path: Path) -> None:
    good = tmp_path / "ref.jpg"
    build_door(good, seed=1)
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    rep = measure(good, bad, "k", _config(), "frame_standard")
    assert rep.status == "unmeasurable"
    assert "GEO-001" in rep.detail


def test_geo002_box_confidence_failure(tmp_path: Path) -> None:
    build_door(tmp_path / "ref.jpg", seed=1)
    # Candidate: normal door but clutter/specks in the margin -> margin check fails.
    rng = np.random.default_rng(3)
    dw, dh = 1200, 1500
    mw, mh = 300, 375
    width, height = dw + 2 * mw, dh + 2 * mh
    img = np.full((height, width), float(BG))
    img[mh : mh + dh, mw : mw + dw] = FRAME_GRAY
    img[mh + 100 : mh + dh - 100, mw + 100 : mw + dw - 100] = PANEL_GRAY
    speck = rng.random((height, width)) < 0.06
    outside = np.ones((height, width), dtype=bool)
    outside[mh : mh + dh, mw : mw + dw] = False
    img[speck & outside] = 0.0
    img = np.clip(img, 0, 255).astype(np.uint8)
    Image.fromarray(img, mode="L").save(tmp_path / "cand.jpg", format="JPEG", quality=90)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert rep.status == "unmeasurable"
    assert "GEO-002" in rep.detail
    assert "candidate" in rep.detail


def test_geo003_no_interior_peaks_is_partial_low_confidence(tmp_path: Path) -> None:
    # Solid gray rectangle: box detectable, but no interior frame/panel boundary.
    def solid(path: Path, seed: int) -> None:
        rng = np.random.default_rng(seed)
        dw, dh, mw, mh = 1200, 1500, 100, 120
        img = np.full((dh + 2 * mh, dw + 2 * mw), float(BG))
        img[mh : mh + dh, mw : mw + dw] = FRAME_GRAY
        img += rng.normal(0.0, 4.0, size=img.shape)
        img = np.clip(img, 0, 255).astype(np.uint8)
        Image.fromarray(img, mode="L").save(path, format="JPEG", quality=85)

    solid(tmp_path / "ref.jpg", 1)
    solid(tmp_path / "cand.jpg", 2)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert rep.status != "unmeasurable"
    assert rep.confidence == "low"
    assert "GEO-003" in rep.detail


def test_geo004_injected_exception_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_door(tmp_path / "ref.jpg", seed=1)
    build_door(tmp_path / "cand.jpg", seed=2)

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("injected")

    monkeypatch.setattr("backend.qa.geometry._measure_image", boom)
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    assert isinstance(rep, GeometryReport)
    assert rep.status == "unmeasurable"
    assert "GEO-004" in rep.detail


# --- strong-peak floor for unmatched boundaries (unit) ------------------------


def test_weak_unmatched_peak_does_not_count() -> None:
    # Unmatched peak at 40% of the median matched strength: grain/shadow, not
    # structure.
    flat = np.zeros(100)
    n = _strong_unmatched([0], [0.5], [0.12], [0.3, 0.3, 0.3], flat)
    assert n == 0


def test_strong_unmatched_peak_counts_when_other_image_is_flat() -> None:
    flat = np.full(100, 0.005)  # grain-level energy only
    n = _strong_unmatched([0], [0.5], [0.3], [0.3, 0.3, 0.3], flat)
    assert n == 1


def test_strong_unmatched_peak_suppressed_by_cross_energy() -> None:
    # The other image carries a real (if weaker) edge at the same position:
    # tone-dependent detection asymmetry, not drift.
    energy = np.full(100, 0.005)
    energy[48:52] = 0.15  # clearly-real edge at position ~0.5
    n = _strong_unmatched([0], [0.5], [0.6], [0.3, 0.3, 0.3], energy)
    assert n == 0


def test_no_matched_structure_counts_all_unmatched_failsafe() -> None:
    n = _strong_unmatched([0, 1], [0.3, 0.7], [0.05, 0.04], [], np.zeros(100))
    assert n == 2


# --- real-photo fixtures (M4 spike regressions) --------------------------------


@needs_fixtures
def test_full_bleed_real_samples_are_measurable() -> None:
    # These real photographed samples returned GEO-002 before the full-frame
    # fallback: the door fills the frame, so there is no background to find.
    for name in ("4ebf2d15_1_replica_-1", "571ae351_2_replica_-1", "23d3dae0_1_replica_-1"):
        m = _measure_image(FIXTURES / name / "sample.jpg", _config())
        assert m.ok, f"{name}: {m.reason}"
        assert m.full_bleed
        assert not m.forced_low  # clean full-bleed stays high-confidence eligible


@needs_fixtures
def test_pale_wood_full_bleed_measurable_at_forced_low() -> None:
    # Light maple fills the frame; the border median sits in the near-white
    # band, so margin evidence is genuinely ambiguous -> measurable, low conf.
    m = _measure_image(FIXTURES / "92e60a19_11_replica_-1" / "sample.jpg", _config())
    assert m.ok, m.reason
    assert m.full_bleed
    assert m.forced_low


@needs_fixtures
def test_clean_full_bleed_replica_pair_measures_high_confidence() -> None:
    d = FIXTURES / "571ae351_0_replica_-1"
    rep = measure(d / "sample.jpg", d / "candidate.jpg", "k", _config(), "frame_standard")
    assert rep.status == "ok"
    assert rep.confidence == "high"


@needs_fixtures
def test_full_bleed_crop_aspect_is_not_drift_evidence() -> None:
    # The sample is a square catalog crop: its frame aspect is not the door
    # aspect. A human accepted this replica; aspect alone must not flag it.
    d = FIXTURES / "4ebf2d15_0_replica_-1"
    rep = measure(d / "sample.jpg", d / "candidate.jpg", "k", _config(), "frame_standard")
    assert rep.status != "unmeasurable"
    assert rep.aspect_delta > 0.3  # the bogus crop-aspect signal is present...
    assert "unverified: full-bleed crop" in rep.detail  # ...and explicitly ignored


@needs_fixtures
@pytest.mark.parametrize(
    "name",
    ["2564359f_0_variant_0", "2564359f_0_variant_2", "40236826_0_variant_1"],
)
def test_accepted_variants_not_flagged_by_weak_unmatched_peaks(name: str) -> None:
    # Human-accepted variants previously flagged drift at high confidence via
    # unmatched grain/shadow peaks and tone-dependent edge detection asymmetry.
    d = FIXTURES / name
    rep = measure(
        d / "replica.jpg", d / "candidate.jpg", "k", _config(), "frame_standard",
        reference="replica",
    )
    assert rep.status == "ok", rep.detail
    assert rep.unmatched_boundaries == 0


# --- timing (informational) --------------------------------------------------


def test_timing_benchmark(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build_door(tmp_path / "ref.jpg", dw=1536, dh=1900, seed=1)
    build_door(tmp_path / "cand.jpg", dw=1536, dh=1900, seed=2)
    t0 = time.perf_counter()
    rep = measure(tmp_path / "ref.jpg", tmp_path / "cand.jpg", "k", _config(), "frame_standard")
    elapsed = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\n[geometry] per-pair measure() at 1536px: {elapsed * 1000:.1f} ms")
    assert rep.status in ("ok", "drift")
    assert elapsed < 5.0
