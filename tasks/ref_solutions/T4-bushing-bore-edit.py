# Reference solution for T4-bushing-bore-edit (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Mode

with BuildPart() as bushing:
    Cylinder(radius=15, height=40)
    Cylinder(radius=12, height=40, mode=Mode.SUBTRACT)

result = bushing.part
