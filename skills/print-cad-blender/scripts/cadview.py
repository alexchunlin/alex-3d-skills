"""cadview: a checked assembly as ONE offline HTML page: spin it, pose every joint, take it apart, click a finding.

    cad view model.blend [cadcheck.json] [-o out.html] [--pose PIV_tilt=30,pan=45] [--config checks.json] [--force]

Geometry comes from Blender's glTF exporter with Draco (14-bit positions), so the page is for looking: measure with
`cad q`. Joints pose with cadlib.joints' maths, the same as cadcheck and cadq: unlisted joints at home, couplings follow,
checks.json "carry" re-parents as in cadcheck. With a report, its fails and warns are listed and clickable: the named
objects light up, the sliders jump to the finding's pose and the camera frames it. A report that names objects or
joints the blend doesn't have is refused (exit 2); --force builds the page anyway with the mismatch in a red banner.
three.js, the Draco decoder and the fonts are inlined from viewer/vendor (viewer/vendor/build.sh made them): no
network when building or viewing. Prints `CADVIEW out.html <KB> ...` on success.
--selftest embeds Blender's matrix_world at a set of poses; open the page with #selftest to compare (tools/verify.d).
"""
import bpy, base64, datetime, fnmatch, gzip, json, os, re, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cadlib import joints as JT  # noqa: E402  (the pose maths cadcheck and cadq use)
from cadlib import export as EX  # noqa: E402  (the glTF exporter call, shared with export.write_glb)

VIEWER = os.path.join(HERE, "viewer")
VENDOR = os.path.join(VIEWER, "vendor")
ROLES = ("PRT", "BUY", "FST", "CAB")
ROLE_COLL = {"PRT": "printed", "BUY": "purchased", "FST": "fasteners", "CAB": "cables"}
DEFAULT_COLL = {"printed": "Printed", "purchased": "Purchased", "fasteners": "Fasteners", "cables": "Cables"}
ROLE_RGBA = {"PRT": (0.82, 0.80, 0.76, 1.0), "BUY": (0.22, 0.23, 0.25, 1.0), "FST": (0.55, 0.56, 0.58, 1.0),
             "CAB": (0.08, 0.08, 0.08, 1.0)}    # cadlib asm.PALETTE, for an object with no material
NAME_RE = re.compile(r"\b(?:PRT|BUY|FST|CAB|PIV)_[A-Za-z0-9_.\-]*[A-Za-z0-9]")   # a3 has FST_cap_L-1
NAME_KEYS = ("object", "a", "b", "part", "objects", "obstacles", "joint")
PROPS = ("orient", "supports", "infill", "material", "stl", "fst_kind")


def die(msg, code=2):
    print("cadview: " + msg, file=sys.stderr)
    sys.exit(code)


def parse_args(a):
    out = {"report": None, "out": None, "pose": "", "config": None, "force": False, "selftest": False}
    i = 0
    while i < len(a):
        x = a[i]
        if x in ("-o", "--out", "--pose", "--config"):
            if i + 1 >= len(a):
                die("%s needs a value" % x)
            out[{"-o": "out", "--out": "out"}.get(x, x[2:])] = a[i + 1]
            i += 2
            continue
        if x in ("--force", "--selftest"):
            out[x[2:]] = True
        elif x.startswith("-"):
            die("unknown flag %s (usage: cad view model.blend [cadcheck.json] -o out.html [--pose ..] [--config c.json] [--force])" % x)
        elif out["report"] is None:
            out["report"] = x
        else:
            die("one report only; got %s and %s" % (out["report"], x))
        i += 1
    return out


def parse_pose(s):
    """'tilt=-50' / 'pan=92.5, tilt=-52.5' / 'PIV_x=3' / 'home' -> {PIV_name: value}; a range 'a..b' (cadcheck's
    between_cell) gives its middle. None if it doesn't parse."""
    s = (s or "").strip()
    if s in ("", "home"):
        return {}
    out = {}
    for kv in re.split(r",\s*", s):
        m = re.fullmatch(r"([A-Za-z0-9_.]+)=(-?[\d.]+(?:e-?\d+)?)(?:\.\.(-?[\d.]+(?:e-?\d+)?))?", kv.strip())
        if not m:
            return None
        k = m[1] if m[1].startswith("PIV_") else "PIV_" + m[1]
        out[k] = float(m[2]) if m[3] is None else (float(m[2]) + float(m[3])) / 2
    return out


