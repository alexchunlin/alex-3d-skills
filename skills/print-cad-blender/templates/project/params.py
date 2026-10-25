"""Named parameters (mm, deg) and the joint tree. Everything a reviewer may want to tune lives here."""
from cadlib import asm

# --- base
BASE = 80.0
BASE_H = 30.0
WALL = 2.4
SCREW = "M3"             # fastener size for features.fastener_joint (M2, M2.5, M3, M4, M5)
# --- moving stage
STAGE_R = 30.0
STAGE_T = 5.0
CLR = 0.5                 # running clearance between bodies that move relative to each other
PAN_LO, PAN_HI = -90.0, 90.0

RENDER_POSES = {"pan-90": {"PIV_pan": -90}, "pan+90": {"PIV_pan": 90}}


def joints():
    asm.joint("PIV_pan", (0, 0, BASE_H), 'Z', PAN_LO, PAN_HI, step=15)
