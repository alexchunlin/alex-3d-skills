"""printcheck's face pass and STL edge count, plain python3 (no Blender). Run by printcheck_overhangs.sh.

    python3 -I printcheck_overhangs_cases.py <skill scripts dir> <v2 stl dir> <v2 manifest> <scratch dir> [review stl dir]

Prints one CASE {...} line per case with "ok". The cases:
  ramp      the 20 mm ramp of docs/features/blend-bracket.md ("The printcheck gap"): underside 5-25 deg from horizontal
            fails by the face pass (the layer check alone gave 0 fails), 30-40 deg warns (the user's two bands), 45 and 50
            deg are not flagged
  tube      a 20 mm tube 30 mm off one wall fails (its underside is anchored at one end); the same tube spanning 20 mm
            between two walls is a sloped bridge, and horizontal holes of 6 and 20 mm through a block are sloped bridges: no finding
  v2        the 36 shipped v2 STLs: the face pass adds no fail or warn; the layer check still fails exactly jar_valve,
            feeder_cover, base_shell, post_R; edges in more than 2 faces: base_shell 7, every other part (hood's
            5 um slivers included) 0
  prior    tools/prior_art/overhang_regions.py (PR #6, the per-region area rule its review proposed: fail at 100 mm2
            projected) on the same synthetic parts: its ramp regions match printcheck's projected area within 2 %, and
            it would fail the 20 mm hole and the tube between walls, which print as bridges
  review    the PR #11 review's parts (printcheck_overhangs_build.py, cadlib): slabs between pillars at different
            heights, a slab in a corner, a 3 mm tab at 10 deg, a lying cylinder and a wedge from the bed, a fillet under
            an 8 mm shelf fail; teardrops, horizontal holes, a tube between walls, 45 deg chamfers, domes, a slab between
            a wall and a 1.2 mm fin and a 2 mm filleted ledge do not fail
  tangent   r 5 / 10 / 15 cylinders lying on the bed at 24 / 36 / 64 facets each fail once as a tangent bed contact; with
            a 0.3 r flat cut on the underside they do not
  sheet     two boxes sharing a face (a coplanar join) are a zero-thickness sheet, two touching along an edge a line
            contact: each reported as itself
  jar_valve the user's print (2026-10-26, labels.json PF-jar_valve print_evidence: drooped without supports):
            `printcheck.py jar_valve.stl --where --section auto` exits 1 and shows the 3 tabs at z 2 with world
            coordinates and as C on the layer section
"""
import json, math, os, subprocess, sys
import numpy as np

SCR, V2, MAN, OUT = sys.argv[1:5]
sys.path.insert(0, SCR)
import printcheck as PC  # noqa: E402
os.makedirs(OUT, exist_ok=True)
ALL = True


def case(name, ok, **kw):
    global ALL
    ALL = ALL and bool(ok)
    print("CASE " + json.dumps(dict(case=name, ok=bool(ok), **kw)))


def prism_x(prof, x0, x1, flip=False):
    """Closed triangles of a convex counter-clockwise (y, z) profile extruded along x (flip: inside out)."""
    T, n = [], len(prof)
    P0 = [np.array([x0, y, z]) for y, z in prof]
    P1 = [np.array([x1, y, z]) for y, z in prof]
    for i in range(1, n - 1):
        T.append([P0[0], P0[i + 1], P0[i]])
        T.append([P1[0], P1[i], P1[i + 1]])
    for i in range(n):
        j = (i + 1) % n
        T += [[P0[i], P0[j], P1[j]], [P0[i], P1[j], P1[i]]]
    T = np.array(T, float)
    return T[:, ::-1] if flip else T


def box(x0, x1, y0, y1, z0, z1):
    return prism_x([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], x0, x1)


