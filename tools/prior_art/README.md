# Prior art: what was evaluated before writing cadcheck, cadq and cadlib

Measured 2026-10-24 on the attempt-1 outputs (copies in `/tmp/alex3d-a1`).

| Option | What it would replace | Measured | Result |
|---|---|---|---|
| Attempt-1 `checks.py` (the designer's own) | cadcheck | R1 re-ran it on the attempt-1 blend (`review/checks_rerun.json`): 35 parts manifold, 0 interference at 9 poses | Misses both R1 blockers. It excludes Fasteners and Cables, treats zero-volume contact as fine, and only checks nominal poses (0, 22.5, 45). Its manifold, wall, overhang and stability code was kept and extended in cadcheck. |
| trimesh 4 + manifold3d (`trimesh_compare.py`, via `uv run`) | per-part checks | 29 STLs in 0.16 s: all watertight, volumes match cadcheck, overhang area matches the unsplit figure (arm_cover_l 2707 mm²) | Fine for per-part checks, but STLs carry no assembly placement, joints, fasteners or purchased parts, so none of the 8 tool-catchable R1 issues can be expressed. Blender's `MANIFOLD` boolean solver is the same library, so staying in Blender costs no accuracy and needs no install. |
| Blender MCP server / persistent daemon (e.g. blender-mcp, a socket add-on in GUI Blender) | cold starts, interactive queries | Not installed. Instead I measured the cost it would remove: `Blender -b` cold start 0.69 s, loading the 6 MB blend 0.70 s; D1 spent 2.3 of 64 min in Blender (27 runs) | No speed case. One-shot `cad q` gives the same queries with no extra process, port or add-on. Revisit only if a GUI session is wanted for the user. |
| build123d / CadQuery (B-rep, STEP, robust fillets) | cadlib geometry | Not measured this run (needs OCP, a ~100 MB wheel) | Candidate for the aesthetics gap (R1 #16-17: inconsistent edge breaks, as Blender bevel-after-boolean is fragile). The next revision should measure fillet success on the attempt's parts before considering it. |
