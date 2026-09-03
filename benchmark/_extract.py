"""Subprocess entry point: exec agent CAD code, measure geometric properties, print JSON.

Run as:  python -m benchmark._extract <code_file.py> [stl_out.stl]

If a second argument is given, the solid is additionally exported as an STL (best-effort; used by
scripts/build_site.py for the 3D results viewer — never affects grading).

The agent code must assign a build123d solid (or anything exposing `.wrapped` TopoDS_Shape, or a
build123d Part/Compound) to a module-level name `result`. We compute kernel-truth properties and
emit a single JSON line on stdout. Any failure is reported as {"error": ...} (never raises to caller).

This is the ONLY module that depends on build123d / OpenCascade; it is isolated in a subprocess so a
kernel crash cannot take down the runner.
"""

from __future__ import annotations

import json
import math
import sys


def _emit(obj: dict) -> None:
    print(json.dumps(obj))


def main() -> None:
    if len(sys.argv) < 2:
        _emit({"error": "usage: _extract <code_file>"})
        return
    code = open(sys.argv[1]).read()

    try:
        from build123d import Solid, Compound, Part  # noqa: F401
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
        from OCP.BRep import BRep_Tool
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.GeomAdaptor import GeomAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder
        from OCP.TopoDS import TopoDS
    except Exception as e:  # build123d / OCP not installed
        _emit({"error": f"build123d/OCP import failed: {e}"})
        return

    ns: dict = {}
    try:
        exec(compile(code, "<agent_code>", "exec"), ns, ns)
    except Exception as e:
        _emit({"error": f"agent code raised: {type(e).__name__}: {e}"})
        return

    result = ns.get("result")
    if result is None:
        _emit({"error": "agent code did not assign a non-None `result`"})
        return

    # Coerce common agent return shapes (lenient on wrapper, strict on geometry):
    # a builder object (BuildPart) -> its .part; a list/tuple of solids -> one Compound.
    if hasattr(result, "part") and not hasattr(result, "wrapped"):
        result = result.part
    if isinstance(result, (list, tuple)):
        if not result:
            _emit({"error": "`result` is an empty list"})
            return
        result = Compound(children=list(result))
    shape = getattr(result, "wrapped", result)
    from OCP.TopoDS import TopoDS_Shape
    if not isinstance(shape, TopoDS_Shape):
        _emit({"error": f"`result` is not a CAD shape (got {type(result).__name__})"})
        return

    try:
        analyzer = BRepCheck_Analyzer(shape)
        valid_solid = bool(analyzer.IsValid())

        vol_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, vol_props)
        volume = vol_props.Mass()
        com = vol_props.CentreOfMass()

        def _count(kind) -> int:
            exp = TopExp_Explorer(shape, kind)
            n = 0
            while exp.More():
                n += 1
                exp.Next()
            return n

        face_count = _count(TopAbs_FACE)
        edge_count = _count(TopAbs_EDGE)
        solid_count = _count(TopAbs_SOLID)

        # Axis-aligned bounding box via OCP Bnd_Box
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        bbox = [xmax - xmin, ymax - ymin, zmax - zmin]
        bbox_center = [(xmin + xmax) / 2, (ymin + ymax) / 2, (zmin + zmax) / 2]

        # Best-effort cylindrical-face detection (holes / rounds).
        # Faces are grouped by their infinite cylinder (radius + axis line), then merged by axial
        # extent: overlapping spans are one physical cylinder (e.g. a hole split into seam halves
        # by a boolean), disjoint spans are separate features (e.g. two coaxial bearing seats).
        from OCP.BRepTools import BRepTools

        groups: dict = {}  # (r, axis dir, axis foot) -> {"spans": [(lo, hi)], ...}
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            surf = BRep_Tool.Surface_s(face)
            ad = GeomAdaptor_Surface(surf)
            if ad.GetType() == GeomAbs_Cylinder:
                cyl = ad.Cylinder()
                r = cyl.Radius()
                ax = cyl.Axis()
                loc = ax.Location()
                d = ax.Direction()
                dx, dy, dz = d.X(), d.Y(), d.Z()
                flip = (dz, dy, dx) < (0.0, 0.0, 0.0)  # canonical axis sign
                if flip:
                    dx, dy, dz = -dx, -dy, -dz
                t0 = loc.X() * d.X() + loc.Y() * d.Y() + loc.Z() * d.Z()
                foot = (loc.X() - t0 * d.X(), loc.Y() - t0 * d.Y(), loc.Z() - t0 * d.Z())
                _, _, vmin, vmax = BRepTools.UVBounds_s(face)  # v runs along the axis
                lo, hi = t0 + vmin, t0 + vmax
                if flip:
                    lo, hi = -hi, -lo
                key = (round(r, 3), round(dx, 3), round(dy, 3), round(dz, 3),
                       round(foot[0], 2), round(foot[1], 2), round(foot[2], 2))
                g = groups.setdefault(key, {"radius": r, "dir": (dx, dy, dz), "foot": foot,
                                            "spans": []})
                g["spans"].append((lo, hi))
            exp.Next()

        cylinders = []
        for g in groups.values():
            spans = sorted(g["spans"])
            merged = [list(spans[0])]
            for lo, hi in spans[1:]:
                if lo <= merged[-1][1] + 1e-3:  # overlap or touch -> same physical cylinder
                    merged[-1][1] = max(merged[-1][1], hi)
                else:
                    merged.append([lo, hi])
            dx, dy, dz = g["dir"]
            fx, fy, fz = g["foot"]
            for lo, hi in merged:
                mid = (lo + hi) / 2.0
                cylinders.append({
                    "radius": round(g["radius"], 4),
                    "center": [round(fx + mid * dx, 4), round(fy + mid * dy, 4),
                               round(fz + mid * dz, 4)],
                    "axis": [round(dx, 4), round(dy, 4), round(dz, 4)],
                    "height": round(hi - lo, 4),
                })
        cylinders.sort(key=lambda c: (-c["radius"], c["center"]))

        # crude watertightness proxy: a valid single solid with positive volume
        watertight = bool(valid_solid and solid_count >= 1 and volume > 0)

        stl_out = sys.argv[2] if len(sys.argv) > 2 else None
        if stl_out:
            try:
                from build123d import export_stl
                export_stl(result, stl_out)
            except Exception:
                pass  # viewer asset only; grading output below is unaffected

        _emit({
            "valid_solid": valid_solid,
            "watertight": watertight,
            "volume": round(volume, 4),
            "bbox": [round(b, 4) for b in bbox],
            "bbox_center": [round(c, 4) for c in bbox_center],
            "com": [round(com.X(), 4), round(com.Y(), 4), round(com.Z(), 4)],
            "solid_count": solid_count,
            "face_count": face_count,
            "edge_count": edge_count,
            "cylinders": cylinders,
        })
    except Exception as e:
        _emit({"error": f"property extraction failed: {type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
