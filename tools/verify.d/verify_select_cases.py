"""Cases for tools/verify_select.py (verify_all.sh --changed). Plain python3; prints PASS/FAIL lines.

    python3 -I tools/verify.d/verify_select_cases.py <repo root>

1. The map itself: every section is guarded and has a watch, no code outside sections and plumbing, every `want X`
   names a section, every verify.d script has a `# watch:` header, every pattern matches a file, every $ROOT path,
   Python os.path.join path, cad subcommand and layer check a unit runs is in its own watch, a unit that reads another
   unit's $V output (shell, or bench's --from-verify reports via corpus.json) makes it or `needs:` it, and every
   tracked file maps somewhere.
2. Fake changed-file lists -> the exact plan (docs only, printcheck.py, a cadlib file, a new tools/ dir, ...).
3. verify_all.sh and verify.d lines -> sections (comment, section body, plumbing, preamble), on the real files.
4. git: merge-base diff + uncommitted + untracked, and an empty diff, on scratch repos; the real verify_all.sh
   --dry-run; a small copy of verify_all.sh that must fail when a selected unit runs no check or doesn't run.
5. printcheck's result cache is keyed on its source.
Every PR #12 review finding has a case here (marked "review").
"""
import contextlib, importlib.util, io, json, os, re, shutil, subprocess, sys, tempfile

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
first = SECTIONS[0]["start"]
loose = [n for n in range(first, len(VA_LINES) + 1) if REGION[n] == ("global",) and code(VA_LINES[n - 1])]
say(not loose and len(set(IDS)) == len(IDS),
    "%d sections, unique IDs; code after the first section is in a section or a plumbing block (review: an appended "
    "section after 7 passed): %s" % (len(SECTIONS), loose or "none outside"))
wants = [w for l in VA_LINES if code(l) for w in re.findall(r'(?:^if |&& )want ([^\s;&|]+)', l)]
odd = [w for w in wants if w not in IDS and w != '"${f##*/}"']
say(not odd and len(wants) == len(SECTIONS) + 1, "every `want X` names a section the parser found (review): %s" % (odd or "%d wants" % len(wants)))
empty = [u["id"] for u in SECTIONS if not [p for p in u["watch"] if not p.startswith("!")]]
say(not empty, "every section's watch: is non-empty (review): %s" % (empty or "all"))
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
    for py in sorted({f for f, _ in want if f.endswith(".py") and not f.startswith(S)}):
        want += [(f, "%s reaches %s" % (py, d)) for d, fs in py_refs(py) for f in fs]
    return want


def py_refs(py):
    """Repo paths a Python file a unit runs reaches with os.path.join(ROOT or its own dir, "a", "b") (review: the
    blend-bracket build imports components/placeholders.py and reads components.json, invisible from the shell). A part
    with * or ? is a glob: the files it matches (cadcfg_cases.py walks examples/**/checks*.json, not all of examples/)."""
    try:
        src = open(os.path.join(ROOT, py)).read()
    except OSError:
        return []
    out = []
    for args in re.findall(r'os\.path\.join\(([^()]*)\)', src):
        if args.split(",")[0].strip() not in ("ROOT", "HERE"):   # paths from the repo root or the file's own dir
            continue
        parts = [a or b for a, b in re.findall(r'"([^"]*)"|\'([^\']*)\'', args)]
        for base in ([os.path.dirname(py), ""] if parts else []):
            c = os.path.normpath(os.path.join(base, *parts))
            if c == S.rstrip("/"):   # cadlib's home: the library and cadcheck (features reads its DEFAULTS)
                out.append((c, [f for f in FILES if f.startswith(S + "cadlib/") or f == S + "cadcheck.py"]))
                break
            if "*" in c or "?" in c:   # a glob.glob pattern (cadcfg's config walk): the files it matches
                hits = [f for f in FILES if not c.startswith("..") and VS.glob_re(c).match(f)]
            else:
                hits = [f for f in FILES if not c.startswith("..") and c != "." and (f == c or f.startswith(c + "/"))]
            if hits:
                out.append((c, hits))
                break
    return out


globbed = {d: len(fs) for d, fs in py_refs("tools/verify.d/cadcfg_cases.py") if "*" in d}
say(sorted(globbed) == ["examples/**/checks*.json", "examples/**/overlay*.json", "examples/**/review_rows*.json",
                        "skills/print-cad-blender/templates/**/checks*.json"] and all(globbed.values()),
    "an os.path.join glob reaches the files it matches, not nothing (cadcfg_cases.py's config walk): %s" % globbed)
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


