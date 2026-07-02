"""Deterministic structural measurement of framed cabinet doors; compares
candidate vs reference as scale-invariant ratios; fail-safe: every failure is
`unmeasurable`, never an exception or silent pass.

Pipeline (numpy + Pillow only, no scipy/cv2):

1. load + grayscale at min(native, working_width)px
2. detect the door box by foreground extent with confidence checks
   (min_box_fraction, near-white/low-variance margin, aspect sanity)
3. build directional edge-energy profiles inside the box (Sobel gradients)
4. detect interior frame/panel boundaries with two-scale peak persistence
   (grain suppression) + parabolic sub-pixel refinement
5. express every measurement as a fraction of the door dimension and compare
   reference vs candidate via order-preserving DP boundary matching
6. compose a confidence-qualified verdict (ok | drift | unmeasurable)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

# Foreground is at least this much darker (normalized) than the near-white bg.
_FG_MARGIN = 0.10
# A column/row counts as "door" if at least this fraction of it is foreground.
_COVERAGE = 0.5
# Margin (outside the box) must be near-white with low variance to trust the box.
_MARGIN_MIN_MEAN = 0.85
_MARGIN_MAX_STD = 0.15
# Ignore peaks this close (fraction of dim) to the box edge — that is the door
# outline, not an interior frame/panel boundary.
_EDGE_MARGIN = 0.02
# DP gap penalty (normalized position units): boundaries farther apart than this
# are cheaper left unmatched than force-matched.
_MATCH_GAP = 0.05
# Two smoothing scales, as a fraction of the profile dimension.
_FINE_SCALE = 0.005
_COARSE_SCALE = 0.02
# Absolute edge-strength floor (mean |gradient| per summed pixel) at the peak.
# Scale-invariant: a real frame/panel step clears this by ~10x; grain/JPEG does not.
_MIN_EDGE_STRENGTH = 0.03
# The coarse scale attenuates sharp edges, so it only needs a fraction of the
# floor to confirm the peak persists across scales (grain suppression).
_COARSE_PERSIST_FACTOR = 0.25


@dataclass
class GeometryConfig:
    measurable_styles: list[str] = field(default_factory=list)
    working_width: int = 1536  # min(native, this)
    drift_thresholds: dict[str, float] = field(default_factory=dict)  # per style-class
    aspect_threshold: float = 0.04
    min_box_fraction: float = 0.40
    min_peak_prominence: float = 0.15
    max_match_residual: float = 0.02


@dataclass
class GeometryReport:
    key: str
    status: str  # "ok" | "drift" | "unmeasurable"
    confidence: str  # "high" | "low"
    reference: str  # "sample" | "replica"
    aspect_delta: float
    stile_deltas: dict[str, float]
    rail_deltas: dict[str, float]
    boundary_deltas: list[float]
    unmatched_boundaries: int
    max_delta: float
    detail: str


@dataclass
class ImageMeasurement:
    """Per-image structural measurement (observability surface for eval/tests)."""

    ok: bool
    reason: str  # "" if ok, else "<check>" describing the box failure
    aspect: float
    box_fraction: float
    v_boundaries: list[float]  # normalized interior vertical boundary positions
    h_boundaries: list[float]  # normalized interior horizontal boundary positions


# --- image loading -----------------------------------------------------------


def _load_gray(path: Path, working_width: int) -> np.ndarray:
    image = Image.open(path)
    image.load()
    image = image.convert("L")
    if image.width > working_width:
        new_h = max(1, round(image.height * working_width / image.width))
        image = image.resize((working_width, new_h), Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float64) / 255.0


# --- Sobel (numpy convolution, no scipy) -------------------------------------

_SOBEL_X = np.array([[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]])
_SOBEL_Y = np.array([[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]])


def _conv3(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    padded = np.pad(img, 1, mode="edge")
    out = np.zeros_like(img)
    for di in range(3):
        for dj in range(3):
            out += kernel[di, dj] * padded[di : di + img.shape[0], dj : dj + img.shape[1]]
    return out


# --- box detection -----------------------------------------------------------


def _detect_box(
    img: np.ndarray, config: GeometryConfig
) -> tuple[int, int, int, int, bool, str]:
    """Return (left, right, top, bottom, ok, reason). Bounds are inclusive."""
    height, width = img.shape
    border = np.concatenate([img[0, :], img[-1, :], img[:, 0], img[:, -1]])
    bg = float(np.median(border))
    fg = img < (bg - _FG_MARGIN)
    col_ok = fg.mean(axis=0) > _COVERAGE
    row_ok = fg.mean(axis=1) > _COVERAGE
    cols = np.flatnonzero(col_ok)
    rows = np.flatnonzero(row_ok)
    if cols.size == 0 or rows.size == 0:
        return 0, 0, 0, 0, False, "no door foreground detected"
    left, right = int(cols[0]), int(cols[-1])
    top, bottom = int(rows[0]), int(rows[-1])
    box_w, box_h = right - left + 1, bottom - top + 1

    fraction = (box_w * box_h) / (width * height)
    if fraction < config.min_box_fraction:
        return left, right, top, bottom, False, f"box_fraction {fraction:.3f} < min"

    outside = np.ones(img.shape, dtype=bool)
    outside[top : bottom + 1, left : right + 1] = False
    if outside.any():
        margin = img[outside]
        if float(margin.mean()) < _MARGIN_MIN_MEAN or float(margin.std()) > _MARGIN_MAX_STD:
            return left, right, top, bottom, False, "margin not near-white/low-variance"

    aspect = box_w / box_h
    if not (0.2 <= aspect <= 5.0):
        return left, right, top, bottom, False, f"aspect {aspect:.2f} out of sanity range"
    return left, right, top, bottom, True, ""


# --- profiles + peaks --------------------------------------------------------


def _smooth(sig: np.ndarray, window: int, passes: int = 1) -> np.ndarray:
    window = max(1, window)
    if window == 1:
        return sig
    kernel = np.ones(window) / window
    out = sig
    for _ in range(passes):  # repeated box filter -> triangular/Gaussian-like
        out = np.convolve(out, kernel, mode="same")
    return out


def _windowed_range(sig: np.ndarray, i: int, half: int) -> float:
    lo, hi = max(0, i - half), min(len(sig), i + half + 1)
    seg = sig[lo:hi]
    return float(seg.max() - seg.min())


def _prominence(sig: np.ndarray, i: int) -> float:
    peak = sig[i]
    left_min = peak
    j = i - 1
    while j >= 0 and sig[j] < peak:
        left_min = min(left_min, sig[j])
        j -= 1
    right_min = peak
    j = i + 1
    while j < len(sig) and sig[j] < peak:
        right_min = min(right_min, sig[j])
        j += 1
    return float(peak - max(left_min, right_min))


def _local_maxima(sig: np.ndarray) -> list[int]:
    return [i for i in range(1, len(sig) - 1) if sig[i] >= sig[i - 1] and sig[i] > sig[i + 1]]


def _refine(sig: np.ndarray, i: int) -> float:
    if i <= 0 or i >= len(sig) - 1:
        return float(i)
    a, b, c = sig[i - 1], sig[i], sig[i + 1]
    denom = a - 2 * b + c
    if denom == 0:
        return float(i)
    offset = 0.5 * (a - c) / denom
    if abs(offset) > 1.0:
        return float(i)
    return i + offset


def _boundaries(profile: np.ndarray, perp: int, config: GeometryConfig) -> list[float]:
    """Interior boundary positions in [0, 1], grain-suppressed + sub-pixel.

    `profile` is the edge energy summed over `perp` pixels (the perpendicular box
    dimension); dividing prominence by `perp` yields a scale-invariant per-pixel
    edge strength that separates real frame/panel steps from grain and JPEG noise.
    """
    dim = len(profile)
    if dim < 5 or perp <= 0:
        return []
    span = float(profile.max() - profile.min())
    if span <= 0:
        return []
    fine = _smooth(profile, round(_FINE_SCALE * dim))
    coarse = _smooth(profile, round(_COARSE_SCALE * dim), passes=2)
    tol = max(round(_COARSE_SCALE * dim), round(0.01 * dim), 2)
    coarse_floor = _MIN_EDGE_STRENGTH * _COARSE_PERSIST_FACTOR
    edge = round(_EDGE_MARGIN * dim)
    positions: list[float] = []
    for i in _local_maxima(fine):
        if i < edge or i > dim - 1 - edge:
            continue
        raw = _prominence(fine, i)
        if raw / perp < _MIN_EDGE_STRENGTH:  # absolute contrast gate (flat/grain)
            continue
        if raw / span < config.min_peak_prominence:  # relative shape gate
            continue
        # Two-scale persistence: the coarse-smoothed profile must still carry a
        # real energy bump at this location. Grain spikes vanish under coarse
        # smoothing; genuine frame/panel edges persist.
        if _windowed_range(coarse, i, tol) / perp < coarse_floor:
            continue
        positions.append(_refine(fine, i) / (dim - 1))
    positions.sort()
    return _dedupe(positions, min_gap=2.0 / dim)


def _dedupe(positions: list[float], min_gap: float) -> list[float]:
    out: list[float] = []
    for p in positions:
        if not out or p - out[-1] >= min_gap:
            out.append(p)
    return out


# --- DP boundary matching ----------------------------------------------------


def _match_boundaries(
    ref: list[float], cand: list[float], gap: float
) -> tuple[list[float], int]:
    """Order-preserving (monotonic) alignment. Returns (matched deltas, unmatched).

    Unmatched peaks are penalized by `gap` and reported as a count, never folded
    into the matched deltas.
    """
    m, n = len(ref), len(cand)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        dp[i][0] = i * gap
    for j in range(1, n + 1):
        dp[0][j] = j * gap
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            match = dp[i - 1][j - 1] + abs(ref[i - 1] - cand[j - 1])
            dp[i][j] = min(match, dp[i - 1][j] + gap, dp[i][j - 1] + gap)
    i, j = m, n
    deltas: list[float] = []
    unmatched = 0
    while i > 0 and j > 0:
        match = dp[i - 1][j - 1] + abs(ref[i - 1] - cand[j - 1])
        if dp[i][j] == match:
            deltas.append(abs(ref[i - 1] - cand[j - 1]))
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j] + gap:
            unmatched += 1
            i -= 1
        else:
            unmatched += 1
            j -= 1
    unmatched += i + j
    deltas.reverse()
    return deltas, unmatched


# --- per-image measurement ---------------------------------------------------


def _measure_image(path: Path, config: GeometryConfig) -> ImageMeasurement:
    img = _load_gray(path, config.working_width)
    left, right, top, bottom, ok, reason = _detect_box(img, config)
    if not ok:
        return ImageMeasurement(False, reason, 0.0, 0.0, [], [])
    crop = img[top : bottom + 1, left : right + 1]
    box_w, box_h = crop.shape[1], crop.shape[0]
    aspect = box_w / box_h
    fraction = (box_w * box_h) / (img.shape[0] * img.shape[1])
    gx = _conv3(crop, _SOBEL_X)
    gy = _conv3(crop, _SOBEL_Y)
    v_profile = np.abs(gx).sum(axis=0)  # over rows -> vertical edges along x
    h_profile = np.abs(gy).sum(axis=1)  # over columns -> horizontal edges along y
    v_boundaries = _boundaries(v_profile, box_h, config)
    h_boundaries = _boundaries(h_profile, box_w, config)
    return ImageMeasurement(True, "", aspect, fraction, v_boundaries, h_boundaries)


# --- public entry point ------------------------------------------------------


def measure(
    reference_path: Path,
    candidate_path: Path,
    key: str,
    config: GeometryConfig,
    style_class: str,
    *,
    reference: str = "sample",
) -> GeometryReport:
    """Measure candidate vs reference. Never raises: every failure is unmeasurable."""
    try:
        return _measure(reference_path, candidate_path, key, config, style_class, reference)
    except FileNotFoundError as exc:
        return _unmeasurable(key, reference, f"GEO-001: unreadable image: {exc}")
    except (OSError, ValueError) as exc:  # PIL decode / bad data
        return _unmeasurable(key, reference, f"GEO-001: unreadable image: {exc}")
    except Exception as exc:  # noqa: BLE001 — fail-safe boundary (GEO-004)
        return _unmeasurable(key, reference, f"GEO-004: internal error: {exc}")


def _unmeasurable(key: str, reference: str, detail: str) -> GeometryReport:
    return GeometryReport(
        key=key,
        status="unmeasurable",
        confidence="low",
        reference=reference,
        aspect_delta=0.0,
        stile_deltas={},
        rail_deltas={},
        boundary_deltas=[],
        unmatched_boundaries=0,
        max_delta=0.0,
        detail=detail,
    )


def _measure(
    reference_path: Path,
    candidate_path: Path,
    key: str,
    config: GeometryConfig,
    style_class: str,
    reference: str,
) -> GeometryReport:
    ref = _measure_image(reference_path, config)
    if not ref.ok:
        return _unmeasurable(key, reference, f"GEO-002: reference box check failed: {ref.reason}")
    cand = _measure_image(candidate_path, config)
    if not cand.ok:
        return _unmeasurable(key, reference, f"GEO-002: candidate box check failed: {cand.reason}")

    aspect_delta = abs(cand.aspect - ref.aspect) / ref.aspect if ref.aspect else 0.0

    v_deltas, v_unmatched = _match_boundaries(ref.v_boundaries, cand.v_boundaries, _MATCH_GAP)
    h_deltas, h_unmatched = _match_boundaries(ref.h_boundaries, cand.h_boundaries, _MATCH_GAP)
    boundary_deltas = v_deltas + h_deltas
    unmatched = v_unmatched + h_unmatched

    stile_deltas = _edge_deltas(ref.v_boundaries, cand.v_boundaries, "left", "right")
    rail_deltas = _edge_deltas(ref.h_boundaries, cand.h_boundaries, "top", "bottom")

    named: dict[str, float] = {}
    named.update({f"stile.{k}": v for k, v in stile_deltas.items()})
    named.update({f"rail.{k}": v for k, v in rail_deltas.items()})
    named.update({f"boundary.{i}": d for i, d in enumerate(boundary_deltas)})
    max_delta = max(named.values(), default=0.0)
    worst_name = max(named, key=lambda k: named[k], default="none")

    partial = not (ref.v_boundaries and cand.v_boundaries) or not (
        ref.h_boundaries and cand.h_boundaries
    )
    counts_agree = (
        abs((len(ref.v_boundaries) + len(ref.h_boundaries))
            - (len(cand.v_boundaries) + len(cand.h_boundaries))) <= 1
    )
    mean_residual = float(np.mean(boundary_deltas)) if boundary_deltas else float("inf")
    confidence = (
        "high"
        if (not partial and counts_agree and mean_residual <= config.max_match_residual)
        else "low"
    )

    threshold = config.drift_thresholds.get(
        style_class, config.drift_thresholds.get("frame_standard", 0.02)
    )
    drift = (
        max_delta > threshold
        or aspect_delta > config.aspect_threshold
        or (unmatched > 0 and confidence == "high")
    )
    status = "drift" if drift else "ok"

    detail = _detail(
        status, worst_name, max_delta, threshold, aspect_delta,
        unmatched, reference, confidence, partial,
    )
    return GeometryReport(
        key=key,
        status=status,
        confidence=confidence,
        reference=reference,
        aspect_delta=aspect_delta,
        stile_deltas=stile_deltas,
        rail_deltas=rail_deltas,
        boundary_deltas=boundary_deltas,
        unmatched_boundaries=unmatched,
        max_delta=max_delta,
        detail=detail,
    )


def _edge_deltas(
    ref: list[float], cand: list[float], near_key: str, far_key: str
) -> dict[str, float]:
    """Outer-frame width deltas from the first/last interior boundary on an axis."""
    if not ref or not cand:
        return {}
    near = abs(cand[0] - ref[0])  # left stile / top rail width
    far = abs((1 - cand[-1]) - (1 - ref[-1]))  # right stile / bottom rail width
    return {near_key: near, far_key: far}


def _detail(
    status: str,
    worst_name: str,
    max_delta: float,
    threshold: float,
    aspect_delta: float,
    unmatched: int,
    reference: str,
    confidence: str,
    partial: bool,
) -> str:
    parts = [
        f"{status}",
        f"worst {worst_name}={max_delta:.3f} (thr {threshold:.3f})",
        f"aspect_delta={aspect_delta:.3f}",
        f"unmatched={unmatched}",
        f"ref={reference}",
        f"conf={confidence}",
    ]
    if partial:
        parts.append("GEO-003: partial (missing interior boundaries on an axis)")
    return "; ".join(parts)
