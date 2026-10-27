"""cadcfg (checks.json hygiene) without Blender: python3 -I cadcfg_cases.py ROOT [REPORT ...]. Prints PASS/FAIL lines.

The schema and the doc agree both ways; the push-assist cases (PA-A4-T6 typo'd keys, PA-A4-T10 substring accepts and
--only stale accepts) and their negative controls; and, on verify's own v2 designer reports when given, the suggested
structured accepts cover exactly what the old substring accepts covered.
"""
import json, os, re, sys

ROOT = sys.argv[1]
S = os.path.join(ROOT, "skills/print-cad-blender/scripts")
sys.path.insert(0, S)
import cadcfg as C  # noqa: E402

CC = os.path.join(S, "cadcheck.py")
D, R, N = C.literal(CC, "DEFAULTS"), C.literal(CC, "CONFIG_ROWS"), C.literal(CC, "CONFIG_NAMED")
DEF = dict(D, printcheck=C.literal(os.path.join(S, "printcheck.py"), "DEFAULTS"))


def want(name, cond, detail=""):
    print("%s cadcfg: %s%s" % ("PASS" if cond else "FAIL", name, "" if cond or not detail else " (%s)" % detail))


def unknown(cfg):
    return C.unknown_keys(cfg, DEF, R, N)


# 1 the doc's jsonc example reads with no unknown key, and shows every key cadcheck knows in its own section
doc = open(os.path.join(ROOT, "skills/print-cad-blender/reference/checks-config.md")).read()
block = re.search(r"```jsonc\n(.*?)```", doc, re.S).group(1)
want("the jsonc stripper keeps // inside a string", json.loads(C.strip_jsonc('{"a": "x//y", // note\n "b": [1,],}')) == {"a": "x//y", "b": [1]})


def merge(pairs):      # the example repeats "fasteners"
    out = {}
    for k, v in pairs:
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


ex = json.loads(C.strip_jsonc(block), object_pairs_hook=merge)
u = unknown(ex)
want("checks-config.md example has no key cadcheck doesn't read", not u, u)
seen = {"top level": set(ex)}


def walk(spec, rws):
    for r in rws:
        seen.setdefault(spec, set()).update(r)
        for k, sub in r.items():
            if spec + "." + k in R:
                walk(spec + "." + k, [x for x in (sub if isinstance(sub, list) else [sub]) if isinstance(x, dict)])


for sec, v in ex.items():
    if sec in R and isinstance(v, list):
        walk(sec, [r for r in v if isinstance(r, dict)])
    elif sec in R and sec in N:
        walk(sec, [r for r in v.values() if isinstance(r, dict)])
    elif isinstance(v, dict) and sec not in N:
        seen.setdefault(sec, set()).update(v)
need = {"top level": set(D)}
need.update({sec: set(v) for sec, v in D.items() if isinstance(v, dict) and sec not in N})
for sec, fs in R.items():
    need.setdefault(sec, set()).update(fs)
miss = {sec: sorted(fs - seen.get(sec, set())) for sec, fs in need.items() if fs - seen.get(sec, set())}
want("the doc example shows every DEFAULTS key and CONFIG_ROWS field in its own section (%d sections)" % len(need), not miss, miss)
# every row field is one cadcheck (or cadlib.joints) reads: the schema can't list a key nothing uses
code = open(CC).read()
code = code[:code.index("CONFIG_ROWS = {")] + code[code.index("CONFIG_NAMED = ["):] + \
    open(os.path.join(S, "cadlib/joints.py")).read() + open(os.path.join(S, "cadcfg.py")).read()
unread = sorted({f for v in R.values() for f in v if not re.search(r"[\[(]\"%s\"[\]),]" % f, code)} - {"what"})
want("every CONFIG_ROWS field is read by cadcheck, cadcfg or cadlib.joints (stacks terms' \"what\" is a label)", not unread, unread)

