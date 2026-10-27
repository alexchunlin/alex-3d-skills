"""mates_task_v2 reference: named parameters (mm, deg). No placement coordinates: the mates derive them."""
import os

EB = 0.6
DECK = (160.0, 120.0, 6.0)
PAN_LO, PAN_HI = -90.0, 90.0
TILT_LO, TILT_HI = -25.0, 60.0
TILT_ABOVE_HORN = 40.0       # tilt axis above the pan horn's disc top (brief)
CAM_AHEAD = 25.0 + float(os.environ.get("MATES_REF_CAM_DX", 0))   # board back ahead of the tilt axis; selftest plants an error
T = 4.0                      # bracket plate thickness
SINK_M25 = 3.0               # counterbore for the pan servo screws under the deck
COVER_CLR, COVER_WALL = 1.0, 2.0
COVER_BOSS_H, EAR_T = 6.0, 3.0
GROUND = "PRT_deck"
RENDER_POSES = {"pan45_tilt30": {"PIV_pan": 45, "PIV_tilt": 30}, "tilt-25": {"PIV_tilt": -25}}
