# parameter-perturbation audit (tools/bench/perturb.py, issue #45): nudge a params value by a print tolerance, rebuild,
# re-check, and list the findings that flip (V2A5-T2: a shared params change brought 14 drop fails; V2A3-F1: a stop sized
# for the nominal candy).
# watch: @core tools/bench/perturb.py tools/bench/replay.py examples/demo-turret/**
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 30 s: plain python3 parser and class cases,
# then two audits of the demo turret with --only interference,distances: CLR and SINK at +-0.2 mm plus a control, over
# an overlay with one pinned distances row; and CLR planted at 0.05 (--range, no band) as the negative control.
PA="$V/perturb"; rm -rf "$PA"; mkdir -p "$PA"
T="$ROOT/examples/demo-turret"
P="$ROOT/tools/bench/perturb.py"

# 1 no Blender. The parser and the rewrite: tuple unpacking, a signed value, tuple elements, UTF-8 before the literal,
# derived values and ints skipped, angles by name and by comment. The classes: pinned one- and two-sided (a bound within d
# of the nominal), not pinned 0.3 away, coverage warns and fixed findings never brittle, labels of the given attempt only.
python3 -I - "$P" <<'PY' > "$PA/cases.txt" 2>&1 || echo "FAIL perturb: parser cases crashed" >> "$PA/cases.txt"
import os, sys; from pathlib import Path; sys.path.insert(0, os.path.dirname(sys.argv[1])); import perturb as Q
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
def fl(line, change="new", status="fail"):
    return {"change": change, "status": status, "line": line, "key": line[:30]}
two = fl("distances: PRT_hood to PRT_flywheel = 6.40 mm (along ray) at hood=0.3, wanted 6.0..6.4 (row)")
one = fl("clearance: PRT_feeder_housing to PRT_feeder_disc only 0.10 mm across a joint at feeder=-60 (min 0.30; declared fit)")
far = fl("distances: PRT_hood to PRT_flywheel = 7.21 mm (along ray) at hood=-0.5, wanted 6.8..7.2 (row)")
cov = fl("interference: PRT_hood x PRT_flywheel not proven clear between the sampled poses at flywheel=0..15", status="warn")
swp = fl("distances: PRT_hood to BUY_tape: the swept ray missed a part at 1 of 53 stations", status="warn")
fix = fl("clearance: PRT_base to FST_arm_0 0.90 mm at pan=92.5", change="fixed", status="warn")
c = lambda f, nom, d=0.2: Q.classify(f, [], [], set(), nom, d)[0]
got = [c(two, 6.5), c(one, 0.3), c(far, 6.5), c(cov, 6.5), c(swp, 6.5), c(fix, 0.5), c(one, 0.3, None)]
for f, k in zip((two, one, far, cov, swp, fix), got):
    f["class"] = k
never = [Q.bad_flip(f) for f in (two, one, cov, swp, fix)]
print(("PASS" if got == ["pinned", "pinned", "design", "coverage", "coverage", "fixed", "design"] and not any(never)
       and Q.bad_flip(far) and Q.bad_flip(two, with_pinned=True) else "FAIL")
      + " perturb: classes: wanted 6.0..6.4 at 6.5 and (min 0.30; at 0.30 pinned, 6.8..7.2 at 6.5 design, 2 coverage warns, a fixed warn, no band (--range) not pinned; none of pinned/coverage/fixed brittle (got %s)" % got)
LJ = Path(os.path.dirname(sys.argv[1])) / "labels.json"
lab, pf = Q.load_labels(LJ, "v2a7")
none_, _ = Q.load_labels(LJ, None)
print(("PASS" if lab and {e["attempt"] for e, _ in lab} == {"v2a7"} and not none_ and all("v2a7" in e["attempts"] for e, _ in pf) else "FAIL")
      + " perturb: --attempt v2a7 loads only v2a7's labels (%s); no attempt, no labels" % sorted({e["id"] for e, _ in lab}))
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/cases.txt"

# 2 two parameters, both signs, a control rebuild; the nominal is built once; the project copies are removed; the source
# dir is never edited. The overlay adds a row that restates CLR (base to pan >= 0.45, 0.05 from CLR's 0.5): CLR -0.2
# fails it, and that pinned flip must not make CLR brittle (brittle_with_pinned does count it).
srchash() { find "$T" -type f | LC_ALL=C sort | xargs shasum | shasum | cut -c1-40; }
before=$(srchash)
python3 -I - "$T/checks.json" "$PA/pin.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c["distances"] = [{"name": "pan above deck", "a": "PRT_base", "b": "PRT_pan", "min": 0.45, "why": "restates CLR (perturb_audit pinned case)"}]
json.dump(c, open(sys.argv[2], "w"), indent=1)
PY
CAD="$CAD" python3 -I "$P" "$T" --params-file build.py --build-args "--out {out}" --params '^(CLR|SINK)$' --checks "$PA/pin.json" \
  --only interference,distances -j 2 --out "$PA/a" > "$PA/a.log" 2>&1; rc_a=$?