# 2 typo'd keys warn with the closest key (PA-A4-T6: "flexure" for "flexures" passed with nothing checked)
typo = {"flexure": [{"part": "PRT_leaf"}], "min_wal": 1.2, "_about": "a note",
        "slide_out": [{"name": "gate stop", "object": "PRT_g", "dir": [1, 0, 0], "dist": 5, "blockd_by": ["PRT_a"]}],
        "stacks": [{"name": "s", "limit": 1, "terms": [{"what": "a", "tole": 0.1}]}],
        "fasteners": {"driver_radius": 3, "captive": {"FST_x": "why"}}, "printcheck": {"bridge_mm": 30},
        "joints": {"PIV_a": {"axis": "X", "low": 0, "_why": "note"}}, "masses_g": {"BUY_anything": 3},
        "distances": [{"a": "PRT_a", "b": "PRT_b", "ray": {"origin": [0, 0, 0], "dirr": [0, 0, 1]}}]}
got = {(w.split(" (")[0], k, c) for w, k, c in unknown(typo)}
exp = {("top level", "flexure", "flexures"), ("top level", "min_wal", "min_wall"), ("slide_out[0]", "blockd_by", "blocked_by"),
       ("stacks[0]", "tole", "tol"), ("fasteners", "driver_radius", "driver_r"), ("printcheck", "bridge_mm", "bridge_warn_mm"),
       ("joints.PIV_a", "low", "lo"), ("distances[0]", "dirr", "dir")}
want("typo'd keys at top level, in rows, sub-rows, dict sections and joints warn with the closest key", got == exp,
     "extra %s missing %s" % (sorted(got - exp), sorted(exp - got)))
m = C.unknown_msgs("checks.json", typo, DEF, R, N)
want("the message names file, row and suggestion",
     "checks.json slide_out[0] (gate stop): unknown key 'blockd_by', ignored (did you mean 'blocked_by'?)" in m, m[:3])
# negative control: every config in the repo (the 10 archived designs, overlays, review rows, examples, template)
cfgs = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(ROOT, "examples")) for f in fs
              if f.endswith(".json") and not re.search(r"cadcheck|manifest", f)) + \
    [os.path.join(S, "../templates/project/checks.json")]
noisy = {os.path.relpath(p, ROOT): unknown(json.load(open(p))) for p in cfgs}
noisy = {k: v for k, v in noisy.items() if v}
want("no unknown key in the repo's %d configs (archived designs, overlays, examples, template)" % len(cfgs), not noisy, noisy)
want("--only typo warns", C.only_problems({"flexure", "stacks"}, ["stacks", "flexures"]) ==
     ["--only: 'flexure' is not a check, nothing ran for it (did you mean 'flexures'?)"])

# 3 accepts: check + kind + object, not substring (PA-A4-T10b: "PRT_tray_L: " accepted every warn on the tray)
W = ["parts: PRT_tray_L: 4 wall samples < 1.6 mm (min 1.02)",
     "parts: PRT_tray_L: 161 mm2 of sloped overhang steeper than 45 deg, supports=no",
     "parts: PRT_tray_L (model): a 26.7 mm bridge at z 27.4 (print [1, 2, 27.4], world [3, 4, 5])",
     "parts: PRT_tray_LR: 9 wall samples < 1.6 mm (min 1.2)",
     "clearance: PRT_hood to FST_nipstop 0.76 mm at hood=2.83",
     "fasteners: FST_M5_bolt_4 needs a 98 mm+ bit/extension (head 88 mm below open space)",
     "build: the model is older than parts/a.py",
     "fasteners: FST_Jack_swivel_nut has no bolt on its axis"]
