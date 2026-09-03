# Reference solution for T1-bushing (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Mode

with BuildPart() as bushing:
    Cylinder(radius=15, height=40)
    Cylinder(radius=10, height=40, mode=Mode.SUBTRACT)

result = bushing.part
