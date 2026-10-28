# calcs, material allowables and per-part print settings (push-assist, docs/evidence-push-assist/loop-log.txt):
# hand calcs with no row (PA-A1-T10, PA-A3-T23) folded into stacks rows (PA-A6-T9), per-agent limits (PA-A6-T10), and
# 8 rounds of stress on solid sections with 3MFs carrying no print settings (PA-A8-T13).
# watch: @core skills/print-cad-blender/scripts/cadmat.py skills/print-cad-blender/scripts/cadrows.py
# watch: tools/verify.d/calcs_materials_cases.py tools/verify.d/calcs_materials_build.py
# Sourced by tools/verify_all.sh (uses $ROOT $V $BL, calls ok/bad). About 10 s: plain python3 cases, one build, one
# cad check --only calcs,stacks on it.
CM="$V/calcs"; mkdir -p "$CM"
CADW="${CAD:-$ROOT/skills/print-cad-blender/scripts/cad}"
python3 -I "$ROOT/tools/verify.d/calcs_materials_cases.py" "$ROOT" > "$CM/cases.txt" 2>&1 || echo "FAIL cadmat: cases crashed (see $CM/cases.txt)" >> "$CM/cases.txt"
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$CM/cases.txt"
# the build: manifest, 3MF and STL header carry the declared settings; asm.part refuses a bad spec
$CADW build "$ROOT/tools/verify.d/calcs_materials_build.py" -- --out "$CM/m" > "$CM/build.log" 2>&1
cat > "$CM/checks.json" <<'EOF'
{"calcs": [{"name": "F", "value": "=LOAD * 1.5", "unit": "N", "why": "1.5 x the rated load"},
           {"name": "leaf_mpa", "value": "=F * ARM / z_eff(B, H, part='PRT_leaf_0')", "max": "=mat('PRT_leaf_0', 'in_mpa')", "unit": "MPa"},
           {"name": "base_mpa", "value": "=F * ARM / z_eff(40, 10, part='PRT_base')", "max": "=mat('PRT_base', 'in_mpa')", "unit": "MPa"},
           {"name": "broken", "value": "=NOPE * 2"},
           {"name": "typo", "value": 1, "maxx": 2}],
 "stacks": [{"name": "stress as a stack", "limit": 15, "terms": [{"what": "sigma", "tol": "=LOAD / 10"}]},
            {"name": "real stack", "limit": 0.3, "terms": [{"what": "a", "tol": 0.1}, {"what": "b", "tol": 0.1}]}]}
EOF
nice -n 10 "$BL" -b --factory-startup "$CM/m/m.blend" --python "$ROOT/skills/print-cad-blender/scripts/cadcheck.py" -- \
  --config "$CM/checks.json" --only calcs,stacks --out "$CM/cadcheck.json" > "$CM/check.log" 2>&1
python3 -I "$ROOT/skills/print-cad-blender/scripts/cadrows.py" "$CM/cadcheck.json" --check calcs > "$CM/rows.txt" 2>&1
python3 -I - "$ROOT" "$CM" <<'PY' > "$CM/asserts.txt" 2>&1
import json, os, re, struct, sys, zipfile
root, d = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(root, "skills", "print-cad-blender", "scripts"))
import cadmat as M
def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "calcs/print settings: " + msg)
log = open(os.path.join(d, "build.log")).read()
say("CM_BUILT" in log, "the build ran (see build.log)")
say("CM_REFUSED material" in log and "not in cadmat.MATERIALS" in log and "CM_REFUSED walls" in log and "CM_ACCEPTED" not in log,
    "asm.part refuses material ABS and walls=2.5")
try:
    man = json.load(open(os.path.join(d, "m", "manifest.json")))["parts"]
except Exception as e:
    man = {}
lp, bp = man.get("PRT_leaf_0", {}).get("print"), man.get("PRT_base", {}).get("print")
say(lp == {"material": "PETG", "walls": 3, "infill": 40, "layer_h": 0.16, "line_w": 0.42, "shells": 3, "defaulted": ["line_w", "shells"]},
    "manifest print block of a part with settings: declared values, the rest defaulted and named (%s)" % lp)
say(bp is not None and bp["defaulted"] == list(M.PRINT_KEYS) and bp["walls"] == 2 and bp["infill"] == 15,
    "manifest print block of a part with none: slicer defaults, all named as defaulted")