def vtokens(u):
    return [re.compile("[^/]+".join(re.escape(x) for x in re.split(r"\$\{?\w+\}?", t)) + r"\Z")
            for l in u["body"] if not l.lstrip().startswith("#") for t in re.findall(r'\$V/([A-Za-z0-9_.${}/-]+)', l)]


def corpus_reads(u):
    """$V files a unit's tools read through `replay.py --from-verify "$V" --attempts X`: corpus.json's verify_out."""
    corpus = json.load(open(os.path.join(ROOT, "tools/bench/corpus.json")))["attempts"]
    out = []
    for l in u["body"]:
        m = re.search(r'--from-verify "\$V".*--attempts (\S+)', l)
        for att in (m.group(1).split(",") if m else []):
            out += [(r["verify_out"], att) for r in corpus.get(att, {}).get("runs", []) if r.get("verify_out")]
    return out


TOK = {u["id"]: vtokens(u) for u in M["units"]}
creads, nread = [], 0
for u in M["units"]:
    for vo, att in corpus_reads(u):
        nread += 1
        prod = [i for i, ts in TOK.items() if i != u["id"] and any(t.match(vo) for t in ts)]
        if not set(prod) & set(u["needs"]):
            creads.append("%s reads $V/%s (%s) from %s" % (u["id"], vo, att, ",".join(prod) or "no unit"))
say(nread and not creads, "bench's --from-verify reads (corpus.json verify_out, %d files) come from units it needs: (review: "
    "4m's pc-v2/printcheck.json, 4n's v2a7/layer.json): %s" % (nread, "; ".join(creads) or "all"))

unm = [f for f in FILES if not VS.line_mapped(f) and not any(covered(u, f) for u in M["units"]) and not M["none"].match(f)]
say(not unm, "every file in the repo is watched or under none: (else it would run everything): %s" % (unm[:8] or "all"))


# ------------------------------------------------------------------ 2. fake changed-file lists
fmt = lambda s: "everything" if s == "ALL" else (" ".join(i for i in IDS if i in s) or "nothing")


def sel(paths, m=None):
    p = VS.plan(m or M, {x: None for x in paths})
    return "ALL" if p["all"] else set(p["run"])


SELF = "verify_select.sh"