old = {"match": "PRT_tray_L: ", "why": "w"}
new = {"check": "parts", "object": "PRT_tray_L", "kind": "wall samples", "any": True, "why": "w"}
TM = C.templates(CC)
acc_of = lambda a: [w for w in W if C.accepts(a, w)]
want("old substring accept still accepts (backward compatible): 'PRT_tray_L: ' takes 2 warns of 2 kinds", acc_of(old) == W[:2], acc_of(old))
want("structured accept takes only its kind on its object (not PRT_tray_LR, not the overhang or the bridge)", acc_of(new) == W[:1])
want("object is a whole token, globs ([..] too) work, a list needs all",
     not C.accepts({"check": "parts", "object": "PRT_tray", "kind": "wall samples", "any": True}, W[0])
     and C.accepts({"check": "parts", "object": "PRT_tray_*", "kind": "wall samples", "any": True}, W[3])
     and C.accepts({"check": "parts", "object": "PRT_tray_[LR]", "kind": "wall samples", "any": True}, W[0])
     and not C.accepts({"check": "parts", "object": "PRT_tray_[XY]", "kind": "wall samples", "any": True}, W[0])
     and C.accepts({"check": "clearance", "object": ["PRT_hood", "FST_nipstop"], "kind": "mm at", "any": True}, W[4])
     and not C.accepts({"check": "clearance", "object": ["PRT_hood", "FST_other"], "kind": "mm at", "any": True}, W[4]))
want("wrong check or missing kind accepts nothing",
     not C.accepts({"check": "clearance", "object": "PRT_tray_L", "kind": "wall samples", "any": True}, W[0])
     and not C.accepts({"check": "parts", "object": "PRT_tray_L", "any": True}, W[0]))
# review case 1: a structured accept that drops the number hid a worse warn (demo base wall 2.4 -> 1.2, min 2.21 -> 0.46)
ok_w = "parts: PRT_base: 427 wall samples < 3.0 mm (min 2.21)"
thin = "parts: PRT_base: 512 wall samples < 3.0 mm (min 0.46)"
leg = {"match": "PRT_base: 427 wall samples < 3.0 mm (min 2.21)", "why": "ribs"}
sg = C.suggest(leg, [ok_w], TM)
want("a suggestion keeps a pinned number in \"match\": it takes the accepted warn, not the worse one",
     sg == [{"check": "parts", "kind": "wall samples", "object": "PRT_base", "match": leg["match"], "why": "ribs"}]
     and C.accepts(sg[0], ok_w) and not C.accepts(sg[0], thin), sg)
bare = {"check": "parts", "object": "PRT_base", "kind": "wall samples"}
t = C.triage([bare], [thin], None)
want("a structured accept without match or any takes no warn with a measured value, and says so (config warn)",
     thin in t["untriaged"] and len(t["unpinned"]) == 1 and "\"any\": true" in t["unpinned"][0], t["unpinned"])
want("\"any\": true takes any value; a warn with no number needs neither",
     C.accepts(dict(bare, any=True), thin) and C.accepts({"check": "fasteners", "object": "FST_Jack_swivel_nut", "kind": "has no bolt"}, W[7]))
# review case 2: kind inside an object name
want("kind matches whole words outside object names (\"bridge\" is not in PRT_bridge_plate's wall warn)",
     not C.accepts({"check": "parts", "object": "PRT_bridge_plate", "kind": "bridge", "any": True},
                   "parts: PRT_bridge_plate: 4 wall samples < 1.6 mm (min 1.02)")
     and C.accepts({"check": "parts", "object": "PRT_bridge_plate", "kind": "bridge", "any": True},
                   "parts: PRT_bridge_plate (model): a 30.1 mm bridge at z 4.0 (print [0, 0, 4], world [0, 0, 4])"))
pr = C.accept_problems([{"check": "part", "kind": "x", "object": "PRT_a"}, {"check": "parts", "object": "PRT_a"}, {"match": ""},
                        {"check": "parts", "kind": "x"}, {"check": "parts", "kind": "x", "any": True}], ["parts", "clearance"])
want("malformed accepts are config warns: no such check, no kind, empty match, no object without any",
     len(pr) == 4 and "did you mean 'parts'" in pr[0] and "no \"object\"" in pr[3], pr)
sug = C.suggest(old, W, TM)
want("suggestions for 'PRT_tray_L: ' are one structured accept per kind, with \"any\" where it took any value",
     [(s["check"], s["object"], s["kind"], s.get("any")) for s in sug] ==
     [("parts", "PRT_tray_L", "wall samples", True), ("parts", "PRT_tray_L", "sloped overhang steeper than", True)], sug)
