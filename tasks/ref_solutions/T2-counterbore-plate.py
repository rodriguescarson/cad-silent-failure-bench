# Reference solution for T2-counterbore-plate (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Box, Cylinder, Locations, Mode

with BuildPart() as plate:
    Box(70, 70, 12)                        # z -6..6
    with Locations((0, 0, 3)):
        Cylinder(radius=10, height=6, mode=Mode.SUBTRACT)   # counterbore: z 0..6 (top face)
    Cylinder(radius=5.5, height=12, mode=Mode.SUBTRACT)     # through-hole

result = plate.part
