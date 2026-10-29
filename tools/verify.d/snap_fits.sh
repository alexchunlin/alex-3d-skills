# snap fits and print-in-place hinges (features.snap_hook, annular_snap, torsion_snap, pip_hinge; cadsnap; cadcheck snaps)
# and computed stress on flexures rows with dimensions: push-assist's flexures check trusted a typed 7.6 MPa that a
# reviewer's script put at 9-22 (PA-A3-T22); A3-F2's leaf spring printed standing up; v2 had ~103 screws in 18 types.
# watch: @core skills/print-cad-blender/scripts/cadsnap.py skills/print-cad-blender/scripts/cadlib/export.py
# watch: tools/verify.d/snap_fits_build.py tools/verify.d/snap_fits_cases.py tools/bench/assembly.py
# Sourced by tools/verify_all.sh (uses $ROOT $V $BL, calls ok/bad). About 15 s: plain python3 cases, one build, one
# cad check on it.
SF="$V/snaps"; mkdir -p "$SF"
CADW="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"
$CADW build "$ROOT/tools/verify.d/snap_fits_build.py" -- --out "$SF/m" > "$SF/build.log" 2>&1
python3 -I "$ROOT/tools/verify.d/snap_fits_cases.py" "$ROOT" "$SF/m" > "$SF/cases.txt" 2>&1 || echo "FAIL snaps: cases crashed (see $SF/cases.txt)" >> "$SF/cases.txt"
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$SF/cases.txt"
cat > "$SF/checks.json" <<'EOF'
{"slide_out": [{"name": "cover off the hook", "object": "PRT_hk_cover", "dir": [1, 0, 0], "dist": 40, "step": 1},
               {"name": "cover into the base", "object": "PRT_hk_cover", "dir": [-1, 0, 0], "dist": 10, "step": 1,
                "expect": "blocked", "blocked_by": ["PRT_hk_base"]}],
 "service": [{"op": "open the cover", "fasteners": [], "remove": ["PRT_hk_cover"]}],
 "assembly_order": [{"step": "base", "objects": ["PRT_hk_base"]}, {"step": "cover", "objects": ["PRT_hk_cover"]}],
 "flexures": [{"part": "PRT_leaf", "name": "typed 7.6", "dir": [1, 0, 0], "l": 30, "b": 8, "h": 1.5, "deflection": 4, "stress_mpa": 7.6},
              {"part": "PRT_leaf2", "name": "guided", "dir": [1, 0, 0], "l": 30, "b": 8, "h": 1.5, "deflection": 0.5, "end": "guided"}]}
EOF
nice -n 10 "$BL" -b --factory-startup "$SF/m/m.blend" --python "$ROOT/skills/print-cad-blender/scripts/cadcheck.py" -- \
  --config "$SF/checks.json" --only snaps,flexures,slide,service,insertion,interference --out "$SF/cadcheck.json" > "$SF/check.log" 2>&1
python3 -I - "$ROOT" "$SF" <<'PY' > "$SF/asserts.txt" 2>&1
import json, os, re, struct, sys
root, d = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "skills", "print-cad-blender", "scripts"))
import cadsnap as S
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "snaps: " + msg)
log = open(os.path.join(d, "build.log")).read()
say("SNAP_BUILT" in log and "SNAP_NOERR" not in log, "the build ran and every expected SnapError was raised (see build.log)")
say(re.search(r"SNAP_ERR short: hk_short: no arm thickness .* Make the arm >= [\d.]+ mm long, or the undercut <= [\d.]+ mm", log) is not None,
    "a hook too short for its undercut raises SnapError naming the length and undercut that would fit")
say("SNAP_ERR noledge: hk_far: PRT_far has no material at" in log, "a hook whose catch has no ledge raises SnapError")
say("SNAP_ERR annular_over: an_x: hoop strain 0.0500" in log and "use interference <= 0.17" in log,
    "an annular interference over the allowable raises SnapError with the largest that fits")
say("SNAP_ERR hinge_strict: hx: clearance 0.20 / gap 0.20 under 0.30" in log, "a hinge under 0.3 mm raises SnapError unless strict=False")
say("JOINS 6: 0 screws, 4 snaps, 2 print-in-place" in log, "the build log counts joins (screws, snaps, print-in-place)")
try:
    man = json.load(open(os.path.join(d, "m", "manifest.json")))
except Exception as e:
    man = {"joins": [], "join_summary": {}}
J = {j["name"]: j for j in man.get("joins", [])}
say(sorted(J) == ["an", "hb", "hg", "hk", "st", "ts"] and man.get("join_summary") == {"screws": 0, "snaps": 4, "print_in_place": 2, "joins": 6},
    "manifest joins: one record per call, and join_summary")
hk = J.get("hk", {})
say(hk.get("thickness") == 2.6 and hk.get("thickness_src") == "sized" and hk.get("strain", 1) <= hk.get("allow", 0) and
    all(k in hk for k in ("P_n", "W_insert_n", "W_release_n", "beam_dir", "allow_src", "source")) and hk.get("W_release_n") is None,
    "snap_hook record: sized thickness, strain within the allowable, P / W_insert / W_release (None: retain 90 self-locks), source (%s)" % {k: hk.get(k) for k in ("thickness", "strain", "allow", "P_n", "W_insert_n")})
