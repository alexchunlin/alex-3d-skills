"""Base: hollow shell, floor screws into bosses."""
from cadlib import geom as G, features as F, asm as A


def build(P):
    h = P.BASE / 2
    shell = G.prism("base", G.rrect(-h, h, -h, h, 6), 0, P.BASE_H, 'Z')
    G.bevel(shell, 0.8)
    cav = G.prism("cav", G.rrect(-h + P.WALL, h - P.WALL, -h + P.WALL, h - P.WALL, 4), -1, P.BASE_H - P.WALL, 'Z')
    shell = G.csg(shell, sub=[cav])
    bosses, cuts, screws = [], [], []
    for sx in (-1, 1):
        for sy in (-1, 1):
            at = (sx * (h - 5.5), sy * (h - 5.5), 0.0)        # head bears on the table side; boss merges into the wall
            # the boss runs up to the deck: printed deck-down, a boss that stops short starts in mid-air (cad printcheck)
            top = P.BASE_H - P.WALL + 0.5
            bosses += F.boss((at[0], at[1], top), (0, 0, 1), 7.0, top)   # pilot 11 mm deep from the floor end
            cuts += F.screw_hole(at, (0, 0, 1), 10, kind="selftap")
            screws.append(at)
    shell = G.csg(shell, add=bosses)
    shell = G.csg(shell, sub=cuts)
    A.part(shell, "PRT_base", 'PRT', "pla_a", stl="base", print_rot=A.R_FLIP, orient="deck on the bed",
           supports="no", infill=15)
    for i, at in enumerate(screws):
        A.fastener("FST_floor_%d" % i, at, (0, 0, 1), 10, "M3_pan", host="PRT_base", step="base")
