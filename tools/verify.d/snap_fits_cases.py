"""Plain-python cases for cadsnap (snap_fits.sh): the Bayer constants, the wedge relation, allowables, sizing, the
torsion and annular relations, leaf stress, and the bench assembly report's join columns on a small fixture.

    python3 -I tools/verify.d/snap_fits_cases.py ROOT [BUILD_DIR]

BUILD_DIR: snap_fits_build.py's output (its manifest.json feeds the bench fixture); without it that case is skipped.
"""
import json, math, os, sys, tempfile
ROOT = sys.argv[1]
sys.path.insert(0, os.path.join(ROOT, "skills", "print-cad-blender", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tools", "bench"))
import cadsnap as S
import cadmat as M


def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "snaps: " + msg)


near = lambda a, b, tol=1e-3: a is not None and b is not None and abs(a - b) <= tol * max(1.0, abs(b))
K1, C1 = S.cantilever(1.0)
K2, _ = S.cantilever(0.5)
say(near(K1, 1.5) and near(C1, 0.25), "constant-section cantilever: eps = 1.5 y h / l^2 (Bayer y = 0.67 eps l^2 / h), P = E b h^3 y / 4 l^3 (%.4f, %.4f)" % (K1, C1))
say(near(1 / K2, 1.09, 2e-3), "thickness halving to the tip: y = 1.09 eps l^2 / h (Bayer; Simpson gives %.4f)" % (1 / K2))
r = S.hook(15, 2.0, 6, 1.0, 2200, 1.0, 0.5, 30, 90)
say(near(r["strain"], 1.5 * 1.0 * 2.0 / 225) and near(r["P_n"], 6 * 2.0 ** 2 * 2200 * r["strain"] / (6 * 15)),
    "hook: strain and P = b h^2 E eps / (6 l) agree with the deflection form (P %.2f N)" % r["P_n"])
say(near(r["W_insert_n"], r["P_n"] * (0.5 + math.tan(math.radians(30))) / (1 - 0.5 * math.tan(math.radians(30)))) and r["W_release_n"] is None,
    "W = P (mu + tan a) / (1 - mu tan a) on the 30 deg lead-in; a 90 deg retaining face self-locks (None)")
say(S.wedge(10, 64.0, 0.5) is None and S.wedge(10, 63.0, 0.5) is not None, "negative control: self-locking starts where mu tan a = 1 (63.4 deg at mu 0.5), not before")
er, _ = S.allowable("PLA", "repeated")
eo, src_o = S.allowable("PLA", "once")
ea, src_a = S.allowable("PLA", "repeated", across=True)
say(near(er, M.MATERIALS["PLA"]["snap_strain"]) and near(eo * S.ONCE_FACTOR, er) and near(ea, 15 / 2200) and "across" in src_a,
    "allowables from cadmat: repeated = snap_strain %.4f, once = / 0.6 = %.4f, across layers = across_mpa / E = %.4f" % (er, eo, ea))
h = S.size_hook(15, 6, 2.0, 2200, er)
say(h == 1.2 and S.hook(15, 1.2, 6, 2.0, 2200)["strain"] <= er < S.hook(15, 1.3, 6, 2.0, 2200)["strain"] and S.size_hook(15, 6, 0.8, 2200, er) == 3.0,
    "size_hook: the thickest arm within the strain, in 0.1 steps (1.2 mm for a 2 mm undercut), capped at l / 5 (3.0 for 0.8)")
say(S.size_hook(4, 6, 1.5, 2200, er) is None, "a 4 mm arm can't take a 1.5 mm undercut: None (snap_hook raises SnapError)")
t = S.torsion(7, 3.0, 10, 0.6, 2200, 0.35)
say(near(t["phi_deg"], math.degrees(0.06)) and near(t["shear_strain"], 0.06 * 1.5 / 7) and
    near(t["P_n"], 2 * 2200 / 2.7 * math.pi * 3 ** 4 / 32 * 0.06 / 7 / 10),
    "torsion: phi = y / lever, gamma = phi r / l, P = 2 G J phi / (l lever) (gamma %.4f, P %.2f N)" % (t["shear_strain"], t["P_n"]))
a = S.annular(10, 0.15, 2200, 13, 0.35)
X = 0.62 * math.sqrt(0.3 / 2.3) / ((1.69 + 1) / 0.69 + 0.35)
say(near(a["strain"], 0.015) and near(a["X"], X) and near(a["P_n"], 0.15 * 10 * 2200 * X),
    "annular: eps = dd / d, P = dd d E X (X %.4f, P %.1f N)" % (X, a["P_n"]))
say(near(S.beam_stress(30, 1.5, 4, 2200), 22.0) and near(S.beam_stress(30, 1.5, 4, 2200, "guided"), 44.0) and
    near(S.beam_stress(30, 1.5, 4, 2200, kt=1.5), 33.0), "leaf stress: 3 E h y / 2 l^2 free, 3 E h y / l^2 guided, times kt")
say(near(S.beam_angle([[1, 0, 0], [0, 1, 0], [0, 0, 1]], (0, 0, 1)), 90) and S.layer_stress_dir("along", 90) and
    not S.layer_stress_dir("normal", 90) and S.layer_stress_dir("normal", 0),
    "layer direction: a beam standing up crosses layers, a ring with its axis up does not, a ring lying down does")
try:
    S.allowable("PLA", "often")
    say(False, "uses='often' is refused")
except ValueError:
    say(True, "uses='often' is refused")

# the bench assembly report: snaps, print-in-place and joins columns, from a cached scan and the build's manifest
bd = sys.argv[2] if len(sys.argv) > 2 else None
if bd and os.path.isfile(os.path.join(bd, "manifest.json")):
    import assembly as AS
    run = tempfile.mkdtemp(prefix="snapbench-")
    os.makedirs(os.path.join(run, "fx"))
    man = json.load(open(os.path.join(bd, "manifest.json")))
    scan = {"printed": [{"name": n, "body": p.get("joint", "static")} for n, p in man["parts"].items() if p.get("kind") == "PRT"],
            "purchased": [], "cables": [], "assembly_order": ["a", "b"],
            "fasteners": [{"name": "FST_m3", "nut": False, "body": "static", "part": "M3_cap x 12", "d": 3.0, "length": 12.0,
                           "head_d": 5.5, "source": "cadlib"}]}
    json.dump(scan, open(os.path.join(run, "fx", "assembly_scan.json"), "w"))
    src = os.path.relpath(bd, AS.ROOT)
    rows = [AS.report("fx", {"dir": src, "as": "m.blend"}, __import__("pathlib").Path(run))]
    md = AS.markdown(rows)
    r0 = rows[0]
    say(r0["snaps"] == 4 and r0["print_in_place"] == 2 and r0["joins"] == 7,
        "bench assembly: 4 snaps, 2 print-in-place, joins = 1 screw + 6 = 7 from the manifest's joins (%s)" % {k: r0[k] for k in ("snaps", "print_in_place", "joins")})
    say("| snaps | print-in-place | joins |" in md and "| fx | 14 | 0 | 1 | 1 | 4 | 2 | 7 |" in md, "the markdown table has the columns: %s" % md.splitlines()[-1])
    os.remove(os.path.join(run, "fx", "assembly_scan.json"))
    scan.pop("fasteners")
    scan["fasteners"] = []
    json.dump(scan, open(os.path.join(run, "fx", "assembly_scan.json"), "w"))
    r1 = AS.report("fx", {"dir": "tools/bench/fixtures", "as": "m.blend"}, __import__("pathlib").Path(run))
    say(r1["snaps"] == 0 and r1["print_in_place"] == 0 and r1["joins"] == 0,
        "negative control: a design with no records (no manifest joins, no scan joins) counts 0 snaps and 0 joins")
else:
    say(False, "the build's manifest.json for the bench case (%s)" % bd)