ok_re = True
for n in ("hk", "an", "ts"):
    r = S.recheck(J.get(n, {"kind": "x"}), "PLA", [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) if n in J else {}
    ok_re &= bool(r) and abs(r["strain"] - J[n]["strain"]) < 1e-4 and abs(r["P_n"] - J[n]["P_n"]) < 0.02
say(ok_re, "cadsnap.recheck reproduces each snap record's strain and force from its dims")
ts, an = J.get("ts", {}), J.get("an", {})
say(ts.get("bar_d") == 3.0 and ts.get("bar_d_src") == "sized" and an.get("interference") == 0.15 and an.get("bore_d") == 10.2,
    "torsion bar sized to bar_d_max 3.0; annular interference sized to 0.15 mm over the measured 10.2 mm bore")
stl = os.path.join(d, "m", "stl")
ntri = lambda f: struct.unpack("<I", open(os.path.join(stl, f), "rb").read()[80:84])[0] if os.path.isfile(os.path.join(stl, f)) else -1
say(ntri("pip_hg.stl") == ntri("hg_a.stl") + ntri("hg_b.stl") > 0 and os.path.isfile(os.path.join(stl, "pip_hg.3mf")),
    "the export writes pip_hg.stl / .3mf with both hinge parts (%d = %d + %d triangles)" % (ntri("pip_hg.stl"), ntri("hg_a.stl"), ntri("hg_b.stl")))
try:
    rep = json.load(open(os.path.join(d, "cadcheck.json")))
    s = rep["summary"]
except Exception as e:
    rep, s = {"checks": {}}, {"fail_list": [], "warn_list": []}
    say(False, "cad check wrote a report (%s)" % e)
fl, wl = s["fail_list"], s["warn_list"]
rows = {r["name"]: r for r in rep["checks"].get("snaps", {}).get("rows", [])}
say(rows.get("hk", {}).get("result") == "pass" and not any("snap_hook hk:" in x for x in fl),
    "a hook sized in the layer plane passes (strain %s <= %s)" % (rows.get("hk", {}).get("value"), rows.get("hk", {}).get("limit")))
say(any(x.startswith("snaps: snap_hook st: strain 0.0159 > 0.0068 allowed for PRT_st_post") and "across layers" in x and "in the layer plane" in x for x in fl),
    "the same hook standing up in print fails against the layer-bond allowable (A3-F2)")
say(rows.get("an", {}).get("result") == "pass" and rows.get("ts", {}).get("result") == "pass" and rows.get("ts", {}).get("quantity") == "shear strain",
    "the annular and torsion snaps pass (the torsion one on shear strain vs (1 + nu) x the allowable)")
say(any(x.startswith("snaps: pip_hinge hb: radial clearance 0.20 mm < 0.30") for x in fl) and any(x.startswith("snaps: pip_hinge hb: axial gap 0.20") for x in fl)
    and any(x.startswith("clearance: PRT_hb_a to PRT_hb_b only 0.19 mm across a joint at hb=-") for x in fl),
    "a hinge with 0.2 mm gaps fails on its record and on the swept clearance (an in-range pose, not the overtravel one)")
hg = [x for x in fl + wl if "PRT_hg_" in x or "pip_hinge hg" in x]
say(not hg and rows.get("hg", {}).get("same_print") is True and rows.get("hg", {}).get("axis_to_bed_deg") == 0.0,
    "a good hinge: no finding while swept -120..0 (the generated fits rule, FromPolygons BVH), axis flat, one print (%s)" % hg[:2])
say(any("snap_hook hk is permanent (retain 90 deg) but service op open the cover removes PRT_hk_cover" in x for x in wl),
    "a permanent snap on a part a service op removes warns")
sl = {r["object"]: r for r in rep["checks"].get("slide", {}).get("rows", [])}
off, into = sl.get("cover off the hook", {}), sl.get("cover into the base", {})
say(off.get("blocked_by") is None and "PRT_hk_base" in (off.get("flexed") or {}) and off.get("snap_flex", {}).get("PRT_hk_base"),
    "slide: the cover comes off past the hook's barb, which rides its catch as a generated flex (%s)" % off.get("flexed"))
say(into.get("blocked_by") == ["PRT_hk_base"] and not any("cover into the base" in x for x in fl),
    "negative control: the snap flex is bounded, so the cover driven into the base is still stopped by it")
ins = {r["object"]: r for r in rep["checks"].get("insertion", {}).get("rows", [])}
say(ins.get("PRT_hk_cover", {}).get("free_dir") is not None and not any("insertion" in x and "PRT_hk_cover" in x for x in wl),
    "insertion does not count the hook's catch as an obstacle to it")
fr = {r["part"]: r for r in rep["checks"].get("flexures", {}).get("rows", [])}
say(fr.get("PRT_leaf", {}).get("stress_src") == "computed" and fr["PRT_leaf"]["stress_mpa"] == 22.0 and fr["PRT_leaf"]["declared_mpa"] == 7.6
    and any(x.startswith("flexures: PRT_leaf (typed 7.6): computed bending stress 22.0 MPa > PLA in_mpa 17.5") for x in fl)
    and any("stress_mpa 7.6 typed, 22.0 MPa computed" in x for x in wl),
    "a flexures row with l, b, h and deflection gets its stress computed (22.0, not the typed 7.6: PA-A3-T22) and fails")
say(fr.get("PRT_leaf2", {}).get("stress_mpa") == 5.5 and not any("PRT_leaf2" in x for x in fl + wl),
    "negative control: a guided leaf within the allowable passes (5.5 MPa)")
say(len(fl) == 5 and "Traceback" not in open(os.path.join(d, "check.log")).read() and any("snaps:" in c and "(scene)" in c for c in rep.get("coverage", [])),
    "exactly the five fails, no traceback, records read from the blend (%s)" % fl)
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; *) bad "snaps: $st $msg" ;; esac; done < "$SF/asserts.txt"
