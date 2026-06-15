"""Project + experimental-design model.

A **Project** is a dataset of recordings grouped into treatment **conditions**,
plus a **Design** describing the experiment: which conditions form each *arm*,
which is the *control* of each arm, an optional *vehicle* pair, and condition
colours. This decouples the app from the hard-coded IC295 structure so users can
load any dataset (any treatments / recording counts) and compare it correctly.

The design is auto-derived from the discovered conditions (it recognises the
IC295 arms; otherwise it makes one arm with a heuristic control) and can be
saved / loaded as a small JSON file. GUI-free.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .io.dataset import discover
from .analysis import feature_tables

_CONTROL_HINTS = ("wt", "control", "ctrl", "dmso", "vehicle", "veh",
                  "untreated", "none", "wildtype", "ctl")
_IC295_GENETIC = ["WT", "GOF", "KO"]
_IC295_DRUG = ["DMSO", "Y1", "OT"]
_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#7f7f7f",
            "#17becf", "#bcbd22", "#8c564b", "#e377c2"]


@dataclass
class Design:
    arms: dict                                   # {arm: {control, conditions[]}}
    vehicle: list | None = None                  # [condA, condB]
    colors: dict = field(default_factory=dict)   # condition -> hex

    def condition_order(self):
        order = []
        for spec in self.arms.values():
            for c in spec.get("conditions", []):
                if c not in order:
                    order.append(c)
        return order

    def color(self, cond):
        return self.colors.get(cond, "#777777")

    def to_dict(self):
        return {"arms": self.arms, "vehicle": self.vehicle, "colors": self.colors}


@dataclass
class Project:
    name: str
    data_roots: list
    entries: list
    design: Design
    path: str | None = None
    excluded: set = field(default_factory=set)    # recording labels dropped from compare
    overrides: dict = field(default_factory=dict)  # recording label -> group (condition)
    corrections: dict = field(default_factory=dict)  # label -> {shifts, fov} (pre-analysis)
    px_size: float | None = None         # manual µm/px override (all recordings)
    frame_interval: float | None = None  # manual min/frame override (all recordings)

    def group_of(self, entry):
        """The comparison group of a recording (override wins over its folder)."""
        return self.overrides.get(entry.label, entry.condition or "?")

    def correction_for(self, label):
        """Pre-analysis correction (channel shifts + FOV) for a recording, or {}."""
        return self.corrections.get(label, {})

    def scaled(self, rec):
        """Apply the project-wide manual pixel-size / time-interval overrides to a
        loaded recording — used when a file's metadata is missing or wrong. Applies
        to **every** recording in the project; unset (None / 0) keeps file values."""
        if self.px_size:
            rec.um_per_px = float(self.px_size)
        if self.frame_interval:
            rec.time_interval_min = float(self.frame_interval)
        return rec

    @property
    def scale_override(self):
        """``(px_size, frame_interval)`` for passing into `build_comparison`."""
        return (self.px_size, self.frame_interval)

    def included_entries(self):
        return [e for e in self.entries if e.label not in self.excluded]

    @property
    def conditions(self):
        """Groups present across included recordings (override-aware), in design order."""
        seen = []
        for e in self.included_entries():
            g = self.group_of(e)
            if g not in seen:
                seen.append(g)
        order = self.design.condition_order()
        return [c for c in order if c in seen] + [c for c in seen if c not in order]

    @property
    def all_groups(self):
        """Every group name the user can assign to (originals ∪ overrides ∪ design)."""
        seen = []
        for e in self.entries:
            for g in (e.condition or "?", self.overrides.get(e.label)):
                if g and g not in seen:
                    seen.append(g)
        for c in self.design.condition_order():
            if c not in seen:
                seen.append(c)
        return seen

    @property
    def n_recordings(self):
        return len(self.included_entries())

    def regroup(self, df):
        """Drop excluded recordings + apply group overrides to a per-cell / MSD
        frame (needs ``recording`` + ``condition`` columns). Lets grouping change
        without recomputing the (expensive) per-cell metrics."""
        if df is None or getattr(df, "empty", True):
            return df
        out = df[~df["recording"].isin(self.excluded)].copy()
        if self.overrides:
            out["condition"] = out["recording"].map(self.overrides).fillna(out["condition"])
        return out


# ----------------------------------------------------------- design helpers
def _guess_control(conds):
    for hint in _CONTROL_HINTS:
        for c in conds:
            if c.lower() == hint:
                return c
    for hint in _CONTROL_HINTS:
        for c in conds:
            if hint in c.lower():
                return c
    return conds[0] if conds else None


def _palette(conds):
    known = feature_tables.COND_COLOR
    out, pi = {}, 0
    for c in conds:
        if c in known:
            out[c] = known[c]
        else:
            out[c] = _PALETTE[pi % len(_PALETTE)]
            pi += 1
    return out


def ensure_colors(design, groups):
    """Give every group a colour (keep existing; assign new ones from the palette)."""
    used = set(design.colors.values())
    pi = 0
    for g in groups:
        if g in design.colors:
            continue
        if g in feature_tables.COND_COLOR:
            design.colors[g] = feature_tables.COND_COLOR[g]
        else:
            while _PALETTE[pi % len(_PALETTE)] in used and pi < len(_PALETTE):
                pi += 1
            design.colors[g] = _PALETTE[pi % len(_PALETTE)]
            used.add(design.colors[g])
            pi += 1
    return design.colors


def auto_design(conditions):
    """Derive a Design from the conditions present (IC295-aware, else generic)."""
    conds = [c for c in conditions if c]
    if not conds:
        return Design({}, None, {})
    gen = [c for c in _IC295_GENETIC if c in conds]
    drg = [c for c in _IC295_DRUG if c in conds]
    if (len(gen) >= 2 and "WT" in gen) or (len(drg) >= 2 and "DMSO" in drg):
        arms = {}
        if len(gen) >= 2 and "WT" in gen:
            arms["genetic"] = {"control": "WT", "conditions": gen}
        if len(drg) >= 2 and "DMSO" in drg:
            arms["drug"] = {"control": "DMSO", "conditions": drg}
        leftover = [c for c in conds if c not in gen + drg]
        if leftover and len(leftover) >= 2:
            arms["other"] = {"control": _guess_control(leftover), "conditions": leftover}
        veh = ["WT", "DMSO"] if ("WT" in conds and "DMSO" in conds) else None
        return Design(arms, veh, _palette(conds))
    ctrl = _guess_control(conds)
    return Design({"comparison": {"control": ctrl, "conditions": conds}}, None,
                  _palette(conds))


# ------------------------------------------------------------- constructors
def _conditions_of(entries):
    conds = []
    for e in entries:
        c = e.condition or "?"
        if c not in conds:
            conds.append(c)
    return conds


def from_entries(entries, name="current", data_roots=None):
    entries = list(entries)
    return Project(name, data_roots or [], entries,
                   auto_design(_conditions_of(entries)))


def from_data_roots(roots, name=None):
    roots = [roots] if isinstance(roots, (str, bytes, os.PathLike)) else list(roots)
    entries = discover(roots)
    nm = name or (os.path.basename(os.path.normpath(roots[0])) if roots else "project")
    return from_entries(entries, name=nm, data_roots=roots)


def load_project(path):
    """Load a project JSON ({name, data_roots, arms?, vehicle?, colors?})."""
    with open(path) as f:
        blob = json.load(f)
    roots = blob.get("data_roots", [])
    entries = discover(roots)
    arms = blob.get("arms")
    if arms:
        design = Design(arms, blob.get("vehicle"),
                        blob.get("colors") or _palette(
                            Design(arms).condition_order()))
    else:
        design = auto_design(_conditions_of(entries))
    name = blob.get("name") or os.path.splitext(os.path.basename(path))[0]
    return Project(name, roots, entries, design, path=path,
                   excluded=set(blob.get("excluded", [])),
                   overrides=dict(blob.get("overrides", {})),
                   corrections=dict(blob.get("corrections", {})),
                   px_size=blob.get("px_size"),
                   frame_interval=blob.get("frame_interval"))


def save_project(project, path):
    blob = {"name": project.name, "data_roots": project.data_roots,
            "arms": project.design.arms, "vehicle": project.design.vehicle,
            "colors": project.design.colors,
            "excluded": sorted(project.excluded), "overrides": project.overrides,
            "corrections": project.corrections, "px_size": project.px_size,
            "frame_interval": project.frame_interval}
    with open(path, "w") as f:
        json.dump(blob, f, indent=2)
    project.path = path
    return path
