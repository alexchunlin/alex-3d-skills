"""Moving stage on PIV_pan."""
from cadlib import geom as G, asm as A


def build(P):
    z0 = P.BASE_H + P.CLR
    disc = G.cyl("stage", (0, 0), P.STAGE_R, z0, z0 + P.STAGE_T, 'Z')
    G.bevel(disc, P.EB)
    A.part(disc, "PRT_stage", 'PRT', "pla_b", joint="PIV_pan", stl="stage", print_rot=A.R_ID, orient="flat",
           supports="no", infill=25)
