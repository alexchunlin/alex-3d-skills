"""Deck (the ground), the pan servo screwed up into it from below, and the cover over the pan servo."""
from cadlib import geom as G, mates as M, asm as A
import kit_parts as K


def build(P):
    S = K.C["servo"]
    L, W, D = P.DECK
    c = S["case"]
    cx = c["centre_x"]                                   # case centre from the spline (pan axis)
    hx, hy = c["length_x"] / 2 + P.COVER_CLR + P.COVER_WALL, c["width_y"] / 2 + P.COVER_CLR + P.COVER_WALL
    ear = hx + 5.0                                       # cover screws on the case's long axis, outside the walls
    deck = G.box("deck", -L / 2, L / 2, -W / 2, W / 2, 0, D)
    G.bevel(deck, P.EB)
    deck = G.csg(deck, add=[G.cyl("boss", (cx + s * ear, 0), 4.0, D - 0.01, D + P.COVER_BOSS_H, 'Z') for s in (-1, 1)])
    bottom = S["connectors"]["bottom"]["pattern"]
    M.connector(deck, "servo", (cx, 0, D), (0, 0, 1), pattern=bottom, hole="M2.5")
    M.connector(deck, "cover", (cx, 0, D + P.COVER_BOSS_H), (0, 0, 1), pattern=M.line(2 * ear, 2), hole="M3")
    M.part(deck, "PRT_deck", 'PRT', "pla_a", stl="deck", print_rot=A.R_ID,
           orient="flat, underside on the bed", supports="no", infill=20)

    srv = M.from_component(K.servo("servo_pan"), S)
    M.part(srv, "BUY_servo_pan", 'BUY', "buy", mass_g=S["mass_g"], src=S["src"])
    M.mate("PRT_deck:servo", "BUY_servo_pan:bottom", "fastened", name="pan_servo", step="pan servo (deck on its back)",
           fastener=dict(style="tapped", depth=S["tapped_holes"]["bottom"]["depth"], head="cap", sink=P.SINK_M25,
                         head_on="a"))

    # cover: modelled on its ear plane (z 0 = boss tops), centred on the case; the top stops under the horn screws
    top_in = c["height_z"] + 0.5 - P.COVER_BOSS_H            # case top + 0.5, from the ear plane
    ix, iy = hx - P.COVER_WALL, hy - P.COVER_WALL
    cov = G.box("cover", -hx, hx, -hy, hy, -P.COVER_BOSS_H + 0.3, top_in + 1.5)
    cov = G.csg(cov, sub=[G.box("cov_in", -ix, ix, -iy, iy, -P.COVER_BOSS_H, top_in),
                          G.cyl("cov_spline", (-cx, 0), 6.0, top_in - 1, top_in + 3, 'Z')])
    cov = G.csg(cov, add=[G.box("ear", s * (hx - 1), s * (ear + 4.5), -4.5, 4.5, 0, P.EAR_T) if s > 0 else
                          G.box("ear", s * (ear + 4.5), s * (hx - 1), -4.5, 4.5, 0, P.EAR_T) for s in (-1, 1)])
    M.connector(cov, "ears", (0, 0, 0), (0, 0, -1), pattern=M.line(2 * ear, 2), hole="M3")
    M.part(cov, "PRT_cover", 'PRT', "pla_b", stl="cover", print_rot=A.R_FLIP, orient="top on the bed",
           supports="yes: under the 2 screw ears", infill=20)
    M.mate("PRT_deck:cover", "PRT_cover:ears", "fastened", name="cover", step="cover",
           fastener=dict(style="selftap", head="cap"))
