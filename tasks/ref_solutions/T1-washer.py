# Reference solution for T1-washer (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Mode

with BuildPart() as washer:
    Cylinder(radius=20, height=3)
    Cylinder(radius=10.5, height=3, mode=Mode.SUBTRACT)

result = washer.part