ALLIDS = set(IDS)
CORE = ALLIDS - {"6", "7", "4m-slice", "design_principles.sh", "verify_select.sh"}
BENCH = {"bench.sh", "4k", "4m", "4n"}   # bench reads 4k's, 4m's and 4n's reports
PCO = {"printcheck_overhangs.sh"}        # watches printcheck.py and the v2a7 STLs, reads 4m's model
STL = {"stl_read.sh"}                    # watches printcheck.py (read_stl), the prior_art readers and the v2a7 STLs
CASES = [   # the selector test always runs under --changed (review); it is added to every set here
    ("docs only", ["docs/STATUS.md", "README.md", "skills/print-cad-blender/reference/api.md", "skills/cad-design-review/SKILL.md",
                   "tools/verify.d/README", "tools/bench/README.md", "docs/tasks/x.md"], set()),
    ("printcheck.py (3's output feeds 3b, 3c)", [S + "printcheck.py"], {"1", "3", "3b", "3c", "blend_bracket.sh"} | BENCH | PCO | STL),
    ("a cadlib file", [S + "cadlib/geom.py"], CORE),
    ("cadcheck.py", [S + "cadcheck.py"], CORE),
    ("the cad wrapper", [S + "cad"], CORE | {"4m-slice"}),
    ("a new standalone tools/ dir", ["tools/newtool/run.py", "tools/newtool/README.md"], "ALL"),
    ("a .md inside skills/*/scripts", [S + "NOTES.md"], "ALL"),
    ("cadslice.py", [S + "cadslice.py"], {"4m-slice"}),
    ("slicers/known.json", ["skills/print-cad-blender/slicers/known.json"], {"4m-slice"}),
    ("cadrows.py + cadbom.py", [S + "cadrows.py", S + "cadbom.py"], {"4f", "calcs_materials.sh"}),   # it asserts cad rows on calcs
    ("template params.py", ["skills/print-cad-blender/templates/project/params.py"], {"3", "3b", "3c", "design_principles.sh"}),
    ("FINDINGS.md (design_principles reads it)", ["docs/FINDINGS.md"], {"design_principles.sh"}),
    ("components/ (review: blend-bracket imports placeholders)", ["components/placeholders.py"], {"5", "blend_bracket.sh"}),
    ("components.json (review)", ["components/components.json"], {"5", "blend_bracket.sh"}),
    ("the workflow template", ["templates/cad-loop.workflow.js"], {"6"}),
    ("tools/transcript", ["tools/transcript/cc_transcript.py"], {"7"}),
    ("v2a3 example (4n's output feeds bench; cadcfg reads every config)", ["examples/mm-launcher-v2a3/checks.json"],
     {"4f", "4g", "4n", "cadcfg.sh"} | BENCH),
    ("v2a3 BOM .md (a test input, not a doc)", ["examples/mm-launcher-v2a3/BOM_AND_ASSEMBLY.md"], {"4f", "4g", "4n"} | BENCH),
    ("a3 example", ["examples/mm-launcher-a3/mm_launcher_a3.blend.gz"], {"4c", "4n", "blend_bracket.sh", "cable_router.sh"} | BENCH),
    ("a2 example (a config: cadcfg too; fastener_access_hint.sh reads 4a's report)", ["examples/mm-launcher-a2/checks.json"],
     {"4a", "4b", "4n", "cadcfg.sh", "fastener_access_hint.sh"} | BENCH),
    ("a v2a7 review_rows config", ["examples/mm-launcher-v2a7/review_rows_v2a7.json"], {"4n", "cadcfg.sh"} | BENCH | PCO),
    ("the v2a3 blend (cadcfg's suggestion check runs on its report)", ["examples/mm-launcher-v2a3/mm_launcher_v2a3.blend.gz"],
     {"4f", "4g", "4n", "cadcfg.sh"} | BENCH),
    ("the template's checks.json", ["skills/print-cad-blender/templates/project/checks.json"],
     {"3", "3b", "3c", "design_principles.sh", "cadcfg.sh"}),
    ("v2a7 STLs", ["examples/mm-launcher-v2a7/stl.tar.gz"], BENCH | PCO | STL),
    ("demo-turret", ["examples/demo-turret/build.py"], {"1", "2"}),
    ("slide-gate config (cadcfg too)", ["examples/slide-gate/checks.json"], {"slide-gate", "cadcfg.sh"}),
    ("slide-gate build", ["examples/slide-gate/build.py"], {"slide-gate"}),
    ("a verify.d helper", ["tools/verify.d/fastener_joint_build.py"], {"fastener_joint.sh"}),
    ("bench labels (review: planned bench + 4k only, and bench failed)", ["tools/bench/labels.json"], BENCH),
    ("the selector", ["tools/verify_select.py"], set()),
    ("a new verify.d script", ["tools/verify.d/new_feature.sh"], set()),
    ("fastener_overlap's prior_art repro (review: no header, prior_art was none:)",
     ["tools/prior_art/cadcheck_head_overlap_repro.py"], {"fastener_overlap.sh"}),
    ("fastener_overlap's build helper", ["tools/verify.d/fastener_overlap_build.py"], {"fastener_overlap.sh"}),
    ("a prior_art file no test reads", ["tools/prior_art/dfam_compare.py"], set()),
    ("a prior_art STL reader (none: in verify_all, but stl_read.sh watches it)", ["tools/prior_art/tri_dist.py"], STL),
    ("a new prior_art file (review: only listed files are none:)", ["tools/prior_art/new_compare.py"], "ALL"),
]
for name, paths, want in CASES:
    want = want if want == "ALL" else want | {SELF}
    got = sel(paths)
    say(got == want, "%s -> %s" % (name, fmt(got)) if got == want else "%s -> got %s, want %s" % (name, fmt(got), fmt(want)))
p = VS.plan(M, {"tools/newtool/run.py": None})
say(p["all"] == ["unmapped: tools/newtool/run.py"], "an unmapped path says why: %s" % p["all"])
# a verify.d script with no # watch: header runs on every change (review: fastener_overlap.sh had none)
M2 = dict(M, units=M["units"] + [dict(VS.parse_script("nohdr.sh", "ok x\n"), pats=VS.Patterns(["tools/verify.d/nohdr.sh"]))],
          ids=M["ids"] + ["nohdr.sh"])