def names_in(f):
    """Object-like names a finding refers to: its name fields, then PRT_/BUY_/FST_/CAB_/PIV_ words in its message."""
    out = []
    for k in NAME_KEYS:
        v = f.get(k)
        for x in (v if isinstance(v, list) else list(v) if isinstance(v, dict) else [v]):
            if isinstance(x, str) and NAME_RE.fullmatch(x):
                out.append(x)
    msg = str(f.get("msg", ""))
    # not a glob from the config ("order" glob PRT_lid* matches none): cadcheck quotes those in its own warns
    out += [m[0] for m in NAME_RE.finditer(msg) if msg[m.end():m.end() + 1] not in ("*", "?", "[")]
    return list(dict.fromkeys(out))


def report_names(rep):
    """Object names anywhere in the report's check rows and assembly steps, so a clean report (no findings) from
    another model is caught too."""
    out = set()

    def walk(v, key=None):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str) and key in NAME_KEYS + ("name", "members") and NAME_RE.fullmatch(v):
            out.add(v)
    walk(rep.get("checks"))
    out.update(k for k in ((rep.get("assembly") or {}).get("step_of") or {}) if NAME_RE.fullmatch(k))
    return out


def pts(v):
    return isinstance(v, list) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v)


def findings(rep, objs, joints):
    """The report's fails and warns as compact records for the page, plus every name the blend doesn't have."""
    acc = (rep.get("summary") or {}).get("accepted_warns") or {}
    out, missing = [], {}
    for check, sec in (rep.get("checks") or {}).items():
        for f in (sec or {}).get("findings", []):
            if f.get("status") not in ("fail", "warn"):
                continue
            msg = str(f.get("msg", ""))
            pose_s = f.get("pose") or f.get("between_cell")
            if pose_s is None:
                m = re.search(r"\bat ((?:[A-Za-z0-9_]+=-?[\d.]+(?:, )?)+)", msg)
                pose_s = m[1].rstrip(", ") if m else None
            if isinstance(pose_s, dict):   # {"PIV_x": deg} or {"x": deg}
                pose = {(k if str(k).startswith("PIV_") else "PIV_" + str(k)): float(v) for k, v in pose_s.items()
                        if isinstance(v, (int, float))}
                pose_s = ", ".join("%s=%g" % (k.replace("PIV_", ""), v) for k, v in sorted(pose.items())) or "home"
            else:
                pose = parse_pose(pose_s) if isinstance(pose_s, str) else None
            names = names_in(f)
            miss = [n for n in names if n not in objs] + [j for j in (pose or {}) if j not in joints]
            for n in miss:
                missing.setdefault(n, []).append("%s: %s" % (check, msg[:80]))
            points = [f[k] for k in ("at", "center") if pts(f.get(k))]
            points += [w[1] for w in f.get("where") or [] if isinstance(w, list) and len(w) == 2 and pts(w[1])][:12]
            m = re.search(r"world \[(-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\]", msg)
            if m and not points:
                points.append([float(m[1]), float(m[2]), float(m[3])])
            box = f.get("region") if isinstance(f.get("region"), list) and len(f["region"]) == 2 and all(pts(c) for c in f["region"]) else None
            key = "%s: %s" % (check, msg)
            out.append({"check": check, "status": f["status"], "msg": msg, "names": [n for n in names if n in objs],
                        "missing": miss, "pose": pose, "pose_s": pose_s, "points": points, "box": box,
                        "accepted": acc.get(key) if f["status"] == "warn" and key in acc else None})
    out.sort(key=lambda r: (r["status"] != "fail", r["accepted"] is not None))
    return out, missing


