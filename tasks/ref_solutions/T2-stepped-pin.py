# Reference solution for T2-stepped-pin (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Cylinder, Locations

with BuildPart() as pin:
    with Locations((0, 0, 10)):
        Cylinder(radius=6, height=20)      # Ø12: z 0..20
    with Locations((0, 0, 32.5)):
        Cylinder(radius=5, height=25)      # Ø10: z 20..45
    with Locations((0, 0, 52.5)):
        Cylinder(radius=4, height=15)      # Ø8:  z 45..60

result = pin.part
