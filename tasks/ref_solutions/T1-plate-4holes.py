# Reference solution for T1-plate-4holes (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Box, Cylinder, Locations, Mode

with BuildPart() as plate:
    Box(80, 80, 8)
    with Locations((25, 25), (25, -25), (-25, 25), (-25, -25)):
        Cylinder(radius=4.5, height=8, mode=Mode.SUBTRACT)

result = plate.part
