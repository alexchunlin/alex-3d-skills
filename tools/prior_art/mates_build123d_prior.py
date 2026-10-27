"""Prior art for cadlib.mates: build123d joints (RigidJoint, RevoluteJoint), measured. Needs the CADGenBench venv:
    /tmp/cgb-venv/bin/python -I tools/prior_art/mates_build123d_prior.py
"""
# Prior-art measurement: build123d RigidJoint/RevoluteJoint frame convention and pattern handling.
from build123d import *
deck = Box(80, 80, 10)                      # z -5..5
lid = Box(40, 40, 4)                        # z -2..2
RigidJoint("top", deck, Location((0, 0, 5)))            # z out of the deck's top face
RigidJoint("bottom", lid, Location((0, 0, -2), (180, 0, 0)))  # z out of the lid's bottom face (outward)
deck.joints["top"].connect_to(lid.joints["bottom"])
bb = lid.bounding_box()
print("outward-normal frames on both: lid z %.2f..%.2f (deck top at 5)" % (bb.min.Z, bb.max.Z))
lid2 = Box(40, 40, 4)
RigidJoint("bottom", lid2, Location((0, 0, -2)))        # same-direction z (build123d's convention)
deck.joints["top"].connect_to(lid2.joints["bottom"])
bb = lid2.bounding_box()
print("same-direction frames: lid z %.2f..%.2f" % (bb.min.Z, bb.max.Z))
arm = Box(60, 10, 5)
RevoluteJoint("pivot", deck, Axis((0, 0, 5), (0, 0, 1)), angular_range=(-90, 90))
RigidJoint("hub", arm, Location((-25, 0, -2.5)))
deck.joints["pivot"].connect_to(arm.joints["hub"], angle=30)
c = arm.center()
print("revolute at 30: arm centre (%.2f, %.2f, %.2f)" % (c.X, c.Y, c.Z))
try:
    deck.joints["pivot"].connect_to(arm.joints["hub"], angle=120)
except Exception as e:
    print("revolute at 120:", type(e).__name__, e)
# a pattern: one joint per hole, nothing compares two patterns
holes_deck = [Location((x, y, 5)) for x in (-29, 29) for y in (-24.5, 24.5)]
holes_pcb = [Location((x, y, 0)) for x in (-29, 29) for y in (-24.75, 24.75)]   # 0.5 mm off in y
print("joint per hole; a 0.5 mm pattern mismatch is placed without complaint: build123d has no pattern type")
print("kinds:", [k for k in ("RigidJoint", "RevoluteJoint", "LinearJoint", "CylindricalJoint", "BallJoint")])