p = VS.plan(M2, {"docs/STATUS.md": None})
say("nohdr.sh" in p["run"] and "no watch header" in p["run"]["nohdr.sh"][0],
    "a verify.d script with no # watch: header runs on a docs-only change, \"%s\" (review)" % p["run"].get("nohdr.sh", ["-"])[0])
p = VS.plan(M, {})
say(not p["run"], "no changed paths -> nothing selected (main() stops before this: see the empty-diff case)")


# ------------------------------------------------------------------ 3. line-mapped files
def line_of(text, pred):
    return next(n for n, l in enumerate(text.split("\n"), 1) if pred(l))


def lsel(path, changes):
    p = VS.plan(M, {path: changes})
    return "ALL" if p["all"] else set(p["run"])


n = line_of(VA_TEXT, lambda l: '$CAD bom "$V23/BOM_AND_ASSEMBLY.md"' in l)
body = lambda sec, pred: next(n for n in range(U[sec]["start"] + 1, U[sec]["end"]) if pred(VA_LINES[n - 1]))
code_in = lambda sec: body(sec, lambda l: code(l))
L = [("verify_all.sh: a 4f body line", [("+", [n], VA_LINES[n - 1] + " # edited")], {"4f"}),
     ("verify_all.sh: a 3b body line pulls in 3 (needs)", [("-", [line_of(VA_TEXT, lambda l: "--out writes model.blend" in l)], "x=1")],
      {"3b", "3"}),
     ("verify_all.sh: a section-3 body line runs 3b and 3c, which read its output (review)", [("+", [code_in("3")], "x=1")], {"3", "3b", "3c"}),
     ("verify_all.sh: a 4k body line runs bench.sh, which reads its reports (review)", [("+", [code_in("4k")], "x=1")], BENCH),
     ("verify_all.sh: a comment line", [("+", [n - 1], "  # a new remark")], set()),
     ("verify_all.sh: a #@ watch line", [("+", [U["4f"]["start"]], VA_LINES[U["4f"]["start"] - 1])], set()),
     ("verify_all.sh: plumbing want() (review: `return 1` ran nothing and passed)",
      [("+", [line_of(VA_TEXT, lambda l: l.startswith("want()"))], "want() { return 1; }")], "ALL"),
     ("verify_all.sh: plumbing, the verify.d loop (review)",
      [("+", [line_of(VA_TEXT, lambda l: l.startswith("for f in") and "verify.d" in l)], "for f in x; do :; done")], "ALL"),
     ("verify_all.sh: plumbing, the SELECT parsing (review)",
      [("-", [line_of(VA_TEXT, lambda l: "SELECTED=$(printf" in l)], "  SELECTED=ALL")], "ALL"),
     ("verify_all.sh: the preamble (CAD_LAYER_CHECK)", [("-", [line_of(VA_TEXT, lambda l: l.startswith("export CAD_LAYER_CHECK"))], "export CAD_LAYER_CHECK=1")], "ALL"),
     ("verify_all.sh: a code line deleted between 4e and 4f (unguarded)", [("-", [U["4e"]["end"], U["4e"]["end"] + 1], "echo x")], "ALL"),
     ("verify_all.sh: a deleted line at the end of 4f's body", [("-", [U["4f"]["end"] - 1, U["4f"]["end"]], "echo x")], {"4f"})]
FJ = open(os.path.join(ROOT, "tools/verify.d/fastener_joint.sh")).read()
L += [("fastener_joint.sh: a code line", [("+", [5], "mkdir -p \"$V/fj2\"")], {"fastener_joint.sh"}),
      ("fastener_joint.sh: its # watch: header", [("+", [2], "# watch: @core")], set())]
for name, ch, want in L:
    want = want if want == "ALL" else want | {SELF}
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

with tempfile.TemporaryDirectory() as t:   # review: --changed on next right after a merge selected nothing silently
    g = lambda *a: subprocess.run(["git", "-C", t, *a], capture_output=True, text=True, check=True)
    g("init", "-q", "-b", "next")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(os.path.join(t, "a.txt"), "w").write("1\n")
    g("add", "-A"); g("commit", "-qm", "base")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = VS.main(["--changed", "next"], root=t)
    say(rc == 3 and "HEAD^1" in out.getvalue() and "merge-base is HEAD" in out.getvalue(),
        "an empty diff (merge-base == HEAD, clean tree) says so and exits %s, suggesting --changed HEAD^1 (review)" % rc)