def flat(M):
    return [round(float(M[i][j]), 7) for i in range(4) for j in range(4)]


def b64gz(data):
    return base64.b64encode(gzip.compress(data, 9, mtime=0)).decode()


def read(p, mode="r"):
    with open(os.path.join(VIEWER, p), mode) as f:
        return f.read()


def main():
    a = parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    blend = bpy.data.filepath
    if not blend:
        die("no blend loaded (cad view model.blend ...)")
    out = os.path.abspath(a["out"] or os.path.splitext(blend)[0] + ".html")
    rep, cfg = None, {}
    if a["report"]:
        try:
            with open(a["report"]) as f:
                rep = json.load(f)
        except (OSError, ValueError) as e:
            die("cannot read report %s: %s" % (a["report"], e))
        if not isinstance(rep, dict) or rep.get("tool") != "cadcheck" or not isinstance(rep.get("checks"), dict):
            die("%s is not a cadcheck report (cad check writes one)" % a["report"])
        cfg = dict(rep.get("config") or {})
    if a["config"]:
        try:
            with open(a["config"]) as f:
                c2 = json.load(f)
        except (OSError, ValueError) as e:
            die("cannot read --config %s: %s" % (a["config"], e))
        if not isinstance(c2, dict):
            die("--config %s is not a checks.json object" % a["config"])
        for k in ("joints", "couplings", "carry", "collections"):
            if k in c2:
                cfg[k] = c2[k]
    coll = dict(DEFAULT_COLL, **(cfg.get("collections") or {}))

    O = bpy.data.objects
    vl = bpy.context.view_layer
    in_coll = {}
    for r in ROLES:
        c = bpy.data.collections.get(coll[ROLE_COLL[r]])
        for o in (c.all_objects if c else []):
            in_coll.setdefault(o.name, r)

    def role(o):
        return in_coll.get(o.name) or (o.name[:3] if o.name[:4] in ("PRT_", "BUY_", "FST_", "CAB_") else None)
    view = [o for o in O if o.type == 'MESH' and role(o) and o.name in vl.objects]
    skipped = [o.name for o in O if o.type == 'MESH' and role(o) and o.name not in vl.objects]
    if not view:
        die("no PRT_/BUY_/FST_/CAB_ meshes in %s" % blend)
    objs = {o.name for o in O}

    # cadcheck's "carry": re-parent onto a joint keeping the home placement, so the page moves them as the checks did
    for g, piv in (cfg.get("carry") or {}).items():
        if piv not in O:
            die("carry %s -> %s: no such joint" % (g, piv))
        for o in [x for x in view if fnmatch.fnmatch(x.name, g)]:
            mw = o.matrix_world.copy()
            o.parent = O[piv]
            o.matrix_world = mw
    J, CP = JT.read(O, cfg)
    JT.apply(J, CP, {})
    vl.update()

    recs, missing = findings(rep, objs, J) if rep else ([], {})
    rnames = report_names(rep) if rep else set()
    for n in sorted(rnames - objs):
        missing.setdefault(n, []).append("check rows")
    named = rnames | {n for r in recs for n in r["names"] + r["missing"]}
    # Another model's report misses most names (demo on v2a7: 11 of 15, v2a7 on demo: 178). A model's own report can
    # name a few that aren't objects: a stale config name cadcheck warns about ("PRT_clip: not found"). Refuse the
    # first; flag the second in the banner and on each finding.
    wrong = missing and (len(missing) == len(named) or (len(missing) >= 3 and len(missing) >= 0.2 * len(named)))
    if wrong and not a["force"]:
        die("%s does not match %s: %d of the %d name(s) in the report are not in the blend: %s. Wrong report? Re-run cad "
            "check, or --force to build the page with the mismatch flagged" % (a["report"], os.path.basename(blend),
                                                                               len(missing), len(named), ", ".join(sorted(missing)[:10])))
    warn = []
    if missing:
        warn.append("%d of the %d name(s) in the report are not in this blend: %s" % (len(missing), len(named), ", ".join(sorted(missing)[:8])))
    if rep:
        try:
            t_rep = datetime.datetime.strptime(str(rep.get("generated") or ""), "%Y-%m-%d %H:%M:%S").timestamp()
            if os.path.getmtime(blend) > t_rep + 1:
                warn.append("the blend was saved after this report (%s): re-run cad check" % rep["generated"])
        except ValueError:
            warn.append("the report has no readable 'generated' time, so it can't be dated against the blend")
        if rep.get("blend") and os.path.basename(str(rep["blend"])) != os.path.basename(blend):
            warn.append("the report was made from %s; this page shows %s" % (rep["blend"], os.path.basename(blend)))
    for w in warn:
        print("cadview: warning: " + w)

    # glTF + Draco: the view objects, every joint, and their ancestors, in Blender's Z-up frame (cadlib.export.gltf,
    # the exporter settings model.glb uses too)
    tmp = tempfile.mkdtemp(prefix="cadview")
    try:
        glb_bytes = open(EX.gltf(os.path.join(tmp, "model.glb"), [o.name for o in view] + list(J), draco=True), "rb").read()
    except RuntimeError as e:
        die(str(e), 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    def rgba(o):
        m = next((s.material for s in o.material_slots if s.material), None)
        return [round(c, 3) for c in (m.diffuse_color if m else ROLE_RGBA[role(o)])]

    def body(o):
        p = o.parent
        while p is not None and not JT.is_joint(p):
            p = p.parent
        return p.name if p is not None else None
    model_objs = {}
    for o in view:
        props = {k: str(o[k]) for k in PROPS if k in o.keys()}
        model_objs[o.name] = {"role": role(o), "rgba": rgba(o), "body": body(o), "props": props}
    joints = []
    for n, s in J.items():
        e = O[n]
        joints.append({"name": n, "parent": e.parent.name if e.parent else None, "axis": s["axis"], "kind": s["kind"],
                       "lo": s["lo"], "hi": s["hi"], "home": s.get("home") or 0.0, "step": s.get("step"),
                       "continuous": bool(s.get("continuous")), "base_rot": list(s["base_rot"]), "base_loc": list(s["base_loc"]),
                       "loc": list(e.location), "rot": list(e.rotation_euler), "mode": e.rotation_mode, "scale": list(e.scale),
                       "basis": flat(e.matrix_basis), "mpi": flat(e.matrix_parent_inverse)})
    pose0 = parse_pose(a["pose"])
    if pose0 is None or any(j not in J for j in pose0):
        die("--pose %s: give joint=value pairs of %s" % (a["pose"], ", ".join(J) or "no joints"))
    summ = (rep or {}).get("summary") or {}
    title = os.path.splitext(os.path.basename(blend))[0]
    if title in ("model", "assembly", "demo"):   # say which one: verify_all unpacks every launcher to model.blend
        title = "%s · %s" % (os.path.basename(os.path.dirname(blend)), title)
    data = {"title": title, "blend": os.path.basename(blend),
            "saved": datetime.datetime.fromtimestamp(os.path.getmtime(blend)).strftime("%Y-%m-%d %H:%M"),
            "objects": model_objs, "joints": joints, "couplings": [[n, c["to"], float(c.get("ratio", 1.0)), float(c.get("offset", 0.0))] for n, c in CP.items()],
            "pose": pose0, "warn": warn, "skipped": skipped,
            "report": None if rep is None else {"file": os.path.basename(a["report"]), "generated": rep.get("generated"),
                                                "fails": summ.get("fails"), "warns": summ.get("warns"),
                                                "untriaged": summ.get("untriaged_warns"), "findings": recs,
                                                "overtravel": [cfg.get("overtravel_deg", 2.5), cfg.get("overtravel_mm", 1.0)]}}
    if a["selftest"]:
        data["expect"] = selftest_poses(J, CP, view, recs)
        JT.apply(J, CP, {})

    html = read("page.html")
    fonts = "".join("@font-face{font-family:'%s';font-weight:%s;font-display:block;src:url(data:font/woff2;base64,%s) format('woff2')}\n" % (
        fam, w, base64.b64encode(open(os.path.join(VENDOR, "fonts", "%s-%s.woff2" % (fam.replace(" ", ""), w)), "rb").read()).decode())
        for fam, w in (("Roboto", 400), ("Roboto", 500), ("Roboto Condensed", 500), ("Roboto Condensed", 700),
                       ("Roboto Mono", 400), ("Roboto Mono", 500)))
    blobs = {"cv-three": open(os.path.join(VENDOR, "ax3.min.js"), "rb").read(),
             "cv-draco-js": open(os.path.join(VENDOR, "draco_wasm_wrapper.js"), "rb").read(),
             "cv-draco-wasm": open(os.path.join(VENDOR, "draco_decoder.wasm"), "rb").read(), "cv-glb": glb_bytes}
    parts = {
        "<!--@FONTS-->": "<style>\n" + fonts + "</style>",
        # comments out: tokens.css's header shows a Google Fonts <link>, and the fonts are inlined above
        "<!--@TOKENS-->": "<style>\n" + re.sub(r"/\*.*?\*/", "", read("vendor/tokens.css"), flags=re.S) + "\n</style>",
        "<!--@DATA-->": '<script type="application/json" id="cv-data">' + json.dumps(data, separators=(",", ":")).replace("<", "\\u003c") + "</script>",
        "<!--@BLOBS-->": "\n".join('<script type="application/octet-stream" id="%s">%s</script>' % (k, b64gz(v)) for k, v in blobs.items()),
        # the licences travel with the page, which is the copy people pass around (MIT / Apache-2.0 / OFL ask for it)
        "<!--@LICENCES-->": "<!--\n" + "\n\n".join("==== %s\n%s" % (n, read("vendor/" + f).replace("--", "- -")) for n, f in (
            ("three.js 0.170.0", "LICENSE-three.txt"), ("Draco decoder (three.js glTF build)", "LICENSE-draco.txt"),
            ("Roboto, Roboto Condensed, Roboto Mono", "fonts/OFL.txt"), ("alex-style guide (tokens.css, ax-three.js)", "LICENSE-alex-style.txt"))) + "\n-->",
        "<!--@VIEW-->": "<script>\n" + read("view.js").replace("</script", "<\\/script") + "\n</script>",
    }
    for tag in parts:
        if html.count(tag) != 1:
            die("viewer/page.html: %s missing" % tag, 1)
    html = re.sub("|".join(map(re.escape, parts)), lambda m: parts[m[0]], html)   # one pass: no body is re-scanned
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(out) / 1024
    print("CADVIEW %s %.0f KB: %d objects, %d joints, %d findings (%d fail), geometry %.0f KB%s" % (
        out, kb, len(view), len(J), len(recs), sum(r["status"] == "fail" for r in recs), len(glb_bytes) / 1024,
        "; MISMATCH flagged (--force)" if wrong else "; %d name(s) not in the blend, flagged" % len(missing) if missing else ""))


def selftest_poses(J, CP, view, recs):
    """Blender's matrix_world of every view object at a spread of poses (cadlib.joints.apply, as cadcheck poses)."""
    drv = [n for n, s in J.items() if s["axis"] and n not in CP]
    poses = [{}]
    for n in drv:
        s = J[n]
        if s.get("continuous"):
            poses.append({n: 137.0})
        elif s["lo"] is not None:
            poses += [{n: float(s["lo"])}, {n: float(s["hi"])}]
    mix = {n: (0.37 * J[n]["lo"] + 0.63 * J[n]["hi"]) if J[n]["lo"] is not None else 61.0 for n in drv
           if J[n]["lo"] is not None or J[n].get("continuous")}
    poses.append(mix)
    poses += [r["pose"] for r in recs if r["pose"]][:3]
    out = []
    for p in poses:
        JT.apply(J, CP, p)
        out.append({"pose": p, "mw": {o.name: flat(o.matrix_world) for o in view}})
    return out


if __name__ == "__main__":
    main()
