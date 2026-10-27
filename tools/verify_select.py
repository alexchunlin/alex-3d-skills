"""verify_select: which tools/verify_all.sh sections and tools/verify.d scripts a change affects.

  sh tools/verify_all.sh --changed [BASE] [--dry-run]   # BASE defaults to next; diffs from merge-base(BASE, HEAD)
  sh tools/verify_all.sh --dry-run                      # no --changed: everything runs, as with no flag
  sh tools/verify_all.sh --dry-run --files PATH ...     # the plan for a given list of changed paths (tests)

verify_all.sh runs this with its own arguments and reads the last line, SELECT ALL | SELECT ID ... | SELECT (nothing).

The map lives beside the code it describes:
  tools/verify_all.sh   `if want ID; then  #@ watch: PATTERNS  needs: IDS` opens a section and `fi  #@ end ID` closes it.
                        Its plumbing block (`#@ plumbing` .. `#@ plumbing end`) holds `#@ group @NAME = PATTERNS` and
                        `#@ none: PATTERNS` (paths no test exercises: docs).
  tools/verify.d/X.sh   `# watch: PATTERNS` (one or more lines) and an optional `# needs: IDS`. The script is always
                        watched by itself. Its ID is its file name.
Patterns are repo-relative: * stays inside a directory, ** crosses them, a leading ! excludes.

Changed paths are `git diff merge-base(BASE, HEAD)` (committed and uncommitted) plus untracked files. A path runs
every section and script that watches it; `needs:` adds what those read from earlier sections. A path nothing watches
runs nothing when `none:` matches it, and everything otherwise ("unmapped: PATH"). verify_all.sh and verify.d/*.sh are
read line by line instead: a comment or blank line in verify_all.sh runs nothing, a `#@` or plumbing line runs the
selector test (verify_select.sh), a line inside a section runs that section, and any other line (the preamble: ok/bad,
CAD_LAYER_CHECK, ...) runs everything. In a verify.d script a code line runs the script, a comment line (its header)
the selector test. Any change to either file also runs the selector test, which checks the map itself.
"""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VA = "tools/verify_all.sh"
VD = "tools/verify.d"
SELFTEST = "verify_select.sh"
ALL = "ALL"


