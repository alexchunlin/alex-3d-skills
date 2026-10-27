"""Board on the deck standoffs, and the lid over it."""
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    pcb = M.from_component(K.pcb(), K.C["pcb"])
    M.part(pcb, "BUY_pcb", 'BUY', "pcb", mass_g=K.C["pcb"]["mass_g"], src=K.C["pcb"]["src"])
    M.mate("PRT_deck:pcb", "BUY_pcb:mount", "fastened", name="pcb", fit="clearance", step="board",
           fastener=dict(style="selftap", head="pan"))

    # lid modelled on its ear plane (z 0 = boss tops); walls stop 0.3 above the deck, top LID_TOP_CLR over the parts
    bL, bW, bT = K.C["pcb"]["board"]
    tall = K.C["pcb"]["tallest_above_board"]
    ix, iy = bL / 2 + P.LID_CLR, bW / 2 + P.LID_CLR
    ox, oy = ix + P.LID_WALL, iy + P.LID_WALL
    z_deck = -P.LID_BOSS_H
    z_in = z_deck + P.PCB_GAP + bT + tall + P.LID_TOP_CLR
    shell = G.box("lid", -ox, ox, -oy, oy, z_deck + 0.3, z_in + P.LID_WALL)
    shell = G.csg(shell, sub=[G.box("lid_in", -ix, ix, -iy, iy, z_deck, z_in)])
    sx, sy = P.LID_SCREWS[0] / 2, P.LID_SCREWS[1] / 2
    r = P.LID_BOSS_D / 2 + 0.5
    ears = [G.box("ear", x - r, x + r, s * (oy - 1), s * (sy + r), 0, P.EAR_T) for x in (-sx, sx) for s in (-1, 1)]
    shell = G.csg(shell, add=ears)
    G.bevel(shell, P.EB)
    M.connector(shell, "ears", (0, 0, 0), (0, 0, -1), pattern=M.rect(*P.LID_SCREWS), hole="M3")
    M.part(shell, "PRT_lid", 'PRT', "pla_b", stl="lid", print_rot=A.R_FLIP, orient="top on the bed",
           supports="yes: under the 4 screw ears", infill=20)
    M.mate("PRT_deck:lid", "PRT_lid:ears", "fastened", name="lid", step="lid",
           fastener=dict(style="selftap", head="cap"))