stl = os.path.join(d, "m", "stl")
try:
    z = zipfile.ZipFile(os.path.join(stl, "leaf.3mf"))
    model, cfg = z.read("3D/3dmodel.model").decode(), z.read("Metadata/model_settings.config").decode()
    zb = zipfile.ZipFile(os.path.join(stl, "base.3mf"))
    bmodel, bcfg = zb.read("3D/3dmodel.model").decode(), zb.read("Metadata/model_settings.config").decode()
except Exception as e:
    model = cfg = bmodel = bcfg = ""
    say(False, "3MFs readable (%s)" % e)
md = dict(re.findall(r'<metadata name="cad:(\w+)"[^>]*>([^<]*)</metadata>', model))
say(md == {"material": "PETG", "walls": "3", "infill": "40", "layer_h": "0.16"}, "3MF core per-object metadata carries the declared settings (%s)" % md)
keys = dict(re.findall(r'<metadata key="(\w+)" value="([^"]*)"/>', cfg))
say(keys.get("wall_loops") == "3" and keys.get("sparse_infill_density") == "40%" and keys.get("layer_height") == "0.16" and keys.get("name") == "leaf",
    "3MF Bambu/Orca per-object keys: wall_loops 3, sparse_infill_density 40%%, layer_height 0.16 (%s)" % keys)
nstl = struct.unpack("<I", open(os.path.join(stl, "leaf.stl"), "rb").read()[80:84])[0]
nt, nv = len(re.findall(r"<triangle ", model)), len(re.findall(r"<vertex ", model))
say(model.count("<item ") == 2 and nt == nstl == 12 and nv == 8, "3MF mesh is the STL's (%d triangles, %d vertices) with one build item per copy (2)" % (nt, nv))
say("<metadatagroup>" not in bmodel and not re.search(r'key="(wall_loops|sparse_infill_density)"', bcfg),
    "negative control: a part with no settings writes none (the slicer's process preset applies)")
hdr = open(os.path.join(stl, "leaf.stl"), "rb").read(80)
say(b"PETG walls=3 infill=40% layer_h=0.16" in hdr and not hdr.startswith(b"solid"), "STL header carries the settings as text: %r" % hdr.rstrip())
try:
    rep = json.load(open(os.path.join(d, "cadcheck.json")))
    s = rep["summary"]
except Exception as e:
    rep, s = {}, {"fail_list": [], "warn_list": [], "config_warns": []}
    say(False, "cad check wrote a report (%s)" % e)
fl, wl, cw = s["fail_list"], s["warn_list"], " | ".join(s["config_warns"])
rows = {r["name"]: r for r in rep.get("checks", {}).get("calcs", {}).get("rows", [])}
lv = 75.0 * 20 / M.section(10, 4, walls=3, infill=40, layer_h=0.16)["Z"]
say(any(re.match(r"calcs: leaf_mpa: [\d.]+ MPa > max 23\.5$", x) for x in fl) and abs(rows.get("leaf_mpa", {}).get("value", 0) - lv) < 1e-6,
    "a calc on the part's printed section fails its max from the part's material (%.1f MPa > 23.5)" % lv)
say(rows.get("base_mpa", {}).get("result") == "pass" and not any("base_mpa" in x for x in fl), "negative control: a calc within its max passes")
say(any(x.startswith("config: calcs[3] 'broken': expression '=NOPE * 2' failed (NameError") and "row skipped" in x for x in fl) and "broken" not in rows,
    "a failed expression is a config fail naming the row, and the row is skipped")
dw = [x for x in wl if "not declared" in x]
say(len(dw) == 1 and dw[0].startswith("calcs: PRT_base: calc 'base_mpa'") and "material/walls/infill are not declared" in dw[0],
    "a calc on a part with no print spec warns once, naming the part and the keys; PRT_leaf_0 (declared) does not")
say("unknown key 'maxx', ignored (did you mean 'max'?)" in cw, "an unknown key on a calcs row is a config warn")
say("stacks[0] (stress as a stack): one term from an =expr" in cw and "stacks[1]" not in cw,
    "a one-term =expr stack is a config warn pointing at calcs; a real two-term stack is not")
say(len(fl) == 2 and "Traceback" not in open(os.path.join(d, "check.log")).read(), "exactly the two fails, and no traceback (%s)" % fl)
rl = open(os.path.join(d, "rows.txt")).read()
say(re.search(r"^calcs\s+leaf_mpa\s.*value=[\d.]+  unit=MPa  max=23\.5  result=fail", rl, re.M) is not None, "cad rows prints the calc rows")
PY
while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; *) bad "calcs/print settings: $st $msg" ;; esac; done < "$CM/asserts.txt"