# a small copy of verify_all.sh with two scripts: one runs a check, one runs none (review: want() `return 1` passed)
with tempfile.TemporaryDirectory() as t:
    os.makedirs(os.path.join(t, "tools/verify.d"))
    shutil.copy(os.path.join(ROOT, "tools/verify_select.py"), os.path.join(t, "tools"))
    open(os.path.join(t, "tools/verify.d/one.sh"), "w").write('# watch: x.txt\nok "one ran"\n')
    open(os.path.join(t, "tools/verify.d/empty.sh"), "w").write('# watch: y.txt\n:\n')
    env = dict(os.environ, VERIFY_TMP=os.path.join(t, "vt"))

    def mini(paths, edit=None):
        va = VA_TEXT if edit is None else VA_TEXT.replace(*edit)
        open(os.path.join(t, "tools/verify_all.sh"), "w").write(va)
        return subprocess.run(["sh", os.path.join(t, "tools/verify_all.sh"), "--files", *paths], capture_output=True, text=True, env=env)

    r = mini(["x.txt"])
    say(r.returncode == 0 and "PASS one ran" in r.stdout and "1 passed, 0 failed" in r.stdout,
        "a --changed run of a small copy runs the one selected script and passes (exit %d)" % r.returncode)
    r = mini(["y.txt"])
    say(r.returncode == 1 and "FAIL verify_all: empty.sh was selected but ran no checks" in r.stdout,
        "a selected unit that runs no check fails the run (exit %d) (review)" % r.returncode)
    brk = ('  CUR=$1; CUR_N=$((pass+fail)); RAN="$RAN $1"; return 0', "  return 1")
    r = mini(["x.txt"], brk)
    say(brk[0] in VA_TEXT and r.returncode == 1 and "FAIL verify_all: one.sh was selected but did not run" in r.stdout,
        "want() broken to `return 1`: the selected unit is reported as not run and the run fails (exit %d) (review)" % r.returncode)

latest = os.path.realpath("/tmp/alex3d-verify/latest") if os.path.exists("/tmp/alex3d-verify/latest") else None
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--dry-run", "--files", S + "printcheck.py"],
                   capture_output=True, text=True)
ran = re.findall(r"^run +(\S+)", r.stdout, re.M)
say(r.returncode == 0 and set(ran) == {"1", "3", "3b", "3c", "blend_bracket.sh", SELF} | BENCH | PCO | STL and "SELECT" not in r.stdout
    and "UNITS" not in r.stdout,
    "verify_all.sh --dry-run --files printcheck.py prints the plan and stops: %s" % " ".join(ran))
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--dry-run"], capture_output=True, text=True)
say(r.returncode == 0 and all(i in r.stdout.split() for i in IDS) and "every section and script runs" in r.stdout,
    "verify_all.sh --dry-run with no --changed lists all %d sections and scripts (no flag runs everything)" % len(IDS))
r = subprocess.run(["sh", os.path.join(ROOT, "tools/verify_all.sh"), "--bogus"], capture_output=True, text=True)
say(r.returncode == 2 and "unknown argument" in r.stdout, "verify_all.sh rejects an unknown flag (exit %d)" % r.returncode)
now = os.path.realpath("/tmp/alex3d-verify/latest") if os.path.exists("/tmp/alex3d-verify/latest") else None
say(now == latest, "dry runs make no run directory (/tmp/alex3d-verify/latest unchanged)")

# ------------------------------------------------------------------ 5. printcheck's cache key
# review: the result cache under $TMPDIR was keyed on a hand-bumped _VERSION, so an edit to the analysis could pass on
# results cached before it. Two copies differing by one comment must get different keys.
PCSRC = open(os.path.join(ROOT, S + "printcheck.py")).read()
with tempfile.TemporaryDirectory() as t:
    keys = []
    for k, extra in enumerate(("", "\n# an edit\n")):
        f = os.path.join(t, "pc%d.py" % k)
        open(f, "w").write(PCSRC + extra)
        sp = importlib.util.spec_from_file_location("pc%d" % k, f)
        mod = importlib.util.module_from_spec(sp)
        try:
            sp.loader.exec_module(mod)
            keys.append(mod._SOURCE)
        except Exception as e:   # numpy missing in this python3
            keys.append("error %s" % e)
say(len(set(keys)) == 2 and not any(k.startswith("error") for k in keys) and "_SOURCE.encode()" in PCSRC.split("def analyze_cached")[1][:900],
    "printcheck's result cache key includes a hash of printcheck.py, so a code change misses the cache (review): %s" % [k[:9] for k in keys])
