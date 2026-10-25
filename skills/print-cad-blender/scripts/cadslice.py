"""cad slice: confirm printability with a real slicer, safely. Plain python3 (stdlib).

    cad slice --detect                          slicers found, version, usable / unusable / untested and why
    cad slice STL_DIR|part.stl ... [--out DIR] [--slicer NAME] [--only GLOB] [--no-support-pass]
    cad slice --probe NAME                      run NAME's one smoke test now (it also runs on first use)
    cad slice --reprobe NAME                    for the user, after updating a slicer: forget its unusable mark

Each part is sliced twice with the slicer's own P1S / PLA 0.20 mm settings: supports off (time, filament, the slicer's
warnings) and supports on, auto (does the slicer put support under it, and at which heights). Results go to
DIR/slice.json (default: next to the STLs) and one line per part. When no slicer is usable it says so and
`cad printcheck` (the layer check) is the authority.

Safety (user rules, docs/HARVEST_BRIEF.md "Printer safety, revised"):
  - Nothing is ever sent to a printer and no network is used: every slicer run is inside `sandbox-exec` with
    (deny network*), and no command line names a printer, host or upload option.
  - The user's slicer settings are never read or written: HOME and CFFIXED_USER_HOME point at a fresh temp dir, PrusaSlicer
    and OrcaSlicer get --datadir there, and the sandbox denies reads and writes of ~/Library/Application Support/
    {BambuStudio,OrcaSlicer,PrusaSlicer} and their preferences; writes are allowed only in the temp dir.
  - No crash dialogs: the slicer runs under guarded_run.py, which receives the crash on its own Mach exception port and
    kills the process before macOS's crash reporter sees it.
  - One smoke test per slicer version. A crash, hang or failed smoke test marks it unusable in the local cache
    (.cad-slice-cache.json next to this skill, git-ignored) and it is never run again automatically; known.json
    (committed) carries verdicts already measured, so a new checkout does not re-test a slicer known to crash.
Profiles: PrusaSlicer uses profiles/prusa_p1s_pla.ini (vendored here); Bambu Studio and OrcaSlicer get their bundled
BBL system presets flattened into the temp dir (read from the .app, never from the user's folders).

Why: v2 shipped "supports: no" on parts that need support (FINDINGS "v2 post-freeze"), and an agent that ran the Bambu
Studio CLI with hand-built profiles crashed it 10 times on 2026-10-24, each one a crash dialog for the user.
"""
import fnmatch, glob, json, os, plistlib, re, shutil, struct, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import guarded_run as GR   # noqa: E402

KNOWN = os.path.join(SKILL, "slicers", "known.json")
CACHE = os.environ.get("CAD_SLICE_CACHE") or os.path.join(SKILL, ".cad-slice-cache.json")
REAL_HOME = os.path.realpath(os.path.expanduser("~"))
USER_DIRS = ["Library/Application Support/BambuStudio", "Library/Application Support/OrcaSlicer",
             "Library/Application Support/PrusaSlicer", "Library/Application Support/PrusaSlicer-alpha",
             "Library/Caches/com.bambulab.bambu-studio", "Library/Caches/com.softfever3d.orca-slicer"]
SLICERS = [   # preference order: PrusaSlicer's CLI is the long-standing headless one
    {"name": "prusaslicer", "kind": "prusa", "apps": ["PrusaSlicer.app", "Original Prusa Drivers/PrusaSlicer.app"],
     "ids": ("com.prusa3d",), "path": ["prusa-slicer"]},
    {"name": "orcaslicer", "kind": "orca", "apps": ["OrcaSlicer.app"], "ids": ("com.softfever3d",), "path": ["orca-slicer"]},
    {"name": "bambustudio", "kind": "bambu", "apps": ["BambuStudio.app"], "ids": ("com.bambulab.bambu-studio",), "path": []},
]
TIMEOUT = 300.0


# ------------------------------------------------------------------ detection and verdicts