python3 -I - "$PA/a" "$rc_a" <<'PY' > "$PA/a.txt" 2>&1 || echo "FAIL perturb: audit JSON unreadable (see $PA/a.log)" >> "$PA/a.txt"
import json, os, sys
d, rc = sys.argv[1], sys.argv[2]
r = json.load(open(os.path.join(d, "perturb.json")))
ps = {p["name"]: p for p in r["params"]}
both = sorted(ps) == ["CLR", "SINK"] and all(set(p["runs"]) == {"-", "+"} and all("check_s" in x for x in p["runs"].values()) for p in ps.values())
print(("PASS" if both and rc == "0" else "FAIL") + " perturb: CLR and SINK each built and checked at -0.2 and +0.2 mm (exit %s, params %s)" % (rc, sorted(ps)))
runs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))
left = sorted("%s/%s" % (x, y) for x in runs for y in os.listdir(os.path.join(d, x)) if y not in ("build.log", "check.log", "cadcheck.json", "manifest.json", "diff.txt"))
print(("PASS" if r["nominal_builds"] == 1 and runs == ["CLRm", "CLRp", "SINKm", "SINKp", "control", "nominal"] and not left else "FAIL")
      + " perturb: one nominal build for 4 perturbed runs and the control; project copies removed, logs/report/manifest/diff kept (%s; left %s)" % (" ".join(runs), left[:4]))
c = r["control"] or {}
print(("PASS" if c.get("flips") == [] and c.get("drift_n") == 0 and not c.get("stls_changed") else "FAIL")
      + " perturb: the control rebuild flips nothing (%s)" % c.get("summary"))
m = ps["CLR"]["runs"]["-"]
moved = all(x["stls_changed"] for p in ps.values() for x in p["runs"].values())
rek = any(l.startswith("rekeyed clearance: PRT_base to PRT_pan") for l in m["drift"])
print(("PASS" if moved and rek and "param CLR: 0.5 -> 0.3" in m["manifest"] and os.path.getsize(os.path.join(m["dir"], "diff.txt")) > 0 else "FAIL")
      + " perturb: every nudge moved geometry; CLR 0.5 -> 0.3 rekeys 'base to pan' (at -> just past the limit): drift, not a flip (%s)" % m["drift"][:1])
pin = [f for f in m["flips"] if f["class"] == "pinned" and "PRT_base to PRT_pan" in f["line"] and "wanted 0.45..None" in f["line"]]
print(("PASS" if pin and not ps["CLR"]["brittle"] and ps["CLR"]["brittle_with_pinned"] and r["brittle"] == [] and r["brittle_with_pinned"] == ["CLR"] else "FAIL")
      + " perturb: the overlay row (min 0.45, CLR 0.5) fails at CLR 0.3 as pinned: CLR not brittle, brittle_with_pinned (%s)" % [f["line"][:70] for f in m["flips"]])
md = open(os.path.join(d, "perturb.md")).read()
print(("PASS" if "| CLR | 0.5 | ±0.2 mm |" in md and "pinned only" in md and "Cost: nominal build" in md and r["rules"]["pinned"] and ps["CLR"]["band"] == 0.4 else "FAIL")
      + " perturb: the markdown has the CLR row ('pinned only') and the cost line; the JSON records the rules and the 0.4 mm band")
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/a.txt"
[ "$(srchash)" = "$before" ] && ok "perturb: every file in examples/demo-turret untouched (scratch copies only)" || bad "perturb: a file in examples/demo-turret changed"

# 3 negative control: CLR planted at 0.05 (--range: no band, nothing pinned) must fail the declared arm/barrel fit (min
# 0.10) and mark CLR brittle
CAD="$CAD" python3 -I "$P" "$T" --params-file build.py --build-args "--out {out}" --params '^CLR$' --range CLR=0.05:0.6 \
  --only interference --no-control --out "$PA/neg" > "$PA/neg.log" 2>&1
python3 -I - "$PA/neg/perturb.json" <<'PY' > "$PA/neg.txt" 2>&1 || echo "FAIL perturb: planted nudge: no JSON (see $PA/neg.log)" >> "$PA/neg.txt"
import json, re, sys
r = json.load(open(sys.argv[1]))
p = r["params"][0]
new = [f["line"] for f in p["runs"]["-"]["flips"] if f["change"] == "new" and f["status"] == "fail" and f["class"] == "design"]
hit = [l for l in new if re.search(r"clearance: PRT_arm_[LR] to PRT_barrel only 0\.05 mm", l)]
print(("PASS" if len(hit) == 2 and p["brittle"] and r["brittle"] == ["CLR"] else "FAIL")
      + " perturb: planted CLR 0.05: the arm/barrel fit fails on both arms as design flips, CLR brittle (%d new fails: %s)" % (len(new), [l[:60] for l in new]))
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$PA/neg.txt"
