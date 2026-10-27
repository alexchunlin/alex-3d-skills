"""Cases for tools/verify_select.py (verify_all.sh --changed). Plain python3; prints PASS/FAIL lines.

    python3 -I tools/verify.d/verify_select_cases.py <repo root>

1. The map itself: every section is guarded and watched, every verify.d script has a `# watch:` header, every pattern
   matches a file, every $ROOT path, cad subcommand and layer-check run a unit makes is covered by its own watch, a
   unit that reads another section's $V output either makes it or `needs:` it, and every tracked file maps somewhere.
2. Fake changed-file lists -> the exact plan (docs only, printcheck.py, a cadlib file, a new tools/ dir, ...).
3. verify_all.sh and verify.d lines -> sections (comment, section body, plumbing, preamble), on the real files.
4. git: merge-base diff + uncommitted + untracked, on a scratch repo; then the real verify_all.sh --dry-run.
"""
import importlib.util, os, re, subprocess, sys, tempfile

ROOT = os.path.abspath(sys.argv[1])
spec = importlib.util.spec_from_file_location("verify_select", os.path.join(ROOT, "tools", "verify_select.py"))
VS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VS)


def say(ok, msg):
    print(("PASS " if ok else "FAIL ") + "verify_select: " + msg)


M = VS.load(ROOT)
U = {u["id"]: u for u in M["units"]}
IDS = M["ids"]
FILES = subprocess.run(["git", "-C", ROOT, "ls-files", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True, check=True).stdout.split()
VA_TEXT = open(os.path.join(ROOT, VS.VA)).read()
VA_LINES = VA_TEXT.split("\n")
REGION = M["region"]
SCRIPTS = [u for u in M["units"] if u["kind"] == "script"]
SECTIONS = [u for u in M["units"] if u["kind"] == "section"]
S = "skills/print-cad-blender/scripts/"

# ------------------------------------------------------------------ 1. the map
code = lambda l: l.strip() and not l.strip().startswith("#")
first, last = SECTIONS[0]["start"], SECTIONS[-1]["end"]
loose = [n for n in range(first, last + 1) if REGION[n] == ("global",) and code(VA_LINES[n - 1])]
say(not loose and len(set(IDS)) == len(IDS),
    "%d sections, all guarded by `if want ID`, unique IDs; unguarded code between sections: %s" % (len(SECTIONS), loose or "none"))
loop = [l for l in VA_LINES if "tools/verify.d/*.sh" in l and l.startswith("for f in")]
say(len(loop) == 1 and 'want "${f##*/}"' in loop[0], "the verify.d loop sources each script only when want selects it")
nohdr = [u["id"] for u in SCRIPTS if not u["has_watch"]]
say(not nohdr, "every tools/verify.d/*.sh has a `# watch:` header (%d scripts; missing: %s)" % (len(SCRIPTS), nohdr or "none"))

dead = ["%s: %s" % (u["id"], p) for u in M["units"] for p in u["pats"].pats if not p.startswith("!")
        and not any(VS.glob_re(p).match(f) for f in FILES)]
dead += ["none: %s" % p for p in M["none"].pats if not p.startswith("!") and not any(VS.glob_re(p).match(f) for f in FILES)]
say(not dead, "every watch pattern matches a file (a renamed path can't go quiet): %s" % (dead or "all match"))


def covered(u, path):
    return u["pats"].match(path) is not None


def body_needs(u):
    """Repo paths the unit's code reads, as (path, why): $ROOT literals, the cad subcommands it calls, layer checks."""
    body = "\n".join(l for l in u["body"] if not l.lstrip().startswith("#"))
    want = []
    for m in re.finditer(r'\$ROOT/([A-Za-z0-9_./*-]+)(.?)', body):
        ref, nxt = m.group(1).rstrip("/"), m.group(2)
        if ref == S.rstrip("/"):   # the scripts dir on sys.path: what Blender-side helpers import is cadlib + cadcheck
            want += [(f, "$ROOT/" + ref) for f in FILES if f.startswith(S + "cadlib/") or f == S + "cadcheck.py"]
            continue
        trunc = nxt == "$"
        hits = [f for f in FILES if f == ref or f.startswith(ref + "/") or (trunc and f.startswith(ref))]
        want += [(f, "$ROOT/" + ref) for f in hits] or [(ref, "$ROOT/" + ref + " (no such file)")]
    sub = set(re.findall(r'\$CAD (\w+)', body))
    core = [S + "cad"] + [f for f in FILES if f.startswith(S + "cadlib/")] + [S + "cadcheck.py"]
    for c in sub:
        want += [(f, "$CAD " + c) for f in ([S + "cad"] + ({"rows": [S + "cadrows.py"], "bom": [S + "cadbom.py"],
                                                          "slice": [S + "cadslice.py", S + "guarded_run.py"],
                                                          "printcheck": core + [S + "printcheck.py"]}.get(c) or core))]
    if "q" in sub:
        want.append((S + "cadq.py", "$CAD q"))
    if "CAD_LAYER_CHECK=1" in body or "best_orientation" in body:
        want.append((S + "printcheck.py", "layer check"))
    if re.search(r'"\$BL"', body):
        want += [(f, "$BL") for f in FILES if f.startswith(S + "cadlib/")]
    return want


gaps = sorted({"%s: %s (%s)" % (u["id"], p, why) for u in M["units"] for p, why in body_needs(u) if not covered(u, p)})
say(not gaps, "every path a unit's code reads is in its own watch: %s" % ("; ".join(gaps[:8]) or "all covered"))


def vdirs(u):
    """($V dirs the unit makes, [(dir, line)] it reads). Made: mkdir -p, --out, a redirect into it."""
    made, read = set(), []
    for l in u["body"]:
        if l.lstrip().startswith("#"):
            continue
        for m in re.finditer(r'mkdir -p ([^;&|]*)', l):
            made |= set(re.findall(r'\$V/([A-Za-z0-9_.-]+)', m.group(1)))
        made |= set(re.findall(r'(?:--out\s+|>\s*)"?\$V/([A-Za-z0-9_.-]+)', l))
        for m in re.finditer(r'\$V/([A-Za-z0-9_.-]+)', l):
            if "||" not in l[m.end():]:   # `cp "$V/x/y" ... 2>/dev/null || gunzip ...` makes its own fallback
                read.append((m.group(1), l.strip()[:70]))
    return made, read


VD = {u["id"]: vdirs(u) for u in M["units"]}
cross = []
for u in M["units"]:
    made, read = VD[u["id"]]
    for d, line in read:
        prod = [i for i, (mk, _) in VD.items() if d in mk and i != u["id"]]
        if d not in made and prod and not set(prod) & set(u["needs"]):
            cross.append("%s reads $V/%s (made by %s): %s" % (u["id"], d, ",".join(prod), line))
say(not cross, "a unit that reads another section's $V output makes it itself or needs: it: %s" % ("; ".join(sorted(set(cross))[:6]) or "all do"))

unm = [f for f in FILES if not VS.line_mapped(f) and not any(covered(u, f) for u in M["units"]) and not M["none"].match(f)]
say(not unm, "every file in the repo is watched or under none: (else it would run everything): %s" % (unm[:8] or "all"))


# ------------------------------------------------------------------ 2. fake changed-file lists
fmt = lambda s: "everything" if s == "ALL" else (" ".join(i for i in IDS if i in s) or "nothing")


def sel(paths):
    p = VS.plan(M, {x: None for x in paths})
    return "ALL" if p["all"] else set(p["run"])


ALLIDS = set(IDS)
CORE = ALLIDS - {"6", "7", "4m-slice", "design_principles.sh", "verify_select.sh"}
CASES = [
    ("docs only", ["docs/STATUS.md", "README.md", "skills/print-cad-blender/reference/api.md", "skills/cad-design-review/SKILL.md",
                   "tools/verify.d/README", "tools/bench/README.md", "docs/tasks/x.md"], set()),
    ("printcheck.py", [S + "printcheck.py"], {"1", "3", "4m", "4n", "blend_bracket.sh", "bench.sh", "4k"}),
    ("a cadlib file", [S + "cadlib/geom.py"], CORE),
    ("cadcheck.py", [S + "cadcheck.py"], CORE),
    ("the cad wrapper", [S + "cad"], CORE | {"4m-slice"}),
    ("a new standalone tools/ dir", ["tools/newtool/run.py", "tools/newtool/README.md"], "ALL"),
    ("a .md inside skills/*/scripts", [S + "NOTES.md"], "ALL"),
    ("cadslice.py", [S + "cadslice.py"], {"4m-slice"}),
    ("slicers/known.json", ["skills/print-cad-blender/slicers/known.json"], {"4m-slice"}),
    ("cadrows.py + cadbom.py", [S + "cadrows.py", S + "cadbom.py"], {"4f"}),
    ("template params.py", ["skills/print-cad-blender/templates/project/params.py"], {"3", "3b", "3c", "design_principles.sh"}),
    ("FINDINGS.md (design_principles reads it)", ["docs/FINDINGS.md"], {"design_principles.sh"}),
    ("components/", ["components/placeholders.py"], {"5"}),
    ("the workflow template", ["templates/cad-loop.workflow.js"], {"6"}),
    ("tools/transcript", ["tools/transcript/cc_transcript.py"], {"7"}),
    ("v2a3 example", ["examples/mm-launcher-v2a3/checks.json"], {"4f", "4g", "4n"}),
    ("v2a3 BOM .md (a test input, not a doc)", ["examples/mm-launcher-v2a3/BOM_AND_ASSEMBLY.md"], {"4f", "4g", "4n"}),
    ("a3 example", ["examples/mm-launcher-a3/mm_launcher_a3.blend.gz"], {"4c", "4n", "blend_bracket.sh", "cable_router.sh"}),
    ("a2 example", ["examples/mm-launcher-a2/checks.json"], {"4a", "4b", "4n"}),
    ("v2a7 STLs", ["examples/mm-launcher-v2a7/stl.tar.gz"], {"4k", "4m", "4n", "bench.sh"}),
    ("demo-turret", ["examples/demo-turret/build.py"], {"1", "2"}),
    ("slide-gate", ["examples/slide-gate/checks.json"], {"slide-gate"}),
    ("a verify.d helper", ["tools/verify.d/fastener_joint_build.py"], {"fastener_joint.sh"}),
    ("bench labels", ["tools/bench/labels.json"], {"bench.sh", "4k"}),
    ("the selector", ["tools/verify_select.py"], {"verify_select.sh"}),
    ("a new verify.d script", ["tools/verify.d/new_feature.sh"], {"verify_select.sh"}),
    ("prior_art (no test runs it)", ["tools/prior_art/dfam_compare.py"], set()),
]
for name, paths, want in CASES:
    got = sel(paths)
    say(got == want, "%s -> %s" % (name, fmt(got)) if got == want else "%s -> got %s, want %s" % (name, fmt(got), fmt(want)))
p = VS.plan(M, {"tools/newtool/run.py": None})
say(p["all"] == ["unmapped: tools/newtool/run.py"], "an unmapped path says why: %s" % p["all"])


# ------------------------------------------------------------------ 3. line-mapped files
def line_of(text, pred):
    return next(n for n, l in enumerate(text.split("\n"), 1) if pred(l))


def lsel(path, changes):
    p = VS.plan(M, {path: changes})
    return "ALL" if p["all"] else set(p["run"])


n = line_of(VA_TEXT, lambda l: '$CAD bom "$V23/BOM_AND_ASSEMBLY.md"' in l)
L = [("verify_all.sh: a 4f body line", [("+", [n], VA_LINES[n - 1] + " # edited")], {"4f", "verify_select.sh"}),
     ("verify_all.sh: a 3b body line pulls in 3 (needs)", [("-", [line_of(VA_TEXT, lambda l: "--out writes model.blend" in l)], "x=1")],
      {"3b", "3", "verify_select.sh"}),
     ("verify_all.sh: a comment line", [("+", [n - 1], "  # a new remark")], set()),
     ("verify_all.sh: a #@ watch line", [("+", [U["4f"]["start"]], VA_LINES[U["4f"]["start"] - 1])], {"verify_select.sh"}),
     ("verify_all.sh: plumbing (want)", [("+", [line_of(VA_TEXT, lambda l: l.startswith("want()"))], "want() { :; }")], {"verify_select.sh"}),
     ("verify_all.sh: the preamble (CAD_LAYER_CHECK)", [("-", [line_of(VA_TEXT, lambda l: l.startswith("export CAD_LAYER_CHECK"))], "export CAD_LAYER_CHECK=1")], "ALL"),
     ("verify_all.sh: a deleted line between 4e and 4f", [("-", [U["4e"]["end"], U["4e"]["end"] + 1], "echo x")], {"verify_select.sh"}),
     ("verify_all.sh: a deleted line at the end of 4f's body", [("-", [U["4f"]["end"] - 1, U["4f"]["end"]], "echo x")], {"4f", "verify_select.sh"})]
FJ = open(os.path.join(ROOT, "tools/verify.d/fastener_joint.sh")).read()
L += [("fastener_joint.sh: a code line", [("+", [5], "mkdir -p \"$V/fj2\"")], {"fastener_joint.sh", "verify_select.sh"}),
      ("fastener_joint.sh: its # watch: header", [("+", [2], "# watch: @core")], {"verify_select.sh"})]
for name, ch, want in L:
    path = "tools/verify.d/fastener_joint.sh" if name.startswith("fastener") else VS.VA
    got = lsel(path, ch)
    say(got == want, "%s -> %s" % (name, fmt(got)) if got == want else "%s -> got %s, want %s" % (name, fmt(got), fmt(want)))
u0 = VS.parse_u0("@@ -10,2 +10,0 @@\n-a\n-b\n@@ -20 +18,2 @@\n-c\n+d\n+e\n\\ No newline at end of file\n")
say(u0 == [("-", [10, 11], "a"), ("-", [10, 11], "b"), ("-", [18, 19], "c"), ("+", [18], "d"), ("+", [19], "e")],
    "git diff -U0 hunks: a pure deletion sits between its neighbours, a replacement on its new lines")

# ------------------------------------------------------------------ 4. git, and the real script
with tempfile.TemporaryDirectory() as t:
    g = lambda *a: subprocess.run(["git", "-C", t, *a], capture_output=True, text=True, check=True)
    g("init", "-q", "-b", "next")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    os.makedirs(os.path.join(t, "tools/verify.d"))
    open(os.path.join(t, "tools/verify_all.sh"), "w").write("a\nb\nc\n")
    open(os.path.join(t, "keep.txt"), "w").write("1\n")
    open(os.path.join(t, "gone.txt"), "w").write("1\n")
    g("add", "-A"); g("commit", "-qm", "base")
    g("checkout", "-qb", "feat")
    open(os.path.join(t, "committed.txt"), "w").write("1\n")
    g("add", "-A"); g("commit", "-qm", "feat")
    open(os.path.join(t, "keep.txt"), "w").write("2\n")                # uncommitted
    open(os.path.join(t, "untracked.txt"), "w").write("1\n")           # untracked
    os.remove(os.path.join(t, "gone.txt"))                             # deleted
    open(os.path.join(t, "tools/verify_all.sh"), "w").write("a\nB\nc\n")
    mb, ch = VS.changes_from_git("next", root=t)
    say(set(ch) == {"committed.txt", "keep.txt", "untracked.txt", "gone.txt", "tools/verify_all.sh"}
        and ch["tools/verify_all.sh"] == [("-", [2], "b"), ("+", [2], "B")],
        "git: committed since the merge-base, uncommitted, untracked and deleted paths; verify_all.sh by line: %s" % sorted(ch))

latest = os.path.realpath("/tmp/alex3d-verify/latest") if os.path.exists("/tmp/alex3d-verify/latest") else None
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--dry-run", "--files", S + "printcheck.py"],
                   capture_output=True, text=True)
ran = re.findall(r"^run +(\S+)", r.stdout, re.M)
say(r.returncode == 0 and set(ran) == {"1", "3", "4m", "4n", "blend_bracket.sh", "bench.sh", "4k"} and "SELECT" not in r.stdout,
    "verify_all.sh --dry-run --files printcheck.py prints the plan and stops: %s" % " ".join(ran))
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--dry-run"], capture_output=True, text=True)
say(r.returncode == 0 and all(i in r.stdout.split() for i in IDS) and "every section and script runs" in r.stdout,
    "verify_all.sh --dry-run with no --changed lists all %d sections and scripts (no flag runs everything)" % len(IDS))
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--bogus"], capture_output=True, text=True)
say(r.returncode == 2 and "unknown argument" in r.stdout, "verify_all.sh rejects an unknown flag (exit %d)" % r.returncode)
now = os.path.realpath("/tmp/alex3d-verify/latest") if os.path.exists("/tmp/alex3d-verify/latest") else None
say(now == latest, "dry runs make no run directory (/tmp/alex3d-verify/latest unchanged)")