def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def detect():
    """Installed slicers (by bundle id, so the Orca agent IDE, com.stablyai.orca, is not taken for OrcaSlicer).
    CAD_SLICE_SLICERS (a JSON list of {name, kind, exe, version}) replaces detection, for tests."""
    if os.environ.get("CAD_SLICE_SLICERS"):
        return [dict(s, key="%s@%s" % (s["name"], s.get("version", "test")), source="CAD_SLICE_SLICERS")
                for s in json.loads(os.environ["CAD_SLICE_SLICERS"])]
    found = []
    for s in SLICERS:
        for root in ("/Applications", os.path.join(REAL_HOME, "Applications")):
            for app in s["apps"]:
                ap = os.path.join(root, app)
                info = _load_plist(os.path.join(ap, "Contents", "Info.plist"))
                if not info or not str(info.get("CFBundleIdentifier", "")).startswith(s["ids"]):
                    continue
                exe = os.path.join(ap, "Contents", "MacOS", info.get("CFBundleExecutable", ""))
                if os.path.isfile(exe):
                    ver = str(info.get("CFBundleShortVersionString", "?"))
                    found.append({"name": s["name"], "kind": s["kind"], "exe": exe, "app": ap, "version": ver,
                                  "bundle_id": info["CFBundleIdentifier"], "key": "%s@%s" % (info["CFBundleIdentifier"], ver)})
        if not any(f["name"] == s["name"] for f in found):
            for cmd in s["path"]:
                p = shutil.which(cmd)
                if p:
                    found.append({"name": s["name"], "kind": s["kind"], "exe": os.path.realpath(p), "app": None, "version": "?",
                                  "bundle_id": cmd, "key": "%s@%s" % (cmd, int(os.path.getmtime(p)))})
    return found


def _load_plist(p):
    try:
        with open(p, "rb") as f:
            return plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None


def verdict(s):
    """(status, why) from known.json, then the local cache: usable | unusable | untested."""
    for src, d in (("known.json", _load(KNOWN)), ("local cache", _load(CACHE))):
        v = d.get(s["key"])
        if v:
            return v["status"], "%s (%s, %s)" % (v.get("why", ""), src, v.get("date", "?"))
    return "untested", "no smoke test yet"


def _record(s, status, why, evidence=None):
    d = _load(CACHE)
    d[s["key"]] = {"status": status, "why": why, "date": time.strftime("%Y-%m-%d %H:%M"), "exe": s["exe"], "evidence": evidence}
    with open(CACHE + ".tmp", "w") as f:
        json.dump(d, f, indent=1)
    os.replace(CACHE + ".tmp", CACHE)


# ------------------------------------------------------------------ isolation

def workspace():
    w = os.path.realpath(tempfile.mkdtemp(prefix="cad-slice-"))
    for d in ("home", "data", "tmp", "out", "cfg"):
        os.makedirs(os.path.join(w, d))
    return w


def sandbox_profile(work):
    q = lambda p: '"%s"' % p.replace("\\", "\\\\").replace('"', '\\"')
    deny = " ".join("(subpath %s)" % q(os.path.join(REAL_HOME, d)) for d in USER_DIRS)
    prefs = '(regex #"^%s/Library/Preferences/com\\.(bambulab|softfever3d|prusa3d)")' % re.escape(REAL_HOME)
    return ("(version 1)\n(allow default)\n(deny network*)\n"
            "(deny file-read* file-write* %s %s)\n"
            "(deny file-write*)\n"
            "(allow file-write* (subpath %s) (literal \"/dev/null\") (literal \"/dev/stdout\") (literal \"/dev/stderr\") "
            "(literal \"/dev/tty\") (literal \"/dev/dtracehelper\") (regex #\"^/dev/fd/\"))\n") % (deny, prefs, q(work))


