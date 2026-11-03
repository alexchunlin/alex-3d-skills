# parameter-perturbation audit (tools/bench/perturb.py, issue #45): nudge a params value by a print tolerance, rebuild,
# re-check, and list the findings that flip (V2A5-T2: a shared params change brought 14 drop fails; V2A3-F1: a stop sized
# for the nominal candy).
# watch: @core tools/bench/perturb.py tools/bench/replay.py examples/demo-turret/**
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 30 s: plain python3 parser cases, then two
# audits of the demo turret (CLR and SINK at +-0.2 mm plus a control; CLR at -0.45) with --only interference.
PA="$V/perturb"; rm -rf "$PA"; mkdir -p "$PA"
T="$ROOT/examples/demo-turret"
P="$ROOT/tools/bench/perturb.py"

# 1 the parser and the rewrite (no Blender): tuple unpacking, a signed value, tuple elements, a UTF-8 comment before the
# literal on the line, derived values and ints skipped, angles by name and by comment; the rewrite touches the literal only
python3 -I - "$P" <<'PY' > "$PA/cases.txt" 2>&1 || echo "FAIL perturb: parser cases crashed" >> "$PA/cases.txt"
import os, sys; sys.path.insert(0, os.path.dirname(sys.argv[1])); import perturb as Q
src = 'import math\nCLR = 0.5   # running gap\nA_LO, PSI_C, Z = -3.0, 45.0, 2 * CLR\nMM_T = (6.3, 7.5)\nN = 3\n' \
      'TWIST = 30.0\nW = 2.4  # tilt sweep 12 deg\nS = "x"\nL = CLR + 1\n'
ps, sk = Q.list_params(src)
names = [p["name"] for p in ps]
ang = sorted(p["name"] for p in ps if p["angle"])
ok1 = names == ["CLR", "A_LO", "PSI_C", "MM_T[0]", "MM_T[1]", "TWIST", "W"] and ang == ["A_LO", "PSI_C", "TWIST", "W"] \
      and {"Z", "N", "S", "L"} <= {n for n, _ in sk}
print(("PASS" if ok1 else "FAIL") + " perturb: lists CLR, A_LO, PSI_C, MM_T[0..1], TWIST, W; skips derived Z/L, int N, string S; angles %s (got %s)" % (ang, names))
by = {p["name"]: p for p in ps}
out = Q.rewrite(src, by["A_LO"]["span"], -3.2)
out = Q.rewrite(out, Q.list_params(out)[0][4]["span"], 7.7)
u = 'X = 1.0\nÉ = 1.0; B = (1.5, 2.5)  # é\n'
ub = Q.rewrite(u, Q.list_params(u)[0][3]["span"], 2.7)
ok2 = "A_LO, PSI_C, Z = (-3.2), 45.0, 2 * CLR\n" in out and "MM_T = (6.3, 7.7)\n" in out and out.count("\n") == src.count("\n") \
      and ub == 'X = 1.0\nÉ = 1.0; B = (1.5, 2.7)  # é\n'
print(("PASS" if ok2 else "FAIL") + " perturb: the rewrite changes only the literal's span (signed, a tuple element, after UTF-8 text)")
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/cases.txt"

# 2 two parameters, both signs, a control rebuild; the nominal is built once; the source is never edited
before=$(shasum "$T/build.py" | cut -c1-40)
CAD="$CAD" python3 -I "$P" "$T" --params-file build.py --build-args "--out {out}" --params '^(CLR|SINK)$' --only interference -j 2 \
  --out "$PA/a" > "$PA/a.log" 2>&1; rc_a=$?
python3 -I - "$PA/a" "$rc_a" <<'PY' > "$PA/a.txt" 2>&1 || echo "FAIL perturb: audit JSON unreadable (see $PA/a.log)" >> "$PA/a.txt"
import json, os, sys
d, rc = sys.argv[1], sys.argv[2]
r = json.load(open(os.path.join(d, "perturb.json")))
ps = {p["name"]: p for p in r["params"]}
both = sorted(ps) == ["CLR", "SINK"] and all(set(p["runs"]) == {"-", "+"} and all("check_s" in x for x in p["runs"].values()) for p in ps.values())
print(("PASS" if both and rc == "0" else "FAIL") + " perturb: CLR and SINK each built and checked at -0.2 and +0.2 mm (exit %s, params %s)" % (rc, sorted(ps)))
builds = sorted(x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "build.log")))
print(("PASS" if r["nominal_builds"] == 1 and builds.count("nominal") == 1 and len(builds) == 6 else "FAIL")
      + " perturb: one nominal build for 4 perturbed runs and the control (%s)" % " ".join(builds))
c = r["control"] or {}
print(("PASS" if c.get("flips") == [] and c.get("drift_n") == 0 and not c.get("stls_changed") else "FAIL")
      + " perturb: the control rebuild flips nothing (%s)" % c.get("summary"))
m = ps["CLR"]["runs"]["-"]
moved = all(x["stls_changed"] for p in ps.values() for x in p["runs"].values())
rek = any(l.startswith("rekeyed clearance: PRT_base to PRT_pan") for l in m["drift"]) and not ps["CLR"]["brittle"]
print(("PASS" if moved and rek and "param CLR: 0.5 -> 0.3" in m["manifest"] else "FAIL")
      + " perturb: every nudge moved geometry; CLR 0.5 -> 0.3 rekeys 'base to pan' (at -> just past the limit), not a flip (%s)" % m["drift"][:2])
md = open(os.path.join(d, "perturb.md")).read()
print(("PASS" if "| CLR | 0.5 | ±0.2 mm |" in md and "Cost: nominal build" in md else "FAIL") + " perturb: the markdown table has a CLR row and the cost line")
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/a.txt"
[ "$(shasum "$T/build.py" | cut -c1-40)" = "$before" ] && ok "perturb: examples/demo-turret/build.py untouched (scratch copies only)" || bad "perturb: the source build.py changed"

# 3 negative control: CLR 0.5 -> 0.05 must fail the declared arm/barrel fit (min 0.10) and mark CLR brittle
CAD="$CAD" python3 -I "$P" "$T" --params-file build.py --build-args "--out {out}" --params '^CLR$' --delta 0.45 --only interference \
  --no-control --out "$PA/neg" > "$PA/neg.log" 2>&1
python3 -I - "$PA/neg/perturb.json" <<'PY' > "$PA/neg.txt" 2>&1 || echo "FAIL perturb: planted nudge: no JSON (see $PA/neg.log)" >> "$PA/neg.txt"
import json, re, sys
r = json.load(open(sys.argv[1]))
p = r["params"][0]
new = [f["line"] for f in p["runs"]["-"]["flips"] if f["change"] == "new" and f["status"] == "fail"]
hit = [l for l in new if re.search(r"clearance: PRT_arm_[LR] to PRT_barrel only 0\.05 mm", l)]
print(("PASS" if len(hit) == 2 and p["brittle"] and r["brittle"] == ["CLR"] else "FAIL")
      + " perturb: planted CLR -0.45 mm: the arm/barrel fit fails on both arms, CLR brittle (%d new fails: %s)" % (len(new), [l[:60] for l in new]))
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/neg.txt"
