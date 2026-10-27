"""Moving stage: a disc on the base deck, turning on PIV_pan. Modelled on its own underside."""
from cadlib import geom as G, mates as M, asm as A


def build(P):
    disc = G.cyl("stage", (0, 0), P.STAGE_R, 0, P.STAGE_T, 'Z')
    G.bevel(disc, P.EB)
    M.connector(disc, "bottom", (0, 0, 0), (0, 0, -1))
    M.part(disc, "PRT_stage", 'PRT', "pla_b", stl="stage", print_rot=A.R_ID, orient="flat", supports="no", infill=25)
    # the interface, once: face to face with the deck, CLR apart, turning about the deck connector's z
    M.mate("PRT_base:deck", "PRT_stage:bottom", "revolute", name="PIV_pan", lo=P.PAN_LO, hi=P.PAN_HI, sweep_step=15,
           gap=P.CLR, designed_gap=True, fit="clearance")