def circle(cy, cz, r, n=32):
    return [(cy + r * math.cos(2 * math.pi * i / n), cz + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def write_stl(path, T):
    import struct
    with open(path, "wb") as f:
        f.write(b"\0" * 80 + struct.pack("<I", len(T)))
        for t in np.asarray(T, np.float32):
            f.write(struct.pack("<3f", 0, 0, 0) + t.tobytes() + b"\0\0")
    return path


SYN = {}


def faces_flagged(r):
    return [f for f in r["findings"] if f["kind"] == "overhang"]


# ramp: a 10 x 20 mm column with a wedge whose underside rises at a from horizontal, reaching 20 mm out
for a in (5, 10, 15, 20, 25, 30, 35, 40, 45, 50):
    t = math.tan(math.radians(a))
    L = min(20.0, 30.0 / t)
    T = np.concatenate([box(0, 20, 0, 10, 0, 40), prism_x([(10, 5), (10 + L, 5 + L * t), (10 + L, 40), (10, 40)], 0, 20)])
    SYN["ramp_%d" % a] = T
    r = PC.analyze(T, supports="no")
    f = faces_flagged(r)
    want = "fail" if a < 30 else "warn" if a < 45 else None      # two bands: under 30 deg from horizontal fails, 30-45 warns
    if a in (20, 30, 40):
        SYN["ramp_%d_pc" % a] = max(g["projected_mm2"] for g in r["faces"])
    case("ramp_%d" % a, [x["status"] for x in f] == [want] if want else not f, want=want,
         face_findings=[x["msg"][:70] for x in f], layer_fails=sum(x["status"] == "fail" for x in r["findings"] if x["kind"] != "overhang"))

# tubes and holes: 20 mm tube (r 10, 24-gon) off one wall, between two walls; 6 and 20 mm holes through a block
wall = lambda x0, x1: box(x0, x1, -20, 20, 0, 40)
tube = prism_x(circle(0, 20, 10, 24), 0, 30)
r1 = PC.analyze(np.concatenate([wall(-10, 0), tube]), supports="no")
SYN["tube_between_walls"] = np.concatenate([wall(-10, 0), prism_x(circle(0, 20, 10, 24), 0, 20), wall(20, 30)])
r2 = PC.analyze(SYN["tube_between_walls"], supports="no")
case("tube_off_one_wall", any(x["status"] == "fail" for x in faces_flagged(r1)), max_face_overhang_mm=r1["max_face_overhang_mm"])
case("tube_between_walls", not faces_flagged(r2) and any(g["kind"] == "bridge" and g["status"] == "ok" for g in r2["faces"]),
     findings=[x["msg"][:70] for x in faces_flagged(r2)])
for d in (6, 20):
    blk = np.concatenate([box(0, 20, -15, 15, 0, 30), prism_x(circle(0, 15, d / 2, 32), 0, 20, flip=True)])
    SYN["hole_%d" % d] = blk
    r = PC.analyze(blk, supports="no")
    case("hole_%d" % d, not faces_flagged(r) and not any(x["status"] == "fail" for x in r["findings"]),
         faces=[(g["kind"], g.get("span_mm"), g["status"]) for g in r["faces"]][:3])

# prior art on the same parts: projected area per region, no anchors
names = ["ramp_20", "ramp_30", "ramp_40", "tube_between_walls", "hole_6", "hole_20"]
paths = [write_stl(os.path.join(OUT, n + ".stl"), SYN[n]) for n in names]
pa = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(SCR.rstrip("/")), "..", "..", "tools", "prior_art", "overhang_regions.py"),
                     "--hi", "44.92"] + paths, capture_output=True, text=True)
try:
    rows = json.loads(pa.stdout)
    rows = rows.get("parts", rows) if isinstance(rows, dict) else rows
    big = {r["part"]: max([g["projected_mm2"] for g in r["regions"]] or [0]) for r in rows}
except (ValueError, KeyError, TypeError) as e:
    big = {"error": "%s %s" % (e, pa.stderr[-300:])}
ramp_ok = all(abs(big.get("ramp_%d" % a, 0) - SYN["ramp_%d_pc" % a]) <= 0.02 * SYN["ramp_%d_pc" % a] for a in (20, 30, 40))
case("prior_art_area_rule", ramp_ok and big.get("hole_20", 0) >= 100 and big.get("tube_between_walls", 0) >= 100,
     prior_largest_projected_mm2=big, printcheck_ramp_projected_mm2={a: SYN["ramp_%d_pc" % a] for a in (20, 30, 40)})

# the PR #11 review's parts: verdict of the face pass ("-": no sloped finding; warn: a sloped bridge over 25 mm)
REV = {"A_corner_10deg": "fail", "A0_ramp_one_wall_10deg": "fail", "B_pillars_rise20": "fail", "B2_pillars_rise10_30mm": "fail",
       "D_ramp10_needle": "fail", "D2_wall_and_fin_0.05mm": "fail", "E_bed_wedge20": "fail", "E2_lying_cyl_r10": "warn+tangent",
       "E2_lying_cyl_r15": "warn+tangent", "E2_lying_cyl_r5": "-+tangent", "H_shelf8_fillet4": "fail", "J_rib_w3_10deg": "fail", "J_rib_w4_10deg": "fail",
       "C_gable20deg_20mm": "-", "D2_wall_and_fin_1.2mm": "-", "F0_tube20_round_bore": "-",
       "F_screw_hole_print_up": "-", "F_teardrop_20": "-", "F_teardrop_20_rot30": "-", "F_teardrop_6": "-", "F_tube20_print_up": "-",
       "G_box_bevel_1p5": "-", "G_shelf_on_45_gusset": "-", "H_shelf2_fillet2": "-", "I_dome_ri9": "-", "J_rib_w3_flat": "-",
       "C_gable20deg_40mm": "warn", "C_hole40": "warn", "I_dome_ri18": "warn"}