def env_for(work):
    h = os.path.join(work, "home")
    return {"HOME": h, "CFFIXED_USER_HOME": h, "TMPDIR": os.path.join(work, "tmp") + "/", "PATH": "/usr/bin:/bin",
            "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}


# ------------------------------------------------------------------ profiles and command lines

def bbl_preset(app, kind, name, seen=None):
    """A BBL system preset from the slicer's own bundle with its inherits chain resolved (later keys win)."""
    base = os.path.join(app, "Contents", "Resources", "profiles", "BBL", kind)
    with open(os.path.join(base, name + ".json")) as f:
        d = json.load(f)
    par = d.get("inherits")
    if par and par != name and (seen is None or par not in seen):
        b = bbl_preset(app, kind, par, (seen or set()) | {name})
        b.update(d)
        d = b
    return d


def bbl_profiles(s, work, supports):
    m = bbl_preset(s["app"], "machine", "Bambu Lab P1S 0.4 nozzle")
    p = bbl_preset(s["app"], "process", "0.20mm Standard @BBL X1C")
    f = bbl_preset(s["app"], "filament", "Bambu PLA Basic @BBL X1C")
    for d, key, name in ((m, "printer_settings_id", "Bambu Lab P1S 0.4 nozzle"), (p, "print_settings_id", "0.20mm Standard @BBL X1C"),
                         (f, "filament_settings_id", "Bambu PLA Basic @BBL X1C")):
        d.pop("inherits", None)
        d["from"] = "system"
        d[key] = [name] if key == "filament_settings_id" else name
    if "nozzle_volume_type" not in m and "default_nozzle_volume_type" in m:
        m["nozzle_volume_type"] = m["default_nozzle_volume_type"]
    p["enable_support"] = "1" if supports else "0"
    if supports:
        p["support_type"] = "normal(auto)"
    paths = []
    for d, n in ((m, "machine"), (p, "process"), (f, "filament")):
        fp = os.path.join(work, "cfg", "%s%s.json" % (n, "_sup" if supports else ""))
        with open(fp, "w") as fh:
            json.dump(d, fh, indent=1)
        paths.append(fp)
    return paths


def command(s, work, stl, supports, outdir):
    """The slicer command line. No option here names a printer, a host, an upload or a network service."""
    if s["kind"] == "prusa":
        ini = os.path.join(SKILL, "slicers", "profiles", "prusa_p1s_pla.ini")
        return [s["exe"], "--datadir", os.path.join(work, "data"), "--load", ini,
                "--support-material" if supports else "--no-support-material", "--export-gcode",
                "--output", os.path.join(outdir, "out.gcode"), stl]
    if s["kind"] == "test":
        return [s["exe"], "--supports" if supports else "--no-supports", "--out", outdir, stl]
    m, p, f = bbl_profiles(s, work, supports)
    cmd = [s["exe"]]
    if s["kind"] == "orca":
        cmd += ["--datadir", os.path.join(work, "data")]
    return cmd + ["--orient", "0", "--arrange", "1", "--load-settings", "%s;%s" % (m, p), "--load-filaments", f,
                  "--slice", "0", "--outputdir", outdir, stl]


# ------------------------------------------------------------------ output parsing

def _hms(t):
    t = t.strip()
    if re.fullmatch(r"[\d.]+", t):
        return float(t)
    sec = 0.0
    for v, u in re.findall(r"([\d.]+)\s*([dhms])", t):
        sec += float(v) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u]
    return sec


def parse_gcode(text):
    """Estimates and features from a G-code file (PrusaSlicer, OrcaSlicer and Bambu Studio header/comment styles)."""
    r = {"time_s": None, "filament_g": None, "filament_mm": None, "support_layers": [], "layers": 0}
    for pat, key, conv in ((r"estimated printing time \(normal mode\)\s*=\s*(.+)", "time_s", _hms),
                           (r"total estimated time:\s*([^;\n]+)", "time_s", _hms),
                           (r"model printing time:\s*([^;\n]+)", "time_s", _hms),
                           (r"filament used \[g\]\s*=\s*([\d.]+)", "filament_g", float),
                           (r"total filament weight \[g\]\s*:\s*([\d.]+)", "filament_g", float),
                           (r"filament used \[mm\]\s*=\s*([\d.]+)", "filament_mm", float),
                           (r"total filament length \[mm\]\s*:\s*([\d.]+)", "filament_mm", float)):
        m = re.search(pat, text)
        if m and r[key] is None:
            r[key] = round(conv(m.group(1)), 1)
    z, sup = None, set()
    for line in text.splitlines():
        if line.startswith((";Z:", "; Z_HEIGHT:")):
            z = float(line.split(":")[1])
            r["layers"] += 1
        elif line.startswith((";TYPE:Support material", "; FEATURE: Support", ";TYPE:Support")) and z is not None:
            sup.add(round(z, 2))
    r["support_layers"] = sorted(sup)
    return r


def warnings_of(text):
    keep = re.compile(r"warning|error|floating|overhang|bridg|stability|detached|empty|cantilever", re.I)
    out = []
    for raw in text.splitlines():
        if not keep.search(raw) or "[trace]" in raw:
            continue
        line = re.sub(r"^\[[^\]]*\]\s*(\[[^\]]*\]\s*)?", "", raw.strip())     # timestamps, thread ids
        if line not in out:
            out.append(line[:240])
    return out[:20]


