# T2-lbracket spec-ambiguity decision (2026-07-07)

## The ambiguity
The sentence *"a horizontal base plate 60x40, and a vertical wall 60 mm wide rising from one
60 mm edge of the base to an overall height of 40 mm"* was read two ways:
- **Reference/grader:** overall depth = 40 mm; the 8 mm wall sits inside the 60x40 footprint (wall
  at y 0-8). bbox_y = 40.
- **Aravind (expert):** full 60x40 base plus an 8 mm wall added outboard (wall at y 40-48).
  bbox_y = 48.

This inverted every L-bracket judgment: the 9 brackets Aravind passed are all 48 mm (grader fails
them on `depth`+`volume`); the one at exactly 40 mm (item 076) is the only one Aravind failed and the
only one the grader passed. Perfect anti-correlation = one definitional split, not rater noise.

## Decision: adopt the reference reading (40 mm overall depth). No oracle change.
Two independent reasons:

1. **Standard angle-bracket convention is heel-to-toe.** Angle/L-bracket leg lengths are dimensioned
   from the outer corner (heel) to the end of the leg (toe), i.e. the *overall* leg length. Under
   that convention a 40 mm base leg IS the 40 mm overall depth, with the wall thickness contained
   within it (wall outer face coincident with the heel at y=0). This matches the reference, not the
   48 mm reading. (Sources below.)
2. **Internal consistency of our own spec.** The sentence already says the wall rises to an
   *"overall height of 40 mm."* The vertical leg is stated as overall, so the horizontal leg's 40 mm
   must be read the same way (overall), giving 40 mm total depth. The 48 mm reading applies "overall"
   to the height but "bare plate" to the depth, which is inconsistent.

Consequence: the grader was correct throughout. This is a finding about natural-language spec
underspecification, not a grader bug; report it as such. Reproducible numbers (scripts/expert_kappa.py
-> data/expert_kappa.json):
- **As scored (primary reported): kappa = 0.64**, raw agreement 82.7%, n=81 (substantial).
- **Excluding the one ambiguous T2-lbracket task (sensitivity): kappa = 0.87**, raw 93.5%, n=62
  (real labels, one task dropped -- the defensible adjusted number).
- Informational only (not a reported agreement, circular): if the expert re-judges the lbracket
  split under the clarified spec, kappa = 0.89.
No benchmark re-run and no oracle/code change are required; the run-time nl_spec is left as the
historical stimulus and the clarification is documented in tasks/T2-lbracket.json.

## Reworded spec sentence (removes the ambiguity for future raters/agents)
> Model an L-bracket (angle bracket) from two 8 mm-thick legs that share a common corner. The
> horizontal leg (base) has an overall footprint of 60 mm (width) x 40 mm (depth). The vertical leg
> (wall) is 60 mm wide and rises from one 60 mm edge of the base, its outer face flush with that
> edge, to an overall height of 40 mm. Measured heel-to-toe the overall depth is 40 mm and the
> overall height is 40 mm; both legs lie within these overall dimensions (the wall is not added
> outboard of the base). Drill one Ø8 mm hole through the base (vertical axis), centred 30 mm along
> the width and 28 mm from the wall; and one Ø8 mm hole through the wall (horizontal axis), centred
> 30 mm along the width and 24 mm above the base bottom.

## Follow-up
Emailed Aravind 2026-07-07 (Resend 34e5b2c5) asking him to confirm the heel-to-toe reading as
standard. If he agrees (expected), the reconciliation is closed with expert sign-off, which is the
strongest form for the paper. Then regrade the 10 lbracket items under the clarified spec and report
kappa = 0.85.

## Sources (angle-bracket heel-to-toe convention)
- Steel-Detail group, "Dimension to heel or toe of angle?": https://groups.io/g/Steel-Detail/topic/dimension_to_heel_or_toe_of/82037728
- Mid Continent Steel & Wire, steel angle sizes (leg lengths measured heel-to-toe): https://mcswusa.com/steel-angle-sizes/
- Stress Ebook LLC, angle bracket sizing (heel/toe terminology): https://www.stressebook.com/angle-bracket-sizing-stress-analysis/