if len(sys.argv) > 5:
    got = {}
    for n in REV:
        fp = os.path.join(sys.argv[5], n + ".stl")
        if not os.path.isfile(fp):
            got[n] = "missing"
            continue
        r = PC.analyze(PC.read_stl(fp), supports="no")
        st = [f["status"] for f in faces_flagged(r)]
        got[n] = ("fail" if "fail" in st else "warn" if st else "-") + ("+tangent" if any(
            f["kind"] == "tangent" and f["status"] == "fail" for f in r["findings"]) else "")
    case("review_parts", got == REV, wrong={n: (got[n], REV[n]) for n in REV if got[n] != REV[n]}, parts=len(got))

# a cylinder lying on the bed, vertex down as cadlib's cyl builds it: a tangent bed contact at every radius and facet
# count; the same cylinder with a flat 0.3 r wide cut on its underside is not one
def lying(r_, nf, flat=0.0):
    raw = [(r_ * math.cos(-math.pi / 2 + 2 * math.pi * i / nf), r_ * math.sin(-math.pi / 2 + 2 * math.pi * i / nf)) for i in range(nf)]
    zc = -math.sqrt(r_ * r_ - (flat / 2) ** 2) if flat else -2 * r_
    prof = []
    for i in range(nf):
        p0, p1 = raw[i], raw[(i + 1) % nf]
        if p0[1] >= zc:
            prof.append(p0)
        if (p0[1] - zc) * (p1[1] - zc) < 0:
            t = (zc - p0[1]) / (p1[1] - p0[1])
            prof.append((p0[0] + t * (p1[0] - p0[0]), zc))
    z0 = min(z for _, z in prof)
    return prism_x([(y, z - z0) for y, z in prof], 0, 40)


ver = {}
for r_ in (5, 10, 15):
    for nf in (24, 36, 64):
        for fl in (0.0, 0.3 * r_):
            r = PC.analyze(lying(r_, nf, fl), supports="no")
            ver["r%d_n%d%s" % (r_, nf, "_flat" if fl else "")] = sum(f["kind"] == "tangent" and f["status"] == "fail" for f in r["findings"])
case("lying_cylinder_tangent", all(v == (0 if k.endswith("_flat") else 1) for k, v in ver.items()), tangent_fails=ver)

# zero-thickness sheet against a line contact
sheet = PC.analyze(np.concatenate([box(0, 10, 0, 10, 0, 10), box(10, 20, 0, 10, 0, 10)]), supports="no")
line = PC.analyze(np.concatenate([box(0, 10, 0, 10, 0, 10), box(10, 20, 10, 20, 0, 10)]), supports="no")
msg = lambda r: [f["msg"][:110] for f in r["findings"] if f["kind"] == "nonmanifold"]
case("sheet_vs_line_contact", sheet["stl_sheet_edges"] > 0 and sheet["stl_nonmanifold_edges"] == 0 and "back to back" in str(msg(sheet))
     and "overlap them" not in str(msg(sheet)) and line["stl_nonmanifold_edges"] == 1 and line["stl_sheet_edges"] == 0,
     sheet=msg(sheet), line=msg(line))

# v2 shipped STLs
rep = PC.run([V2], manifest=MAN, out=os.path.join(OUT, "v2.json"))
P = {r["stl"]: r for r in rep["parts"]}
fails = sorted(n for n, r in P.items() if any(f["status"] == "fail" for f in r["findings"]))
ov = {n: [f["msg"][:60] for f in faces_flagged(r)] for n, r in P.items() if faces_flagged(r)}
nm = {n: r["stl_nonmanifold_edges"] for n, r in P.items() if r["stl_nonmanifold_edges"]}
case("v2_face_pass", len(P) == 36 and not ov and fails == ["base_shell", "feeder_cover", "jar_valve", "post_R"],
     parts=len(P), face_findings=ov, fails=fails, max_face_overhang_mm=max(r["max_face_overhang_mm"] for r in P.values()))
case("v2_stl_edges", nm == {"base_shell": 7} and any(f["kind"] == "nonmanifold" and f["status"] == "warn" for f in P["base_shell"]["findings"]),
     nonmanifold=nm)

# the print-confirmed miss
p = subprocess.run([sys.executable, "-I", os.path.join(SCR, "printcheck.py"), os.path.join(V2, "jar_valve.stl"), "--manifest", MAN,
                    "--out", os.path.join(OUT, "jar_valve.json"), "--where", "--section", "auto"], capture_output=True, text=True)
tabs = [l for l in p.stdout.splitlines() if l.strip().startswith("FAIL    layer z   2.0") and "cantilever 5." in l and "world [" in l]
sec = [l for l in p.stdout.splitlines() if l.strip().startswith("section z 2.1")]
cs = sum(l.count("C") for l in p.stdout.splitlines() if l[:12].strip().replace(".", "").replace("-", "").isdigit())
case("jar_valve_print_evidence", p.returncode == 1 and len(tabs) == 3 and sec and cs > 50, exit=p.returncode, tab_lines=len(tabs),
     sections=len(sec), c_cells=cs)
print("CASES_ALL " + json.dumps({"ok": ALL}))
