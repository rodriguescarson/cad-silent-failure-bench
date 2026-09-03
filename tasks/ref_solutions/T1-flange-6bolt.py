# Reference solution for T1 (grader calibration only — NEVER shown to the agent).
# Run the extractor on this to confirm the task's checks pass on a known-good part:
#   python -m benchmark._extract tasks/ref_solutions/T1-flange-6bolt.py
from build123d import BuildPart, Cylinder, PolarLocations, Mode

with BuildPart() as flange:
    Cylinder(radius=60, height=14)                                  # OD 120, t 14
    Cylinder(radius=20, height=14, mode=Mode.SUBTRACT)              # Ø40 bore
    with PolarLocations(radius=47.5, count=6):                      # 95 PCD
        Cylinder(radius=5.5, height=14, mode=Mode.SUBTRACT)        # 6× Ø11

result = flange.part
