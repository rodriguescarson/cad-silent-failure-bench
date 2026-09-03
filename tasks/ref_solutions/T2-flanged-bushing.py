# Reference solution for T2-flanged-bushing (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Locations, Mode

with BuildPart() as bushing:
    with Locations((0, 0, 3)):
        Cylinder(radius=30, height=6)      # flange: z 0..6
    with Locations((0, 0, 15)):
        Cylinder(radius=15, height=30)     # hub: z 0..30
    with Locations((0, 0, 15)):
        Cylinder(radius=10, height=30, mode=Mode.SUBTRACT)  # through-bore

result = bushing.part
