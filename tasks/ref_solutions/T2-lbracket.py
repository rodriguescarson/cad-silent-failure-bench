# Reference solution for T2-lbracket (grader calibration only — NEVER shown to the agent).
from build123d import BuildPart, Box, Cylinder, Locations, Mode

with BuildPart() as bracket:
    with Locations((30, 20, 4)):
        Box(60, 40, 8)                      # base: x 0..60, y 0..40, z 0..8
    with Locations((30, 4, 20)):
        Box(60, 8, 40)                      # wall: x 0..60, y 0..8,  z 0..40
    with Locations((30, 28, 4)):
        Cylinder(radius=4, height=8, mode=Mode.SUBTRACT)                      # base hole (Z axis)
    with Locations((30, 4, 24)):
        Cylinder(radius=4, height=8, rotation=(90, 0, 0), mode=Mode.SUBTRACT)  # wall hole (Y axis)

result = bracket.part
