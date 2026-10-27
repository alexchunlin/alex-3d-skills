"""Deck (the ground, modelled where it lies): servo rim, board standoffs, lid bosses."""
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    L, W, T = P.DECK
    deck = G.box("deck", -L / 2, L / 2, -W / 2, W / 2, 0, T)
    G.bevel(deck, P.EB)
    s = K.C["servo"]
    cl, cw, _ = s["case"]
    cx = P.SERVO_AT[0] - s["spline"]["offset_from_case_centre"]     # case centre, toward -X
    i0, i1 = cl / 2 + P.RIM_CLR, cw / 2 + P.RIM_CLR
    rim = G.box("rim", cx - i0 - P.RIM_W, cx + i0 + P.RIM_W, -i1 - P.RIM_W, i1 + P.RIM_W, T - 0.01, T + P.RIM_H)
    rim = G.csg(rim, sub=[G.box("rim_in", cx - i0, cx + i0, -i1, i1, T - 1, T + P.RIM_H + 1)])
    pcb = K.C["pcb"]["connectors"]["mount"]["pattern"]      # the board's datasheet pattern, ["rect", 42, 32]
    top = T + P.PCB_GAP
    posts = [G.cyl("so", (P.PCB_AT[0] + x, P.PCB_AT[1] + y), P.STANDOFF_D / 2, T - 0.01, top, 'Z') for x, y in M.pattern_points(pcb)]
    lid = M.rect(*P.LID_SCREWS)
    bosses = [G.cyl("lb", (P.PCB_AT[0] + x, P.PCB_AT[1] + y), P.LID_BOSS_D / 2, T - 0.01, T + P.LID_BOSS_H, 'Z')
              for x, y in M.pattern_points(lid)]
    deck = G.csg(deck, add=[rim] + posts + bosses)
    M.connector(deck, "servo", (cx, 0, T), (0, 0, 1), note="case bottom centre, inside the rim")
    M.connector(deck, "pcb", (P.PCB_AT[0], P.PCB_AT[1], top), (0, 0, 1), pattern=pcb, hole="M2.5")
    M.connector(deck, "lid", (P.PCB_AT[0], P.PCB_AT[1], T + P.LID_BOSS_H), (0, 0, 1), pattern=lid, hole="M3")
    M.part(deck, "PRT_deck", 'PRT', "pla_a", stl="deck", print_rot=A.R_ID, orient="flat, underside on the bed",
           supports="no", infill=20)