def gcode_text(outdir):
    for g in sorted(glob.glob(os.path.join(outdir, "**", "*.gcode"), recursive=True)):
        with open(g, errors="replace") as f:
            return f.read()
    import zipfile
    for t in sorted(glob.glob(os.path.join(outdir, "*.3mf"))):
        with zipfile.ZipFile(t) as z:
            for n in z.namelist():
                if n.endswith(".gcode"):
                    return z.read(n).decode("utf-8", "replace")
    return None


# ------------------------------------------------------------------ running

def slice_one(s, stl, supports, work):
    outdir = os.path.join(work, "out", "%s_%s" % (os.path.basename(stl)[:-4], "sup" if supports else "nosup"))
    os.makedirs(outdir, exist_ok=True)
    r = GR.run_sandboxed(command(s, work, stl, supports, outdir), sandbox_profile(work), env=env_for(work), cwd=work, timeout=TIMEOUT)
    g = gcode_text(outdir)
    res = {"status": r["status"], "code": r["code"], "exception": r["exception"], "seconds": r.get("seconds"),
           "warnings": warnings_of(r.get("stdout", "") + "\n" + r.get("stderr", "")), "gcode": g is not None}
    if g:
        res.update(parse_gcode(g))
    if r["status"] != "exit" or r["code"] != 0 or not g:
        res["log_tail"] = (r.get("stderr") or r.get("stdout") or "")[-1500:]
    return res


def cube_stl(path, a=20.0):
    v = [(x, y, z) for z in (0, a) for y in (0, a) for x in (0, a)]
    faces = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4), (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]
    with open(path, "wb") as f:
        f.write(b"cad slice smoke cube".ljust(80, b" ") + struct.pack("<I", len(faces)))
        for t in faces:
            f.write(struct.pack("<3f", 0, 0, 0) + b"".join(struct.pack("<3f", *v[i]) for i in t) + b"\0\0")


def probe(s):
    """The one smoke test: a 20 mm cube, supports off. Usable only if it exits 0 with G-code and a time estimate."""
    work = workspace()
    stl = os.path.join(work, "cube20.stl")
    cube_stl(stl)
    t0 = time.time()
    r = slice_one(s, stl, False, work)
    leaked = GR.crash_reports_since(t0, [os.path.basename(s["exe"])])
    ok = r["status"] == "exit" and r["code"] == 0 and r["gcode"] and r.get("time_s")
    why = ("smoke test sliced a 20 mm cube: %s s, %s g" % (r.get("time_s"), r.get("filament_g")) if ok else
           "smoke test %s (exit %s%s)%s" % (r["status"], r["code"], ", %s" % r["exception"] if r["exception"] else "",
                                            "; no G-code" if r["status"] == "exit" else ""))
    if leaked:
        why += "; crash report written despite the guard: %s" % leaked
    _record(s, "usable" if ok else "unusable", why, {k: r.get(k) for k in ("status", "code", "exception", "seconds", "warnings", "log_tail")})
    shutil.rmtree(work, ignore_errors=True)
    return ok, why


def choose(found, want=None):
    """The first usable slicer (preference order), smoke-testing an untested one once. Never re-runs an unusable one."""
    notes = []
    for s in found:
        if want and s["name"] != want:
            continue
        st, why = verdict(s)
        if st == "untested":
            ok, why = probe(s)
            st = "usable" if ok else "unusable"
        notes.append("%s %s: %s, %s" % (s["name"], s["version"], st, why))
        if st == "usable":
            return s, notes
    return None, notes


