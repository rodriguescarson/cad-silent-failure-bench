"""Kernel-dependent extractor tests (need build123d/OCP — run via .venv). Skip cleanly otherwise.

Regression for the coaxial-cylinder bug: two same-radius coaxial faces lie on one infinite cylinder
surface and used to be deduped into a single detection; they must be reported as two features, while
a single hole whose face is split by a boolean seam must still count once.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import build123d  # noqa: F401
    HAVE_KERNEL = True
except ImportError:
    HAVE_KERNEL = False

from benchmark.executor import Build123dExecutor  # noqa: E402

COAXIAL_SEATS = """
from build123d import BuildPart, Cylinder, Locations
with BuildPart() as shaft:
    with Locations((0, 0, 10)):
        Cylinder(radius=15, height=20)
    with Locations((0, 0, 60)):
        Cylinder(radius=20, height=80)
    with Locations((0, 0, 110)):
        Cylinder(radius=15, height=20)
result = shaft.part
"""

THROUGH_HOLE = """
from build123d import BuildPart, Box, Cylinder, Mode
with BuildPart() as plate:
    Box(60, 60, 10)
    Cylinder(radius=5, height=10, mode=Mode.SUBTRACT)
result = plate.part
"""


def test_coaxial_same_radius_cylinders_counted_separately():
    if not HAVE_KERNEL:
        print("  (skipped: build123d not installed)")
        return
    props = Build123dExecutor().run(COAXIAL_SEATS).props
    seats = [c for c in props["cylinders"] if abs(c["radius"] - 15) < 0.1]
    assert len(seats) == 2, props["cylinders"]
    assert sorted(round(c["height"]) for c in seats) == [20, 20]
    journal = [c for c in props["cylinders"] if abs(c["radius"] - 20) < 0.1]
    assert len(journal) == 1 and abs(journal[0]["height"] - 80) < 0.1


def test_seam_split_hole_counted_once():
    if not HAVE_KERNEL:
        print("  (skipped: build123d not installed)")
        return
    props = Build123dExecutor().run(THROUGH_HOLE).props
    holes = [c for c in props["cylinders"] if abs(c["radius"] - 5) < 0.1]
    assert len(holes) == 1, props["cylinders"]
    assert abs(holes[0]["height"] - 10) < 0.1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                fails += 1
    print(f"\n{'FAILED' if fails else 'all kernel tests passed'}")
    raise SystemExit(1 if fails else 0)
