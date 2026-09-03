# Reference solution for T2-pulley-blank (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Locations, Mode

with BuildPart() as pulley:
    with Locations((0, 0, 8)):
        Cylinder(radius=40, height=16)     # disc: z 0..16
    with Locations((0, 0, 18)):
        Cylinder(radius=16, height=36)     # hub: z 0..36
    with Locations((0, 0, 18)):
        Cylinder(radius=8, height=36, mode=Mode.SUBTRACT)   # through-bore

result = pulley.part
