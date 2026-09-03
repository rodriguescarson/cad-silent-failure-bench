"""Task + check definitions and (de)serialization.

A task is a natural-language CAD spec plus a list of *machine-checkable* requirements. Each check
names a `kind` the grader knows how to evaluate against the measured-properties dict produced by the
executor. Keeping checks declarative (JSON) means tasks are data, not code, and the suite is auditable.

Property vocabulary the grader/executor agree on (task units, default mm):
    valid_solid : bool      watertight : bool        solid_count : int
    face_count  : int       edge_count : int         volume : float (mm^3)
    bbox        : [dx,dy,dz] (axis-aligned extents)   com : [x,y,z]
    cylinders   : [{radius, height, axis:[x,y,z], center:[x,y,z]}]  (best-effort hole/round detection)

Derived scalar accessors usable by approx/range/equal checks via `property`:
    bbox_x bbox_y bbox_z bbox_xy_max bbox_xy_min volume solid_count face_count edge_count
    com_x com_y com_z
Boolean accessors usable by true/false checks: valid_solid watertight
Specialized checks: cylinder_count, bolt_circle (operate on the `cylinders` list).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

CHECK_KINDS = {"approx", "equal", "range", "true", "false", "cylinder_count", "bolt_circle"}

SCALAR_PROPERTIES = {
    "bbox_x", "bbox_y", "bbox_z", "bbox_xy_max", "bbox_xy_min",
    "volume", "solid_count", "face_count", "edge_count",
    "com_x", "com_y", "com_z",
    "com_off_x", "com_off_y", "com_off_z",  # mass centre minus bbox centre (translation-invariant)
}
BOOL_PROPERTIES = {"valid_solid", "watertight"}


@dataclass
class Check:
    id: str
    kind: str
    desc: str = ""
    # approx/range/equal:
    property: str | None = None
    target: float | None = None
    tol: float | None = None
    lo: float | None = None
    hi: float | None = None
    # cylinder_count / bolt_circle:
    radius: float | None = None
    radius_tol: float | None = 0.5
    height: float | None = None        # axial extent filter (catches blind/short features)
    height_tol: float | None = 1.0
    pcd: float | None = None
    pcd_tol: float | None = 0.5        # bolt_circle: max PER-HOLE radial deviation (x2)
    center_tol: float | None = 1.5     # bolt_circle: pattern centroid vs part com (XY)
    ang_tol: float | None = 10.0       # bolt_circle: max angular-spacing error, degrees
    weight: float = 1.0

    def validate(self) -> None:
        if self.kind not in CHECK_KINDS:
            raise ValueError(f"check {self.id}: unknown kind {self.kind!r}")
        if self.kind in {"approx"}:
            _require(self, "property", "target", "tol")
            _scalar(self.property, self.id)
        elif self.kind == "range":
            _require(self, "property", "lo", "hi")
            _scalar(self.property, self.id)
        elif self.kind == "equal":
            _require(self, "property", "target")
            _scalar(self.property, self.id)
        elif self.kind in {"true", "false"}:
            _require(self, "property")
            if self.property not in BOOL_PROPERTIES:
                raise ValueError(f"check {self.id}: {self.property!r} is not a boolean property")
        elif self.kind == "cylinder_count":
            _require(self, "radius", "target")
        elif self.kind == "bolt_circle":
            _require(self, "radius", "pcd", "target")


@dataclass
class Task:
    id: str
    tier: int
    title: str
    nl_spec: str
    checks: list[Check]
    units: str = "mm"
    density: float | None = None           # kg/m^3, if a mass check is used later
    reference_solution: str | None = None  # path to build123d code; never shown to the agent
    tags: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.checks:
            raise ValueError(f"task {self.id}: no checks")
        seen = set()
        for c in self.checks:
            if c.id in seen:
                raise ValueError(f"task {self.id}: duplicate check id {c.id!r}")
            seen.add(c.id)
            c.validate()


def _require(obj: Any, *fields: str) -> None:
    for f in fields:
        if getattr(obj, f) is None:
            raise ValueError(f"check {getattr(obj, 'id', '?')}: {f!r} is required for kind {obj.kind!r}")


def _scalar(prop: str | None, cid: str) -> None:
    if prop not in SCALAR_PROPERTIES:
        raise ValueError(f"check {cid}: {prop!r} is not a known scalar property {sorted(SCALAR_PROPERTIES)}")


def task_from_dict(d: dict) -> Task:
    checks = [Check(**c) for c in d.get("checks", [])]
    task = Task(
        id=d["id"], tier=int(d["tier"]), title=d["title"], nl_spec=d["nl_spec"],
        checks=checks, units=d.get("units", "mm"), density=d.get("density"),
        reference_solution=d.get("reference_solution"), tags=list(d.get("tags", [])),
    )
    task.validate()
    return task


def load_task(path: str | Path) -> Task:
    return task_from_dict(json.loads(Path(path).read_text()))


def load_suite(dir_path: str | Path) -> list[Task]:
    d = Path(dir_path)
    tasks = [load_task(p) for p in sorted(d.glob("*.json"))]
    ids = [t.id for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task ids in suite")
    return tasks


def task_to_dict(task: Task) -> dict:
    out = asdict(task)
    out["checks"] = [{k: v for k, v in c.items() if v is not None} for c in out["checks"]]
    return out
