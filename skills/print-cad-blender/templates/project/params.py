"""Named parameters (mm, deg). Everything a reviewer may want to tune lives here. Joints come from the mates
(parts/*.py), not from here."""

# --- detail set: every G.bevel and G.rrect takes one of these, never a literal
EB = 0.8                  # edge break on every printed edge
CR = 6.0                  # outer corner radius
CR_S = 4.0                # inner (cavity) corner radius
# --- base
BASE = 80.0
BASE_H = 30.0
WALL = 2.4
SCREW = "M3"             # fastener size for the fastened mates (M2, M2.5, M3, M4, M5)
FLOOR_PITCH = BASE - 11.0  # floor screw square
# --- moving stage
STAGE_R = 30.0
STAGE_T = 5.0
CLR = 0.5                 # running clearance between bodies that move relative to each other
PAN_LO, PAN_HI = -90.0, 90.0

GROUND = "PRT_base"       # assemble() places every other part from this one through the mates
RENDER_POSES = {"pan-90": {"PIV_pan": -90}, "pan+90": {"PIV_pan": 90}}
