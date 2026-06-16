"""Per-frame cell-state classification (rounded vs spread), GUI-free.

Replicates the CellScope IC295 rule so values stay comparable to the existing
findings (docs/FINDINGS_followup.md). An edge-truncated cell-frame is ``edge``
(shape unreliable → excluded from per-state stats but still counted/tracked).
Otherwise, when the pixel scale is known, a cell is ``rounded`` iff its
footprint is small **and** not elongated (area ≤ 960 µm² and eccentricity
≤ 0.85), else ``spread`` — size/footprint-collapse beats circularity here.
Without scale a circularity/solidity fallback is used; tiny/undefined regions
are ``unknown``. Thresholds are module constants (tunable).
"""
from __future__ import annotations

ROUNDED_AREA_UM2 = 960.0
ROUNDED_ECC = 0.85
FALLBACK_CIRCULARITY = 0.80
FALLBACK_SOLIDITY = 0.92
MIN_AREA_PX = 200

STATES = ("unknown", "spread", "rounded", "edge")
STATE_CODE = {"unknown": 0, "spread": 1, "rounded": 2, "edge": 3}
STATE_COLOR = {"unknown": (130, 130, 130), "spread": (44, 160, 44),
               "rounded": (214, 39, 40), "edge": (255, 165, 0)}


def classify_state(area_px, area_um2=None, eccentricity=None, circularity=None,
                   solidity=None, edge=False, min_area_px=None) -> str:
    """Return one of 'rounded' / 'spread' / 'edge' / 'unknown' for one cell-frame.
    ``min_area_px=None`` reads the (configurable) module-level ``MIN_AREA_PX``."""
    min_area_px = MIN_AREA_PX if min_area_px is None else min_area_px
    if edge:
        return "edge"
    if area_px is None or area_px < min_area_px or eccentricity is None:
        return "unknown"
    if area_um2 is not None:
        return "rounded" if (area_um2 <= ROUNDED_AREA_UM2
                             and eccentricity <= ROUNDED_ECC) else "spread"
    if circularity is not None and solidity is not None:
        return "rounded" if (circularity >= FALLBACK_CIRCULARITY
                             and solidity >= FALLBACK_SOLIDITY) else "spread"
    return "unknown"
