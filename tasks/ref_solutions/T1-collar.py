# Reference solution for T1-collar (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Mode

with BuildPart() as collar:
    Cylinder(radius=22.5, height=15)
    Cylinder(radius=12.5, height=15, mode=Mode.SUBTRACT)

result = collar.part