want("suggested kinds: bridge, clearance, bit", [C.kind_of(w.split(": ")[0], w.split(": ", 1)[1], TM) for w in W[2:6]] ==
     ["bridge", "wall samples", "mm at", "bit/extension"])
want("a partial object name in an old accept becomes a glob",
     C.suggest({"match": "x CAB_Amp_to_ESP32_"}, ["interference: cable BUY_amp_L x CAB_Amp_to_ESP32_L overlap 5.2 mm3 (route through solid?)"],
               TM)[0]["object"] == "CAB_Amp_to_ESP32_*")

# 4 triage: stale and not evaluated (PA-A4-T10a: under --only no stale accept was ever reported)
acc = [new, {"check": "parts", "kind": "island", "object": "PRT_x", "why": "fixed?"}, {"check": "stacks", "kind": "worst case", "any": True},
       {"match": "head stands"}, {"match": "older than"}]
t = C.triage(acc, W, {"parts", "config", "build"})
want("--only: accepted, stale (check ran, matched nothing), not evaluated (check did not run; old form unmatched)",
     list(t["accepted"]) == W[:1] and t["stale"] == ["parts: PRT_x island"] and
     t["not_evaluated"] == ["stacks: worst case", "head stands", "older than"], t)
want("a stale-model warn is never accepted", W[6] in t["untriaged"] and W[6] not in t["accepted"])
t = C.triage(acc, W, None)
want("full run: every accept that matched nothing is stale, the old form too",
     t["stale"] == ["parts: PRT_x island", "stacks: worst case", "head stands", "older than"] and not t["not_evaluated"], t)
want("the old form gets one deprecation warn naming a wide accept",
     "2 of 3 entries" in (C.legacy_msg(C.triage([old, {"match": "needs a"}, new], W, None)["legacy"], 3, W, TM) or "")
     and "'PRT_tray_L: '" in C.legacy_msg(C.triage([old, new], W, None)["legacy"], 2, W, TM))

# nested keys (review case 4): expect.angle and ray.sweep rows are checked too
nt = {"drop_tests": [{"name": "d", "emit": {}, "expect": {"angle": {"center": "PIV_a", "rnage": [0, 10]}}}],
      "distances": [{"a": "PRT_a", "b": "PRT_b", "ray": {"origin": [0, 0, 0], "dir": [0, 0, 1], "sweep": {"form": 0, "to": 9}}}]}
got = {(k, c) for _, k, c in unknown(nt)}
want("typo'd keys inside expect.angle ('rnage') and ray.sweep ('form') warn", got == {("rnage", "range"), ("form", "from")}, got)

# 5 on verify's own designer reports: the suggestions accept exactly the warns the old accepts did
for rep, cfg in zip(sys.argv[2::2], sys.argv[3::2]):
    if not (os.path.exists(rep) and os.path.exists(cfg)):
        continue
    s = json.load(open(rep))["summary"]
    warns = list(s["warn_list"]) + list(s["accepted_warns"])
    leg = [a for a in json.load(open(cfg)).get("accepted_warns", []) if not C.structured(a)]
    sugg = [u for x in s.get("accept_suggestions", []) for u in x["use"]]
    before = {w for w in warns if any(C.accepts(a, w) for a in leg) and not w.startswith("build: ")}
    after = {w for w in warns if any(C.accepts(a, w) for a in sugg)}
    name = os.path.basename(os.path.dirname(rep))
    want("%s: %d suggested structured accepts take the same %d warns as the %d old ones (config_warns %d, none an unknown key)" % (
        name, len(sugg), len(before), len(leg), len(s.get("config_warns", []))),
        before == after and set(s["accepted_warns"]) == before and not any("unknown key" in x for x in s.get("config_warns", [])),
        "only old: %s; only new: %s" % (sorted(before - after)[:3], sorted(after - before)[:3]))
