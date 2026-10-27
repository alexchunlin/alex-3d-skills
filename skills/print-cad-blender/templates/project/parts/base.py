"""Base: hollow shell, floor screws into bosses. The ground part: modelled where it stands."""
from cadlib import geom as G, features as F, mates as M, asm as A


def build(P):
    h = P.BASE / 2
    shell = G.prism("base", G.rrect(-h, h, -h, h, P.CR), 0, P.BASE_H, 'Z')
    G.bevel(shell, P.EB)
    cav = G.prism("cav", G.rrect(-h + P.WALL, h - P.WALL, -h + P.WALL, h - P.WALL, P.CR_S), -1, P.BASE_H - P.WALL, 'Z')
    shell = G.csg(shell, sub=[cav])
    floor = M.rect(P.FLOOR_PITCH, P.FLOOR_PITCH)
    # the bosses run up to the deck: printed deck-down, a boss that stops short starts in mid-air (cad printcheck)
    top = P.BASE_H - P.WALL + 0.5
    shell = G.csg(shell, add=[b for x, y in M.pattern_points(floor) for b in F.boss((x, y, top), (0, 0, 1), 7.0, top)])
    # connectors: z points out of the part from the mating face; the holes come from the same pattern as the bosses
    M.connector(shell, "deck", (0, 0, P.BASE_H), (0, 0, 1))
    M.connector(shell, "floor", (0, 0, 0), (0, 0, -1), pattern=floor, hole=P.SCREW)
    M.part(shell, "PRT_base", 'PRT', "pla_a", stl="base", print_rot=A.R_FLIP, orient="deck on the bed",
           supports="no", infill=15)
    # one self-tap screw per pattern point, head on the table side: assemble() measures, picks lengths and cuts
    M.fasten("PRT_base:floor", name="FST_floor", size=P.SCREW, head="pan", step="base")
