"""Deterministic structural measurement of framed cabinet doors; compares
candidate vs reference as scale-invariant ratios; fail-safe: every failure is
`unmeasurable`, never an exception or silent pass.

Pipeline (numpy + Pillow only, no scipy/cv2):

1. load + grayscale at min(native, working_width)px
2. detect the door box: foreground extent on near-white backgrounds with
   confidence checks (min_box_fraction, near-white/low-variance margin,
   aspect sanity); full-frame fallback for full-bleed real photos where the
   door fills the frame (ambiguous margins force low confidence)
3. build directional edge-energy profiles inside the box (Sobel gradients)
4. detect interior frame/panel boundaries with two-scale peak persistence
   (grain suppression) + parabolic sub-pixel refinement
5. express every measurement as a fraction of the door dimension and compare
   reference vs candidate via order-preserving DP boundary matching; only
   unmatched peaks as strong as the matched structure count as mismatches
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
# Border median below this -> the image is a clean full-bleed door photo (the
# door surface itself reaches the frame edges; there is no background to find).
# Between this and _MARGIN_MIN_MEAN the margin evidence is genuinely ambiguous:
# still measurable via the full-frame box, but confidence is forced low.
_FULL_BLEED_MAX = 0.70
# A near-white border only counts as a clean render background when it is this
# white and this uniform; otherwise it may be pale wood filling the frame.
_CLEAN_BG_MED = 0.95
_CLEAN_BG_STD = 0.02
# Absolute edge-strength floor (mean |gradient| per summed pixel) at the peak.
# Scale-invariant: a real frame/panel step clears this by ~10x; grain/JPEG does not.
_MIN_EDGE_STRENGTH = 0.03
# An unmatched peak counts as a structural boundary only if its strength is
# comparable to the matched structural boundaries in the same image...
_UNMATCHED_STRENGTH_FACTOR = 0.6
# ...and the OTHER image shows no comparable edge energy at that position.
# (Different wood tones make different subsets of the same edges detectable;
# energy present in both images means shared structure, not drift.)
_CROSS_ENERGY_FACTOR = 0.5
# The energy required of the other image is capped: how sharply an edge renders
# depends on the wood tone, so a strong edge in one tone may be a moderate (yet
# clearly real) edge in another. Anything at 3x the absolute detection floor is
# unambiguously a real edge regardless of the unmatched peak's own strength.
_CROSS_ENERGY_CAP = 3 * _MIN_EDGE_STRENGTH
# Position tolerance (fraction of dim) for the check. Wide enough that a
# double-rendered shadow edge (e.g. groove shadow in dark wood) is covered by
# the single edge the other tone renders; a genuinely added frame member sits
# far from existing structure and is unaffected.
_CROSS_ENERGY_TOL = 0.04
# Ignore peaks this close (fraction of dim) to the box edge — that is the door
# outline, not an interior frame/panel boundary.
_EDGE_MARGIN = 0.02
# DP gap penalty (normalized position units): boundaries farther apart than this
# are cheaper left unmatched than force-matched.
_MATCH_GAP = 0.05
# Two smoothing scales, as a fraction of the profile dimension.
_FINE_SCALE = 0.005
_COARSE_SCALE = 0.02
# The coarse scale attenuates sharp edges, so it only needs a fraction of the
# _MIN_EDGE_STRENGTH floor to confirm the peak persists across scales.
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
    v_strengths: list[float] = field(default_factory=list)  # per-pixel edge strength
    h_strengths: list[float] = field(default_factory=list)
    forced_low: bool = False  # margin evidence ambiguous -> confidence capped at low
    full_bleed: bool = False  # box is the full frame -> crop aspect is not door aspect
    v_energy: np.ndarray | None = None  # smoothed per-pixel edge-energy profiles,
    h_energy: np.ndarray | None = None  # for cross-image structure checks


@dataclass
class _Box:
    left: int
    right: int
    top: int
    bottom: int
    ok: bool
    reason: str = ""
    forced_low: bool = False
    full_bleed: bool = False


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


def _full_frame_box(img: np.ndarray, forced_low: bool) -> _Box:
    height, width = img.shape
    aspect = width / height
    if not (0.2 <= aspect <= 5.0):
        return _Box(0, width - 1, 0, height - 1, False, f"aspect {aspect:.2f} out of range")
    return _Box(
        0, width - 1, 0, height - 1, True, forced_low=forced_low, full_bleed=True
    )


def _detect_box(img: np.ndarray, config: GeometryConfig) -> _Box:
    """Locate the door box. Two regimes:

    - near-white border (renders / product shots): foreground-extent box with
      the min_box_fraction, margin, and aspect confidence checks;
    - non-white border (real photos where the door fills the frame): full-frame
      box. A clearly door-toned border (< _FULL_BLEED_MAX) is a clean full-bleed
      photo and stays eligible for high confidence; a border in the ambiguous
      band forces confidence low.
    """
    height, width = img.shape
    border = np.concatenate([img[0, :], img[-1, :], img[:, 0], img[:, -1]])
    bg = float(np.median(border))
    border_std = float(border.std())

    if bg < _MARGIN_MIN_MEAN:
        # No near-white background exists: the content plausibly IS the door
        # (full-bleed photo). Fall back to the full frame as the box.
        return _full_frame_box(img, forced_low=bg >= _FULL_BLEED_MAX)

    clean_bg = bg >= _CLEAN_BG_MED and border_std <= _CLEAN_BG_STD
    fg = img < (bg - _FG_MARGIN)
    col_cov = fg.mean(axis=0)
    row_cov = fg.mean(axis=1)
    # Adaptive coverage: the door may occupy well under half of one dimension
    # (e.g. a wide drawer render). Half the peak coverage separates door
    # columns/rows from stray specks without a fixed 50% requirement.
    if min(col_cov.max(), row_cov.max()) < 0.15:
        if clean_bg:
            return _Box(0, 0, 0, 0, False, "no door foreground detected")
        # Near-white but textured border: plausibly pale wood filling the frame.
        return _full_frame_box(img, forced_low=True)
    cols = np.flatnonzero(col_cov > max(_COVERAGE * col_cov.max(), 0.05))
    rows = np.flatnonzero(row_cov > max(_COVERAGE * row_cov.max(), 0.05))
    left, right = int(cols[0]), int(cols[-1])
    top, bottom = int(rows[0]), int(rows[-1])
    box_w, box_h = right - left + 1, bottom - top + 1

    fraction = (box_w * box_h) / (width * height)
    if fraction < config.min_box_fraction:
        if clean_bg:
            return _Box(left, right, top, bottom, False, f"box_fraction {fraction:.3f} < min")
        return _full_frame_box(img, forced_low=True)

    outside = np.ones(img.shape, dtype=bool)
    outside[top : bottom + 1, left : right + 1] = False
    if outside.any():
        margin = img[outside]
        if float(margin.mean()) < _MARGIN_MIN_MEAN or float(margin.std()) > _MARGIN_MAX_STD:
            return _Box(left, right, top, bottom, False, "margin not near-white/low-variance")

    aspect = box_w / box_h
    if not (0.2 <= aspect <= 5.0):
        return _Box(left, right, top, bottom, False, f"aspect {aspect:.2f} out of sanity range")
    return _Box(left, right, top, bottom, True)


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


def _boundaries(
    profile: np.ndarray, perp: int, config: GeometryConfig
) -> tuple[list[float], list[float], np.ndarray | None]:
    """Interior boundary (positions, strengths, per-pixel energy profile).

    `profile` is the edge energy summed over `perp` pixels (the perpendicular box
    dimension); dividing prominence by `perp` yields a scale-invariant per-pixel
    edge strength that separates real frame/panel steps from grain and JPEG noise.
    Every returned peak has passed two-scale persistence; its strength is kept so
    the matching stage can distinguish strong structural peaks from weak ones, and
    the smoothed per-pixel energy profile is kept so unmatched peaks can be
    cross-checked against the other image's edge evidence.
    """
    dim = len(profile)
    if dim < 5 or perp <= 0:
        return [], [], None
    span = float(profile.max() - profile.min())
    if span <= 0:
        return [], [], None
    fine = _smooth(profile, round(_FINE_SCALE * dim))
    coarse = _smooth(profile, round(_COARSE_SCALE * dim), passes=2)
    tol = max(round(_COARSE_SCALE * dim), round(0.01 * dim), 2)
    coarse_floor = _MIN_EDGE_STRENGTH * _COARSE_PERSIST_FACTOR
    edge = round(_EDGE_MARGIN * dim)
    peaks: list[tuple[float, float]] = []
    for i in _local_maxima(fine):
        if i < edge or i > dim - 1 - edge:
            continue
        raw = _prominence(fine, i)
        strength = raw / perp
        if strength < _MIN_EDGE_STRENGTH:  # absolute contrast gate (flat/grain)
            continue
        if raw / span < config.min_peak_prominence:  # relative shape gate
            continue
        # Two-scale persistence: the coarse-smoothed profile must still carry a
        # real energy bump at this location. Grain spikes vanish under coarse
        # smoothing; genuine frame/panel edges persist.
        if _windowed_range(coarse, i, tol) / perp < coarse_floor:
            continue
        peaks.append((_refine(fine, i) / (dim - 1), strength))
    peaks.sort()
    positions, strengths = _dedupe(peaks, min_gap=2.0 / dim)
    return positions, strengths, fine / perp


def _dedupe(
    peaks: list[tuple[float, float]], min_gap: float
) -> tuple[list[float], list[float]]:
    positions: list[float] = []
    strengths: list[float] = []
    for pos, strength in peaks:
        if not positions or pos - positions[-1] >= min_gap:
            positions.append(pos)
            strengths.append(strength)
        elif strength > strengths[-1]:  # keep the stronger of near-duplicates
            positions[-1], strengths[-1] = pos, strength
    return positions, strengths


# --- DP boundary matching ----------------------------------------------------


def _match_indices(
    ref: list[float], cand: list[float], gap: float
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Order-preserving (monotonic) DP alignment.

    Returns (matched index pairs, unmatched ref indices, unmatched cand indices).
    Unmatched peaks are penalized by `gap` and reported separately, never folded
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
    pairs: list[tuple[int, int]] = []
    un_ref: list[int] = []
    un_cand: list[int] = []
    while i > 0 and j > 0:
        match = dp[i - 1][j - 1] + abs(ref[i - 1] - cand[j - 1])
        if dp[i][j] == match:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i][j] == dp[i - 1][j] + gap:
            un_ref.append(i - 1)
            i -= 1
        else:
            un_cand.append(j - 1)
            j -= 1
    un_ref.extend(range(i - 1, -1, -1))
    un_cand.extend(range(j - 1, -1, -1))
    pairs.reverse()
    un_ref.reverse()
    un_cand.reverse()
    return pairs, un_ref, un_cand


def _match_boundaries(
    ref: list[float], cand: list[float], gap: float
) -> tuple[list[float], int]:
    """Positions-only view of `_match_indices`: (matched deltas, raw unmatched)."""
    pairs, un_ref, un_cand = _match_indices(ref, cand, gap)
    deltas = [abs(ref[i] - cand[j]) for i, j in pairs]
    return deltas, len(un_ref) + len(un_cand)


# --- per-image measurement ---------------------------------------------------


def _measure_image(path: Path, config: GeometryConfig) -> ImageMeasurement:
    img = _load_gray(path, config.working_width)
    box = _detect_box(img, config)
    if not box.ok:
        return ImageMeasurement(False, box.reason, 0.0, 0.0, [], [])
    crop = img[box.top : box.bottom + 1, box.left : box.right + 1]
    box_w, box_h = crop.shape[1], crop.shape[0]
    aspect = box_w / box_h
    fraction = (box_w * box_h) / (img.shape[0] * img.shape[1])
    gx = _conv3(crop, _SOBEL_X)
    gy = _conv3(crop, _SOBEL_Y)
    v_profile = np.abs(gx).sum(axis=0)  # over rows -> vertical edges along x
    h_profile = np.abs(gy).sum(axis=1)  # over columns -> horizontal edges along y
    v_boundaries, v_strengths, v_energy = _boundaries(v_profile, box_h, config)
    h_boundaries, h_strengths, h_energy = _boundaries(h_profile, box_w, config)
    return ImageMeasurement(
        True, "", aspect, fraction,
        v_boundaries, h_boundaries, v_strengths, h_strengths,
        box.forced_low, box.full_bleed, v_energy, h_energy,
    )


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

    v_pairs, v_un_ref, v_un_cand = _match_indices(
        ref.v_boundaries, cand.v_boundaries, _MATCH_GAP
    )
    h_pairs, h_un_ref, h_un_cand = _match_indices(
        ref.h_boundaries, cand.h_boundaries, _MATCH_GAP
    )
    v_deltas = [abs(ref.v_boundaries[i] - cand.v_boundaries[j]) for i, j in v_pairs]
    h_deltas = [abs(ref.h_boundaries[i] - cand.h_boundaries[j]) for i, j in h_pairs]
    boundary_deltas = v_deltas + h_deltas

    # Strong-peak floor: an unmatched peak counts as a structural mismatch only
    # if it is comparable in strength to the matched structure of its own image
    # AND the other image shows no comparable edge energy at that position.
    ref_matched = [ref.v_strengths[i] for i, _ in v_pairs] + [
        ref.h_strengths[i] for i, _ in h_pairs
    ]
    cand_matched = [cand.v_strengths[j] for _, j in v_pairs] + [
        cand.h_strengths[j] for _, j in h_pairs
    ]
    unmatched_ref = _strong_unmatched(
        v_un_ref, ref.v_boundaries, ref.v_strengths, ref_matched, cand.v_energy
    ) + _strong_unmatched(
        h_un_ref, ref.h_boundaries, ref.h_strengths, ref_matched, cand.h_energy
    )
    unmatched_cand = _strong_unmatched(
        v_un_cand, cand.v_boundaries, cand.v_strengths, cand_matched, ref.v_energy
    ) + _strong_unmatched(
        h_un_cand, cand.h_boundaries, cand.h_strengths, cand_matched, ref.h_energy
    )
    unmatched = unmatched_ref + unmatched_cand

    stile_deltas = _edge_deltas(ref.v_boundaries, cand.v_boundaries, v_pairs, "left", "right")
    rail_deltas = _edge_deltas(ref.h_boundaries, cand.h_boundaries, h_pairs, "top", "bottom")

    named: dict[str, float] = {}
    named.update({f"stile.{k}": v for k, v in stile_deltas.items()})
    named.update({f"rail.{k}": v for k, v in rail_deltas.items()})
    named.update({f"boundary.{i}": d for i, d in enumerate(boundary_deltas)})
    max_delta = max(named.values(), default=0.0)
    worst_name = max(named, key=lambda k: named[k], default="none")

    partial = not (ref.v_boundaries and cand.v_boundaries) or not (
        ref.h_boundaries and cand.h_boundaries
    )
    # Structural (strong) boundary counts: matched + strong unmatched per image.
    matched_count = len(v_pairs) + len(h_pairs)
    counts_agree = abs((matched_count + unmatched_ref) - (matched_count + unmatched_cand)) <= 1
    mean_residual = float(np.mean(boundary_deltas)) if boundary_deltas else float("inf")
    confidence = (
        "high"
        if (
            not partial
            and counts_agree
            and mean_residual <= config.max_match_residual
            and not ref.forced_low
            and not cand.forced_low
        )
        else "low"
    )

    threshold = config.drift_thresholds.get(
        style_class, config.drift_thresholds.get("frame_standard", 0.02)
    )
    # A full-bleed box is the photo crop, not the door outline: its aspect says
    # nothing about the door's true aspect, so it cannot be drift evidence.
    aspect_comparable = not ref.full_bleed and not cand.full_bleed
    drift = (
        max_delta > threshold
        or (aspect_comparable and aspect_delta > config.aspect_threshold)
        or (unmatched > 0 and confidence == "high")
    )
    status = "drift" if drift else "ok"

    detail = _detail(
        status, worst_name, max_delta, threshold, aspect_delta,
        unmatched, reference, confidence, partial, aspect_comparable,
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


def _strong_unmatched(
    unmatched: list[int],
    positions: list[float],
    strengths: list[float],
    matched_strengths: list[float],
    other_energy: np.ndarray | None,
) -> int:
    """Count unmatched peaks that are genuinely structural mismatches.

    Two gates:
    - strength: weak grain/shadow peaks that survived detection in only one
      image must not count. The floor is relative to the matched structural
      boundaries of the same image (with no matched structure to calibrate
      against, every unmatched peak counts — fail-safe).
    - cross-energy: different wood tones make different subsets of the SAME
      edges detectable. If the other image carries comparable edge energy at
      this position (even sub-detection-threshold), the structure exists in
      both images and the peak is a detection asymmetry, not drift.
    """
    floor = (
        _UNMATCHED_STRENGTH_FACTOR * float(np.median(matched_strengths))
        if matched_strengths
        else 0.0
    )
    count = 0
    for i in unmatched:
        if strengths[i] < floor:
            continue
        if other_energy is not None:
            dim = len(other_energy)
            center = round(positions[i] * (dim - 1))
            local = _windowed_range(other_energy, center, max(2, round(_CROSS_ENERGY_TOL * dim)))
            required = max(
                _MIN_EDGE_STRENGTH, min(_CROSS_ENERGY_FACTOR * strengths[i], _CROSS_ENERGY_CAP)
            )
            if local >= required:
                continue
        count += 1
    return count


def _edge_deltas(
    ref: list[float],
    cand: list[float],
    pairs: list[tuple[int, int]],
    near_key: str,
    far_key: str,
) -> dict[str, float]:
    """Outer-frame width deltas from the outermost MATCHED boundaries on an axis.

    Using matched pairs (not raw first/last peaks) keeps a weak spurious peak
    near an edge from corrupting the stile/rail width measurement.
    """
    if not pairs:
        return {}
    i0, j0 = pairs[0]
    i1, j1 = pairs[-1]
    near = abs(cand[j0] - ref[i0])  # left stile / top rail width
    far = abs((1 - cand[j1]) - (1 - ref[i1]))  # right stile / bottom rail width
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
    aspect_comparable: bool,
) -> str:
    aspect_note = "" if aspect_comparable else " (unverified: full-bleed crop)"
    parts = [
        f"{status}",
        f"worst {worst_name}={max_delta:.3f} (thr {threshold:.3f})",
        f"aspect_delta={aspect_delta:.3f}{aspect_note}",
        f"unmatched={unmatched}",
        f"ref={reference}",
        f"conf={confidence}",
    ]
    if partial:
        parts.append("GEO-003: partial (missing interior boundaries on an axis)")
    return "; ".join(parts)
