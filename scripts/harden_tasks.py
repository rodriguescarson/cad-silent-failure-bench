"""One-shot oracle hardening of the v1 task suite (2026-06-10 review round).

Applies to every tasks/*.json:
  - height filters on cylinder_count / bolt_circle checks (blind holes, transposed sections,
    wrong counterbore depth no longer pass)
  - tightened bolt_circle (per-hole radial deviation + centre-vs-com + angular uniformity
    are grader-side; here we set the tolerances)
  - solid_count == 1 check (stray un-subtracted tool bodies)
  - translation-invariant mass-centre checks (com_off_*) where informative (mirrored or
    wrong-face features)
  - volume bands tightened to ~±8% of the reference solution's measured volume
  - the tautological `watertight` check removed (it duplicated valid_solid)

Run once:  .venv/bin/python scripts/harden_tasks.py   (idempotent)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# task -> {check_id: height}  (axial extents measured from reference solutions)
HEIGHTS = {
    "T1-washer": {"bore": 3},
    "T1-bushing": {"bore": 40, "outer": 40},
    "T1-plate-4holes": {"holes": 8},
    "T1-collar": {"bore": 15},
    "T1-flange-6bolt": {"bore": 14, "bolts": 14},
    "T2-stepped-shaft": {"central": 80, "seats": 20},
    "T2-flanged-bushing": {"bore": 30, "hub": 24, "flange_rim": 6},
    "T2-counterbore-plate": {"cbore": 6, "through": 6},
    "T2-stepped-pin": {"step1": 20, "step2": 25, "step3": 15},
    "T2-pulley-blank": {"bore": 36, "hub": 20, "disc_rim": 16},
    "T2-lbracket": {"holes": 8},
    "T4-flange-8bolt-edit": {"bore": 14, "bolts": 14},
    "T4-bushing-bore-edit": {"new_bore": 40},
}

# task -> nominal reference volume (measured); band = ±8% rounded to 3 significant-ish figures
NOMINAL_VOL = {
    "T1-washer": 2731, "T1-bushing": 15708, "T1-plate-4holes": 49164, "T1-collar": 16493,
    "T1-flange-6bolt": 132761, "T2-stepped-shaft": 128805, "T2-flanged-bushing": 24504,
    "T2-counterbore-plate": 56345, "T2-stepped-pin": 4979, "T2-pulley-blank": 89271,
    "T2-lbracket": 33756, "T4-flange-8bolt-edit": 130100,
    # T4-bushing-bore-edit's volume check IS the spec's global cap — leave its band alone.
}

# task -> extra checks appended (translation-invariant com offsets; solid_count everywhere)
EXTRA = {
    "T2-counterbore-plate": [
        {"id": "cbore_face", "kind": "approx", "property": "com_off_z", "target": -0.07,
         "tol": 0.1, "desc": "counterbore from the TOP face (mass centre sits low)"},
    ],
    "T2-lbracket": [
        {"id": "com_y", "kind": "approx", "property": "com_off_y", "target": -7.19, "tol": 1.0,
         "desc": "wall on the y=0 side (catches mirrored bracket)"},
        {"id": "com_z", "kind": "approx", "property": "com_off_z", "target": -7.14, "tol": 1.0,
         "desc": "base at the bottom"},
    ],
    "T2-flanged-bushing": [
        {"id": "flange_low", "kind": "approx", "property": "com_off_z", "target": -6.23,
         "tol": 1.0, "desc": "flange at the base, hub above"},
    ],
    "T2-pulley-blank": [
        {"id": "disc_low", "kind": "approx", "property": "com_off_z", "target": -7.57,
         "tol": 1.2, "desc": "disc at the base, hub above"},
    ],
}

AXISYM = {  # axisymmetric parts: mass centre on the bbox axis in XY
    "T1-washer", "T1-bushing", "T1-collar", "T1-flange-6bolt", "T2-stepped-shaft",
    "T2-flanged-bushing", "T2-stepped-pin", "T2-pulley-blank", "T1-plate-4holes",
    "T2-counterbore-plate", "T4-flange-8bolt-edit", "T4-bushing-bore-edit",
}

BOLT_TOL = {  # task -> (pcd_tol per-hole, center_tol, ang_tol)
    "T1-flange-6bolt": (1.0, 1.5, 8.0),
    "T1-plate-4holes": (1.0, 1.5, 8.0),
    "T4-flange-8bolt-edit": (1.0, 1.5, 8.0),
}


def main() -> int:
    for path in sorted((ROOT / "tasks").glob("*.json")):
        t = json.loads(path.read_text())
        tid = t["id"]
        checks = [c for c in t["checks"] if c["id"] != "watertight"]
        for c in checks:
            h = HEIGHTS.get(tid, {}).get(c["id"])
            if h is not None and c["kind"] in {"cylinder_count", "bolt_circle"}:
                c["height"] = h
                c["height_tol"] = 1.0
            if c["kind"] == "bolt_circle" and tid in BOLT_TOL:
                c["pcd_tol"], c["center_tol"], c["ang_tol"] = BOLT_TOL[tid]
            if c["id"] == "volume" and tid in NOMINAL_VOL:
                v = NOMINAL_VOL[tid]
                c["lo"], c["hi"] = round(v * 0.92), round(v * 1.08)
                c["desc"] = f"volume within ±8% of nominal {v} mm^3"
        ids = {c["id"] for c in checks}
        if "one_solid" not in ids:
            checks.append({"id": "one_solid", "kind": "equal", "property": "solid_count",
                           "target": 1, "desc": "exactly one solid body"})
        if tid in AXISYM and "centered" not in ids:
            checks.append({"id": "centered", "kind": "approx", "property": "com_off_x",
                           "target": 0, "tol": 0.5, "desc": "mass centre on the part axis (x)"})
            checks.append({"id": "centered_y", "kind": "approx", "property": "com_off_y",
                           "target": 0, "tol": 0.5, "desc": "mass centre on the part axis (y)"})
        for extra in EXTRA.get(tid, []):
            if extra["id"] not in ids:
                checks.append(extra)
        t["checks"] = checks
        path.write_text(json.dumps(t, indent=2) + "\n")
        print(f"hardened {tid}: {len(checks)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
