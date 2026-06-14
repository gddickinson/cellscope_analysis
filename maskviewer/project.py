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

    @property
    def conditions(self):
        seen = []
        for e in self.entries:
            c = e.condition or "?"
            if c not in seen:
                seen.append(c)
        order = self.design.condition_order()
        return [c for c in order if c in seen] + [c for c in seen if c not in order]

    @property
    def n_recordings(self):
        return len(self.entries)


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
    return Project(name, roots, entries, design, path=path)


def save_project(project, path):
    blob = {"name": project.name, "data_roots": project.data_roots,
            "arms": project.design.arms, "vehicle": project.design.vehicle,
            "colors": project.design.colors}
    with open(path, "w") as f:
        json.dump(blob, f, indent=2)
    project.path = path
    return path