def main(argv):
    opt, pos = {}, []
    i = 0
    while i < len(argv):
        if argv[i].startswith("--"):
            k = argv[i][2:]
            if k in ("detect", "no-support-pass"):
                opt[k] = True
                i += 1
            else:
                opt[k] = argv[i + 1] if i + 1 < len(argv) else ""
                i += 2
        else:
            pos.append(argv[i])
            i += 1
    found = detect()
    if opt.get("detect") or (not pos and not opt.get("probe") and not opt.get("reprobe")):
        if not found:
            print("CAD SLICE: no slicer installed (looked for PrusaSlicer, OrcaSlicer, Bambu Studio)")
        for s in found:
            st, why = verdict(s)
            print("CAD SLICE: %-12s %-12s %-9s %s\n    %s" % (s["name"], s["version"], st, why, s["exe"]))
        return 0
    if opt.get("reprobe"):
        d = _load(CACHE)
        for s in found:
            if s["name"] == opt["reprobe"]:
                d.pop(s["key"], None)
                if s["key"] in _load(KNOWN):
                    print("CAD SLICE: %s is listed in %s; that verdict stays until the slicer version changes" % (s["key"], KNOWN))
        with open(CACHE, "w") as f:
            json.dump(d, f, indent=1)
        opt["probe"] = opt["reprobe"]
    if opt.get("probe"):
        s = next((x for x in found if x["name"] == opt["probe"]), None)
        if not s:
            print("CAD SLICE: %s is not installed" % opt["probe"])
            return 2
        st, why = verdict(s)
        if st != "untested":
            print("CAD SLICE: %s %s already %s: %s" % (s["name"], s["version"], st, why))
            return 0 if st == "usable" else 1
        ok, why = probe(s)
        print("CAD SLICE: %s %s %s: %s" % (s["name"], s["version"], "usable" if ok else "UNUSABLE", why))
        return 0 if ok else 1
    s, notes = choose(found, opt.get("slicer"))
    for n in notes:
        print("  " + n)
    if not s:
        print("CAD SLICE: NO USABLE SLICER%s. Nothing was sliced. `cad printcheck` (the layer check) is the authority for "
              "supports; see docs/STATUS.md for the slicer to install." % (" (none installed)" if not found else ""))
        return 3
    files = []
    for p in pos:
        files += sorted(glob.glob(os.path.join(p, "*.stl"))) if os.path.isdir(p) else [p]
    if opt.get("only"):
        files = [f for f in files if any(fnmatch.fnmatch(os.path.basename(f)[:-4], g) for g in opt["only"].split(","))]
    work = workspace()
    rows = []
    for fp in files:
        stl = os.path.join(work, os.path.basename(fp))
        shutil.copy(fp, stl)                                  # the sandbox reads only copies in its own dir
        a = slice_one(s, stl, False, work)
        b = None if opt.get("no-support-pass") else slice_one(s, stl, True, work)
        row = {"stl": os.path.basename(fp)[:-4], "no_supports": a, "with_supports": b,
               "slicer_adds_support": bool(b and b.get("support_layers")),
               "support_z": (b or {}).get("support_layers", [])[:1] + (b or {}).get("support_layers", [])[-1:]}
        rows.append(row)
        print("  %-22s %s  %s g  %s%s" % (row["stl"], "%5.1f min" % (a["time_s"] / 60) if a.get("time_s") else "  failed ",
                                          a.get("filament_g"), "SUPPORT z %s..%s" % tuple(row["support_z"]) if row["slicer_adds_support"] else
                                          "no support" if b and b.get("gcode") else "", "; %d warnings" % len(a["warnings"]) if a["warnings"] else ""))
    out = opt.get("out") or (pos[0] if pos and os.path.isdir(pos[0]) else os.path.dirname(os.path.abspath(pos[0])))
    rep = {"tool": "cad slice", "slicer": {k: s[k] for k in ("name", "version", "exe")}, "parts": rows,
           "summary": {"parts": len(rows), "failed": [r["stl"] for r in rows if not r["no_supports"].get("gcode")],
                       "slicer_adds_support": [r["stl"] for r in rows if r["slicer_adds_support"]],
                       "total_min": round(sum(r["no_supports"].get("time_s") or 0 for r in rows) / 60, 1),
                       "total_g": round(sum(r["no_supports"].get("filament_g") or 0 for r in rows), 1)}}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "slice.json"), "w") as f:
        json.dump(rep, f, indent=1)
    shutil.rmtree(work, ignore_errors=True)
    sm = rep["summary"]
    print("CAD SLICE %s: %s %s, %d parts, %.1f min, %.1f g; slicer adds support to: %s -> %s" % (
        "FAIL" if sm["failed"] else "OK", s["name"], s["version"], sm["parts"], sm["total_min"], sm["total_g"],
        ", ".join(sm["slicer_adds_support"]) or "none", os.path.join(out, "slice.json")))
    return 1 if sm["failed"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
