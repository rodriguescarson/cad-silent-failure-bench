"""Auto-grader: evaluate a task's checks against a measured-properties dict.

Pure standard library — no CAD kernel. The executor (build123d) is responsible for producing the
`props` dict; this module only does arithmetic on it, so it is fully unit-testable offline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .schema import Check, Task


@dataclass
class CheckResult:
    id: str
    passed: bool
    value: float | bool | None
    reason: str
    weight: float = 1.0


@dataclass
class GradeResult:
    task_id: str
    passed: bool                 # all checks pass
    score: float                 # weighted fraction of checks passed
    valid_solid: bool            # did we even get a renderable solid?
    checks: list[CheckResult]

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def _scalar(props: dict, name: str) -> float:
    bbox = props.get("bbox") or [0.0, 0.0, 0.0]
    dx, dy, dz = (list(bbox) + [0.0, 0.0, 0.0])[:3]
    com = props.get("com") or [0.0, 0.0, 0.0]
    bc = props.get("bbox_center") or [0.0, 0.0, 0.0]
    table = {
        "bbox_x": dx, "bbox_y": dy, "bbox_z": dz,
        "bbox_xy_max": max(dx, dy), "bbox_xy_min": min(dx, dy),
        "volume": float(props.get("volume", 0.0)),
        "solid_count": float(props.get("solid_count", 0)),
        "face_count": float(props.get("face_count", 0)),
        "edge_count": float(props.get("edge_count", 0)),
        "com_x": com[0], "com_y": com[1], "com_z": com[2],
        # mass-centre offset from bbox centre: translation-invariant, mirror/feature-placement
        # sensitive — usable as a check without pinning where the agent placed the part
        "com_off_x": com[0] - bc[0], "com_off_y": com[1] - bc[1], "com_off_z": com[2] - bc[2],
    }
    return float(table[name])


def _matching_cylinders(props: dict, radius: float, radius_tol: float,
                        height: float | None = None, height_tol: float = 1.0) -> list[dict]:
    """Cylindrical features matching a radius (and, when given, an axial extent). The height
    filter is what catches blind holes sold as through-holes and transposed section lengths."""
    out = []
    for c in props.get("cylinders", []):
        if abs(float(c.get("radius", -1)) - radius) > radius_tol:
            continue
        if height is not None and abs(float(c.get("height", -1)) - height) > height_tol:
            continue
        out.append(c)
    return out


def _eval_check(check: Check, props: dict) -> CheckResult:
    k = check.kind
    try:
        if k == "approx":
            v = _scalar(props, check.property)  # type: ignore[arg-type]
            ok = abs(v - check.target) <= check.tol  # type: ignore[operator]
            return CheckResult(check.id, ok, v,
                               f"{check.property}={v:.3f} vs {check.target}±{check.tol}", check.weight)
        if k == "range":
            v = _scalar(props, check.property)  # type: ignore[arg-type]
            ok = check.lo <= v <= check.hi      # type: ignore[operator]
            return CheckResult(check.id, ok, v,
                               f"{check.property}={v:.3f} in [{check.lo},{check.hi}]", check.weight)
        if k == "equal":
            v = _scalar(props, check.property)  # type: ignore[arg-type]
            ok = math.isclose(v, check.target, rel_tol=0, abs_tol=1e-6)
            return CheckResult(check.id, ok, v, f"{check.property}={v} vs {check.target}", check.weight)
        if k in {"true", "false"}:
            v = bool(props.get(check.property, False))
            ok = v if k == "true" else (not v)
            return CheckResult(check.id, ok, v, f"{check.property}={v}", check.weight)
        if k == "cylinder_count":
            n = len(_matching_cylinders(props, check.radius, check.radius_tol or 0.5,  # type: ignore[arg-type]
                                        check.height, check.height_tol or 1.0))
            ok = n == check.target
            h = f" h≈{check.height}±{check.height_tol}" if check.height is not None else ""
            return CheckResult(check.id, ok, n,
                               f"{n} cyl r≈{check.radius}±{check.radius_tol}{h} vs {check.target}",
                               check.weight)
        if k == "bolt_circle":
            cyls = _matching_cylinders(props, check.radius, check.radius_tol or 0.5,  # type: ignore[arg-type]
                                       check.height, check.height_tol or 1.0)
            n = len(cyls)
            if n != check.target:
                return CheckResult(check.id, False, n,
                                   f"{n} matching holes vs {check.target}", check.weight)
            # pattern centre must sit on the part's own axis (com), not be self-referential:
            # a translated pattern moves its centroid with it, the part's mass centre far less.
            com = props.get("com") or [0.0, 0.0, 0.0]
            cx = sum(c["center"][0] for c in cyls) / n
            cy = sum(c["center"][1] for c in cyls) / n
            centre_off = math.hypot(cx - com[0], cy - com[1])
            # per-hole radial deviation (NOT the mean — opposite-hole errors must not cancel)
            radii = [math.hypot(c["center"][0] - cx, c["center"][1] - cy) for c in cyls]
            pcd_est = 2.0 * (sum(radii) / n)
            max_dev = max(abs(2.0 * r - check.pcd) for r in radii)  # type: ignore[operator]
            # angular uniformity: max gap between sorted hole angles vs nominal 360/n
            angs = sorted(math.atan2(c["center"][1] - cy, c["center"][0] - cx) for c in cyls)
            gaps = [angs[i + 1] - angs[i] for i in range(n - 1)] + [2 * math.pi - (angs[-1] - angs[0])]
            ang_err = max(abs(math.degrees(g) - 360.0 / n) for g in gaps) if n > 1 else 0.0
            ok = (max_dev <= (check.pcd_tol or 0.5)
                  and centre_off <= (check.center_tol or 1.5)
                  and ang_err <= (check.ang_tol or 10.0))
            return CheckResult(check.id, ok, round(pcd_est, 3),
                               f"{n} holes, PCD≈{pcd_est:.2f} vs {check.pcd} (max dev {max_dev:.2f}"
                               f"≤{check.pcd_tol}), centre off {centre_off:.2f}≤{check.center_tol or 1.5},"
                               f" ang err {ang_err:.1f}°≤{check.ang_tol or 10}", check.weight)
    except Exception as e:  # missing/garbage props
        return CheckResult(check.id, False, None, f"eval error: {e}", check.weight)
    return CheckResult(check.id, False, None, f"unhandled kind {k}", check.weight)


def grade(task: Task, props: dict | None) -> GradeResult:
    valid = bool(props and props.get("valid_solid", False))
    if not props:
        checks = [CheckResult(c.id, False, None, "no properties (execution failed)", c.weight)
                  for c in task.checks]
        return GradeResult(task.id, False, 0.0, False, checks)
    results = [_eval_check(c, props) for c in task.checks]
    total_w = sum(c.weight for c in results) or 1.0
    score = sum(c.weight for c in results if c.passed) / total_w
    return GradeResult(task.id, all(c.passed for c in results), score, valid, results)
