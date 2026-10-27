"""Base: hollow shell, floor screws into bosses."""
from cadlib import geom as G, features as F, asm as A


def build(P):
    h = P.BASE / 2
    shell = G.prism("PRT_base", G.rrect(-h, h, -h, h, P.CR), 0, P.BASE_H, 'Z')    # final name: cutters come back under it
    G.bevel(shell, P.EB)
    cav = G.prism("cav", G.rrect(-h + P.WALL, h - P.WALL, -h + P.WALL, h - P.WALL, P.CR_S), -1, P.BASE_H - P.WALL, 'Z')
    shell = G.csg(shell, sub=[cav])
    pts = [(sx * (h - 5.5), sy * (h - 5.5), 0.0) for sx in (-1, 1) for sy in (-1, 1)]   # heads bear on the table side
    # the boss runs up to the deck: printed deck-down, a boss that stops short starts in mid-air (cad printcheck)
    top = P.BASE_H - P.WALL + 0.5
    shell = G.csg(shell, add=[b for x, y, z in pts for b in F.boss((x, y, top), (0, 0, 1), 7.0, top)])   # boss merges into the wall
    # one call per screw: measures the stack, picks the stock length, cuts, places the FST (P.SCREW = "M3" -> "M4")
    cuts = {}
    for i, at in enumerate(pts):
        F.fastener_joint("FST_floor_%d" % i, P.SCREW, at, (0, 0, 1), [shell], style="selftap", head="pan", step="base", cuts=cuts)
    shell = G.csg(shell, sub=cuts[shell.name])
    A.part(shell, "PRT_base", 'PRT', "pla_a", stl="base", print_rot=A.R_FLIP, orient="deck on the bed",
           supports="no", infill=15)
