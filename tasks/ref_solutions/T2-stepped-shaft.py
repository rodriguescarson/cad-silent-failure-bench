# Reference solution for T2 (grader calibration only — NEVER shown to the agent).
#   python -m benchmark._extract tasks/ref_solutions/T2-stepped-shaft.py
from build123d import BuildPart, Cylinder, Locations

with BuildPart() as shaft:
    with Locations((0, 0, 10)):
        Cylinder(radius=15, height=20)    # bearing seat 1:  z 0..20
    with Locations((0, 0, 60)):
        Cylinder(radius=20, height=80)    # central journal: z 20..100
    with Locations((0, 0, 110)):
        Cylinder(radius=15, height=20)    # bearing seat 2:  z 100..120

result = shaft.part
