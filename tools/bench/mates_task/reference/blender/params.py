"""mates_task reference: named parameters (mm, deg). Placement numbers come from the brief, once each."""
import os

EB = 0.6
DECK = (140.0, 90.0, 4.0)
SERVO_AT = (-35.0, 0.0)          # spline axis (brief)
RIM_CLR, RIM_W, RIM_H = 0.2, 2.0, 4.0
ARM_LEN, ARM_T, ARM_HUB_R, ARM_TIP_R = 70.0, 4.0, 10.0, 6.0
ARM_LO, ARM_HI = -90.0, 90.0
PCB_AT = (35.0 + float(os.environ.get("MATES_REF_PCB_DX", 0)), 0.0)   # selftest plants a board offset here
PCB_GAP = 8.0                    # board underside above the deck top (brief)
STANDOFF_D = 6.0
LID_CLR, LID_WALL, LID_TOP_CLR = 1.2, 2.0, 1.4
LID_SCREWS = (40.0, 56.0)        # rect pattern of the lid screws, centred on the board
LID_BOSS_D, LID_BOSS_H, EAR_T = 8.0, 6.0, 3.0
GROUND = "PRT_deck"
RENDER_POSES = {"arm-90": {"PIV_arm": -90}, "arm+90": {"PIV_arm": 90}}
