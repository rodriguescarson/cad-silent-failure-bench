# Reference solution for T4-flange-8bolt-edit (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Locations, Mode, PolarLocations

with BuildPart() as flange:
    Cylinder(radius=60, height=14)
    Cylinder(radius=20, height=14, mode=Mode.SUBTRACT)
    with PolarLocations(radius=47.5, count=8):
        Cylinder(radius=5.5, height=14, mode=Mode.SUBTRACT)

result = flange.part