def glob_re(p):
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif p.startswith("**", i):
            out, i = out + ".*", i + 2
        elif p[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif p[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(p[i]), i + 1
    return re.compile(out + r"\Z")


class Patterns:
    def __init__(self, pats):
        self.pats = list(pats)
        self.pos = [(p, glob_re(p)) for p in self.pats if not p.startswith("!")]
        self.neg = [glob_re(p[1:]) for p in self.pats if p.startswith("!")]

    def match(self, path):
        """The first positive pattern matching path, unless an exclusion matches it."""
        if any(n.match(path) for n in self.neg):
            return None
        return next((p for p, r in self.pos if r.match(path)), None)


def keyvals(s):
    """'watch: a b  needs: 3' -> {'watch': ['a', 'b'], 'needs': ['3']}"""
    return {k: v.split() for k, v in re.findall(r"(\w+):\s*(.*?)(?=\s+\w+:\s|\s*$)", s.strip())}


SEC_OPEN = re.compile(r"^if want (\S+); then\s+#@(.*)$")
SEC_END = re.compile(r"^fi\s+#@ end (\S+)\s*$")


def parse_verify_all(text):
    """{'units': [...], 'groups': {...}, 'none': [...], 'region': [None, kind per line 1..n]}.
    region kinds: ('sec', ID), ('plumbing',), ('global',)."""
    lines = text.split("\n")
    groups, none, units, region = {}, [], [], [None]
    cur, plumb = None, False
    for n, l in enumerate(lines, 1):
        m, e = SEC_OPEN.match(l), SEC_END.match(l)
        if l.strip() == "#@ plumbing":
            plumb = True
        if m:
            if cur:
                raise ValueError("%s:%d: section %s opens inside %s" % (VA, n, m.group(1), cur["id"]))
            kv = keyvals(m.group(2))
            cur = {"id": m.group(1), "kind": "section", "watch": kv.get("watch", []), "needs": kv.get("needs", []),
                   "start": n, "body": []}
            units.append(cur)
            region.append(("plumbing",))
            continue
        if e:
            if not cur or e.group(1) != cur["id"]:
                raise ValueError("%s:%d: end %s without its open" % (VA, n, e.group(1)))
            cur["end"] = n
            cur = None
            region.append(("plumbing",))
            continue
        if cur:
            cur["body"].append(l)
            region.append(("sec", cur["id"]))
        elif plumb or "#@" in l:
            region.append(("plumbing",))
        else:
            region.append(("global",))
        g = re.match(r"^#@ group (@\S+) = (.*)$", l)
        if g:
            groups[g.group(1)] = g.group(2).split()
        nm = re.match(r"^#@ none:(.*)$", l)
        if nm:
            none += nm.group(1).split()
        if l.strip() == "#@ plumbing end":
            plumb = False
    if cur:
        raise ValueError("%s: section %s never ends" % (VA, cur["id"]))
    return {"units": units, "groups": groups, "none": none, "region": region}


def parse_script(name, text):
    w, nd = [], []
    for l in text.split("\n"):
        m = re.match(r"^#\s*(watch|needs):(.*)$", l)
        if m:
            (w if m.group(1) == "watch" else nd).extend(m.group(2).split())
    return {"id": name, "kind": "script", "watch": w + ["%s/%s" % (VD, name)], "needs": nd, "body": text.split("\n"),
            "has_watch": bool(w)}


def expand(pats, groups, seen=()):
    out = []
    for p in pats:
        neg = p.startswith("!")
        q = p[1:] if neg else p
        if q.startswith("@"):
            if q not in groups or q in seen:
                raise ValueError("unknown or recursive group %s" % q)
            out += ["!" + x if neg else x for x in expand(groups[q], groups, seen + (q,))]
        else:
            out.append(p)
    return out


def load(root=ROOT):
    va = parse_verify_all(open(os.path.join(root, VA)).read())
    units = list(va["units"])
    d = os.path.join(root, VD)
    for f in sorted(os.listdir(d)):
        if f.endswith(".sh"):
            units.append(parse_script(f, open(os.path.join(d, f)).read()))
    for u in units:
        u["pats"] = Patterns(expand(u["watch"], va["groups"]))
    ids = [u["id"] for u in units]
    for u in units:
        for x in u["needs"]:
            if x not in ids:
                raise ValueError("%s needs %s, which is not a section or script" % (u["id"], x))
    return {"units": units, "ids": ids, "none": Patterns(va["none"]), "region": va["region"], "groups": va["groups"]}


# ------------------------------------------------------------------ changes

def git(*a, root=ROOT):
    return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, check=True).stdout


def parse_u0(diff):
    """git diff -U0 -> [(sign, [new-file line numbers it sits at], text)]. A removed line sits at the new lines that
    replaced it, or between the two new lines around a pure deletion."""
    out, cur, span = [], 0, []
    for l in diff.split("\n"):
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", l)
        if m:
            c, k = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            cur, span = c, ([c, c + 1] if k == 0 else list(range(c, c + k)))
        elif l.startswith(("+++", "---", "\\")) or not span:
            continue
        elif l.startswith("+"):
            out.append(("+", [cur], l[1:]))
            cur += 1
        elif l.startswith("-"):
            out.append(("-", span, l[1:]))
    return out


def line_mapped(path):
    return path == VA or (path.startswith(VD + "/") and path.endswith(".sh") and path.count("/") == 2)


def changes_from_git(base, root=ROOT):
    """(merge-base, {path: None | [(sign, lines, text)]}): line lists for the tracked line-mapped files."""
    try:
        mb = git("merge-base", base, "HEAD", root=root).strip()
    except subprocess.CalledProcessError:
        raise SystemExit("verify_all --changed: no merge-base with %r (pass --changed BASE)" % base)
    paths = set(git("diff", "--name-only", "--no-renames", mb, root=root).split("\n"))
    paths |= set(git("ls-files", "--others", "--exclude-standard", root=root).split("\n"))
    paths.discard("")
    ch = {}
    for p in sorted(paths):
        tracked = os.path.exists(os.path.join(root, p)) and git("ls-tree", "--name-only", mb, "--", p, root=root).strip()
        ch[p] = parse_u0(git("diff", "-U0", "--no-renames", mb, "--", p, root=root)) if line_mapped(p) and tracked else None
    return mb, ch


# ------------------------------------------------------------------ plan

def plan(m, changes):
    """changes: {path: None | [(sign, lines, text)]}. Returns {'all': [why] | [], 'run': {id: [why]}, 'none': [path]}."""
    run, allw, none = {}, [], []
    add = lambda i, why: run.setdefault(i, []).append(why)
    reg = m["region"]
    for p, lines in sorted(changes.items()):
        if lines is not None and p == VA:
            for sign, at, text in lines:
                t = text.strip()
                if "#@" in t:
                    add(SELFTEST, "%s line %d (map / plumbing)" % (p, at[0]))
                elif not t or t.startswith("#"):
                    continue
                else:
                    for n in at:
                        r = reg[min(max(n, 1), len(reg) - 1)]
                        if r[0] == "sec":
                            add(r[1], "%s line %d (in section %s)" % (p, n, r[1]))
                        elif r[0] == "plumbing":
                            add(SELFTEST, "%s line %d (map / plumbing)" % (p, n))
                        else:
                            allw.append("%s line %d is outside every section: %s" % (p, n, t[:60]))
                    add(SELFTEST, "%s changed" % p)
            continue
        if lines is not None:
            name = p.split("/")[-1]
            for sign, at, text in lines:
                t = text.strip()
                if not t:
                    continue
                add(SELFTEST, "%s changed" % p)
                if not t.startswith("#") and name in m["ids"]:
                    add(name, "%s line %d" % (p, at[0]))
            continue
        hit = False
        for u in m["units"]:
            pat = u["pats"].match(p)
            if pat:
                add(u["id"], p if pat == p else "%s (%s)" % (p, pat))
                hit = True
        if not hit:
            if m["none"].match(p):
                none.append(p)
            else:
                allw.append("unmapped: %s" % p)
    # what the selected units read from earlier sections
    need = {u["id"]: u["needs"] for u in m["units"]}
    todo = list(run)
    while todo:
        i = todo.pop()
        for x in need.get(i, []):
            if x not in run:
                todo.append(x)
            add(x, "needed by %s" % i)
    return {"all": allw, "run": run, "none": none}


def render(m, pl, head):
    out = [head]
    ids = m["ids"]
    if pl["all"]:
        out += ["  %s" % w for w in pl["all"]]
        out.append("run   everything (%d sections and scripts)" % len(ids))
        out.append("SELECT ALL")
        return out
    for i in ids:
        if i in pl["run"]:
            why = list(dict.fromkeys(pl["run"][i]))
            out.append("run   %-22s %s%s" % (i, "; ".join(why[:3]), " (+%d more)" % (len(why) - 3) if len(why) > 3 else ""))
    skip = [i for i in ids if i not in pl["run"]]
    if pl["none"]:
        out.append("no tests for: %s" % " ".join(pl["none"]))
    if not pl["run"]:
        out.append("no tests affected")
    elif skip:
        out.append("skip  %s" % " ".join(skip))
    out.append("SELECT " + " ".join(i for i in ids if i in pl["run"]))
    return out


def main(argv):
    changed, base, dry, files = False, "next", False, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--changed":
            changed = True
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                base, i = argv[i + 1], i + 1
        elif a == "--dry-run":
            dry = True
        elif a == "--files":
            changed, files = True, argv[i + 1:]
            break
        else:
            print("usage: sh tools/verify_all.sh [--changed [BASE]] [--dry-run] [--files PATH ...]\n"
                  "verify_select: unknown argument %r" % a)
            return 2
        i += 1
    try:
        m = load()
    except ValueError as e:
        print("verify_select: %s" % e)
        return 2
    if not changed:
        print("verify_all: no --changed, so every section and script runs:\n  %s" % " ".join(m["ids"]))
        print("SELECT ALL")
        return 0
    if files is not None:
        ch, head = {p: None for p in files}, "verify_all --changed: %d given paths" % len(files)
    else:
        mb, ch = changes_from_git(base)
        head = "verify_all --changed %s: %d changed paths since %s (merge-base of %s and HEAD; committed, uncommitted, untracked)" % (
            base, len(ch), mb[:9], base)
    print("\n".join(render(m, plan(m, ch), head)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
