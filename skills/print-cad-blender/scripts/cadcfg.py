"""cadcfg: checks.json hygiene for cadcheck. Plain python3, no Blender (cadcheck imports it; tools/verify.d tests it).

    unknown_keys(cfg, defaults, rows, named)    keys cadcheck never reads, each with the closest known key
    accepts(a, w) / triage(acc, warns, ran)     accepted_warns: check + kind (+ object), or the old substring form
    literal(path, name)                         a module-level literal (DEFAULTS, CONFIG_ROWS) read without importing

The known keys are cadcheck's DEFAULTS (top level, and the members of a dict section), CONFIG_ROWS (row fields) and
printcheck.py DEFAULTS (the "printcheck" section). reference/checks-config.md documents the same set; the verify test
holds the two together.

Why: a typo'd key was ignored without a word. "flexure" for "flexures" gave a PASS that checked nothing (push-assist
PA-A4-T6). An accept was a substring of the warn text, so "PRT_tray_L: " accepted every warn on the part, including later
ones of another kind, and under --only no stale accept was ever reported (PA-A4-T10).
"""
import ast, difflib, re

NOTE = "_"                                   # "_about", "_source": notes for people, never read
COMMON = ("why", "name", "past_limit_ok")    # any row may carry these
OBJ = re.compile(r"(?<![\w-])(?:PRT|BUY|FST|CAB|PIV)_[\w.-]*")
# words that say where or how much, not what is wrong; trimmed from the ends of a suggested kind
_FILLER = {"a", "an", "the", "of", "to", "at", "on", "in", "x", "z", "mm", "mm2", "mm3", "deg", "model", "print", "world",
           "min", "max", "and", "with", "by", "is", "+"}


def literal(path, name):
    """The literal assigned to `name` at module level in a source file (cadcheck.py, printcheck.py import bpy or numpy)."""
    with open(path) as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise KeyError("%s: no module-level %s" % (path, name))


def closest(k, known):
    m = difflib.get_close_matches(str(k), sorted(known), n=1, cutoff=0.6)
    return m[0] if m else None


def row_label(r):
    """How a row is named in a message: its name, op, step, part or object, or "a to b"."""
    for k in ("name", "op", "step", "part", "object", "check"):
        if isinstance(r.get(k), str):
            return r[k]
    if r.get("a") or r.get("b"):
        return "%s to %s" % (r.get("a", "*"), r.get("b", "*"))
    return r.get("match") if isinstance(r.get("match"), str) else None


def unknown_keys(cfg, defaults, rows, named):
    """[(where, key, closest)] for each key in one config file that cadcheck does not read. defaults: the known top-level
    keys and, for a dict section, its members; rows: {section: row fields} ("section.sub" for a dict or list of dicts
    inside a row; for a dict section, members beyond defaults); named: sections keyed by object or joint name."""
    out = []

    def chk(d, known, where):
        for k in d:
            if not (isinstance(k, str) and k.startswith(NOTE)) and k not in known:
                out.append((where, k, closest(k, known)))

    def row(r, sec, where, top=True):
        lab = row_label(r) if top else None
        where = "%s (%s)" % (where, lab) if lab else where
        chk(r, set(rows[sec]) | set(COMMON), where)
        for k, sub in r.items():     # "drop_tests.expect", then "drop_tests.expect.angle", ...
            if sec + "." + k in rows:
                for j, s in enumerate(sub if isinstance(sub, list) else [sub]):
                    if isinstance(s, dict):
                        row(s, sec + "." + k, "%s.%s" % (where, k) + ("[%d]" % j if isinstance(sub, list) else ""), False)

    chk(cfg, set(defaults), "top level")
    for sec, v in cfg.items():
        if sec not in defaults:
            continue
        if isinstance(v, list) and sec in rows:
            for i, r in enumerate(v):
                if isinstance(r, dict):
                    row(r, sec, "%s[%d]" % (sec, i))
        elif isinstance(v, dict) and sec in named:
            if sec in rows:      # joints, couplings: {name: row}
                for n, r in v.items():
                    if isinstance(r, dict):
                        row(r, sec, "%s.%s" % (sec, n))
        elif isinstance(v, dict) and isinstance(defaults[sec], dict):
            chk(v, set(defaults[sec]) | set(rows.get(sec, ())), sec)
    return out


def unknown_msgs(src, cfg, defaults, rows, named):
    return ["%s %s: unknown key '%s', ignored%s" % (src, where, k, " (did you mean '%s'?)" % c if c else "")
            for where, k, c in unknown_keys(cfg, defaults, rows, named)]


# ------------------------------------------------------------------ accepted_warns

def _obj_re(o):
    """An object name as a whole token; * and ? and [..] glob over a family (tools/bench/replay.py's locator rule)."""
    out, i = "", 0
    while i < len(o):
        c = o[i]
        if c == "*":
            out += r"[\w.-]*"
        elif c == "?":
            out += r"\w"
        elif c == "[" and "]" in o[i:]:
            j = o.index("]", i)
            out += o[i:j + 1]
            i = j
        else:
            out += re.escape(c)
        i += 1
    return re.compile(r"(?<![\w-])" + out + r"(?![\w-])")


def structured(a):
    return "check" in a or "kind" in a or "object" in a


def _bare(msg):
    """The message with object names blanked out, so a kind can't match inside one ("bridge" in PRT_bridge_plate)."""
    return OBJ.sub(lambda m: " " * len(m.group()), msg)


def _has_number(t):
    return re.search(r"\d", _bare(t)) is not None


def accepts(a, w, loose=False):
    """True when accept `a` covers warn line w ("check: message"). Structured: the check is w's, kind is whole words of
    the message outside object names, each object is a whole token of it, and "match" (if given) is in w. A warn with a
    measured value needs "match" (which pins it) or "any": true: an accept that drops the number also takes a worse
    warn of the same kind (PR #10 review: the demo base's wall at 1.2 mm under an accept written for 2.21; 6 of 8
    worsened push-assist variants). loose skips that rule. Old form: a["match"] is anywhere in w."""
    if not structured(a):
        return bool(a.get("match")) and a["match"] in w
    chk, _, msg = w.partition(": ")
    k = a.get("kind")
    if chk != a.get("check") or not isinstance(k, str) or not k.strip() or \
            not re.search(r"(?<!\w)%s(?!\w)" % re.escape(k), _bare(msg)):
        return False
    objs = a.get("object") or []
    if not all(_obj_re(o).search(msg) for o in ([objs] if isinstance(objs, str) else objs)):
        return False
    if "match" in a:
        return isinstance(a["match"], str) and a["match"] in w
    return loose or bool(a.get("any")) or not _has_number(msg)


def accept_label(a):
    if not structured(a):
        return a.get("match")
    o = a.get("object")
    return "%s: %s%s%s" % (a.get("check"), "%s " % (o if isinstance(o, str) else " ".join(o)) if o else "", a.get("kind"),
                           " ('%s')" % a["match"] if isinstance(a.get("match"), str) else "")


def _trim(t):
    """Drop where-and-how-much words from both ends: " a 26.7 mm bridge at z " -> "bridge"."""
    words = t.split()
    while words and words[0].lower().strip(".'?+") in _FILLER:
        words.pop(0)
    while words and words[-1].lower().strip(".'?+") in _FILLER:
        words.pop()
    return " ".join(words).strip(" .'?+")


def _letters(t):
    return sum(c.isalpha() for c in t)


def templates(path):
    """{check: [fixed text of its finding() messages]} from a source file: the words every warn of a kind has.
    "%s: %d wall samples < %.1f mm (min %.2f)" gives " wall samples ", " mm "."""
    with open(path) as f:
        tree = ast.parse(f.read())
    out = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "finding" and len(node.args) >= 3
                and isinstance(node.args[0], ast.Constant)):
            continue
        for c in ast.walk(node.args[2]):
            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                for piece in re.split(r"%[-#0 +]*\d*(?:\.\d+)?[sdfgrx]|[\d:()\[\]=,;<>'\"]+", c.value.replace("%%", "%")):
                    if piece.strip() and piece not in out.setdefault(node.args[0].value, []):
                        out[node.args[0].value].append(piece)
    return out


def warn_kind(msg):
    """Without templates: the first stretch of 6+ letters between numbers, object and row names, quoted labels, poses
    and brackets, trimmed of where-and-how-much words."""
    segs = [x for x in re.split(r"%s|'[^']*'|\w*_\w*|\w+=\S*|[\d:()\[\]=,;<>]+" % OBJ.pattern, msg) if x.strip()]
    trimmed = [t for t in map(_trim, segs) if t and t in msg]
    return next((t for t in trimmed if _letters(t) >= 6), None) or max(trimmed, key=_letters, default="") or \
        max((x.strip() for x in segs), key=_letters, default="")


def kind_of(check, msg, tmpl=None):
    """The kind for an accept of this warn, from the fixed text of the check's messages (templates) found in it as
    whole words: the first with 7+ letters once trimmed ("wall samples", "slides out but with only"); else what
    warn_kind finds ("bridge" in a layer-check message, which printcheck words); else the longest piece ("mm at" for a
    clearance). Always a substring of msg."""
    def at(t):
        m = re.search(r"(?<!\w)%s(?!\w)" % re.escape(t), msg)
        return m.start() if m else -1
    pieces = (tmpl or {}).get(check, [])
    trimmed = sorted({t for t in map(_trim, pieces) if _letters(t) >= 3 and at(t) >= 0}, key=at)
    wk = warn_kind(msg)
    return next((t for t in trimmed if _letters(t) >= 7), None) or (wk if _letters(wk) >= 6 else None) or \
        max(trimmed, key=_letters, default="") or max((p.strip() for p in pieces if _letters(p) >= 2 and at(p.strip()) >= 0),
                                                     key=_letters, default="") or wk


def suggest(a, warns, tmpl=None):
    """The structured accepts that cover what an old substring accept covers in this run: one per (check, objects,
    kind). Objects are those the match names (a partial name becomes a glob), else the warn's first object."""
    out = []
    for w in warns:
        if not accepts(a, w):
            continue
        chk, _, msg = w.partition(": ")
        objs = []
        for t in OBJ.findall(a["match"]):
            objs.append(t if _obj_re(t).search(msg) else t + "*")
        if not objs:
            objs = OBJ.findall(msg)[:1]
        s = {"check": chk, "kind": kind_of(chk, msg, tmpl)}
        if objs:
            s["object"] = objs[0] if len(objs) == 1 else objs
        if _has_number(a["match"]):
            s["match"] = a["match"]     # it pinned a number: keep it, so a worse value is a new warn
        elif _has_number(msg) or not objs:
            s["any"] = True             # it took any value (or any part): say so
        if a.get("why"):
            s["why"] = a["why"]
        if s not in out:
            out.append(s)
    return out


def accept_problems(acc, checks):
    """Config warns for malformed accepts: a structured one with no check or kind, a check that is not one, or no
    object without "any": true (it takes the kind on every part)."""
    out = []
    for i, a in enumerate(acc):
        if not isinstance(a, dict):
            out.append("accepted_warns[%d]: not an object, ignored" % i)
        elif structured(a):
            if not a.get("check") or not a.get("kind"):
                out.append("accepted_warns[%d] (%s): needs both \"check\" and \"kind\", so it accepts nothing" % (i, accept_label(a)))
            elif a["check"] not in checks:
                c = closest(a["check"], checks)
                out.append("accepted_warns[%d]: check '%s' is not a check, so it accepts nothing%s" % (
                    i, a["check"], " (did you mean '%s'?)" % c if c else ""))
            if not a.get("object") and not a.get("any"):
                out.append("accepted_warns[%d] (%s): no \"object\", so it takes this kind of warn on every part; name the "
                           "object, or say \"any\": true" % (i, accept_label(a)))
        elif not a.get("match"):
            out.append("accepted_warns[%d]: no \"match\" and no \"check\"/\"kind\", so it accepts nothing" % i)
    return out


def triage(acc, warns, ran, never=("build: ",)):
    """Sort the warns into accepted / untriaged and the accepts into used / stale / not evaluated.
    ran: the checks that ran (None: all of them). An accept whose check did not run is not evaluated; an old substring
    accept names no check, so under --only one that matched nothing is not evaluated either."""
    acc = [a for a in acc if isinstance(a, dict)]
    accepted, unpinned = {}, []
    for w in warns:
        if w.startswith(never):     # a stale model is never accepted
            continue
        a = next((a for a in acc if accepts(a, w)), None)
        if a is not None:
            accepted[w] = a.get("why", "")
            continue
        a = next((a for a in acc if structured(a) and accepts(a, w, loose=True)), None)
        if a is not None:
            unpinned.append("accepted_warns[%d] (%s) would take '%s' but for its measured value: add \"match\" with the "
                            "text you accept (it pins the number), or \"any\": true" % (acc.index(a), accept_label(a), w))
    stale, not_eval, legacy = [], [], []
    for a in acc:
        hit = [w for w in warns if not w.startswith(never) and accepts(a, w)]
        if not structured(a):
            legacy.append({"match": a.get("match"), "why": a.get("why"), "accepts": len(hit)})
        if hit:
            continue
        if ran is None or (structured(a) and a.get("check") in ran):
            stale.append(accept_label(a))
        else:
            not_eval.append(accept_label(a))
    return {"accepted": accepted, "untriaged": [w for w in warns if w not in accepted], "stale": stale,
            "not_evaluated": not_eval, "legacy": legacy, "unpinned": unpinned}


def legacy_msg(legacy, n_acc, warns, tmpl=None):
    """One config warn for the old substring accepts; each entry of `legacy` gets "use", the structured accepts that
    cover what it covers in this run."""
    if not legacy:
        return None
    for x in legacy:
        x["use"] = suggest(x, warns, tmpl) if x["accepts"] else []
    wide = [x for x in legacy if len({(s["check"], s["kind"]) for s in x["use"]}) > 1]
    return ("accepted_warns: %d of %d entries use the old substring \"match\" (deprecated: it accepts any warn containing "
            "the text%s). Write {\"check\", \"kind\", \"object\", \"why\"} (plus \"match\" to pin a number, or \"any\": true) "
            "instead; summary.accept_suggestions has the form for each one that matched a warn in this run" % (
                len(legacy), n_acc, "; %d of them accept warns of more than one kind, e.g. '%s'" % (len(wide), wide[0]["match"]) if wide else ""))


def only_problems(only, checks):
    return ["--only: '%s' is not a check, nothing ran for it%s" % (n, " (did you mean '%s'?)" % closest(n, checks) if closest(n, checks) else "")
            for n in sorted(only) if n not in checks]


def strip_jsonc(t):
    """JSON from jsonc: // comments dropped outside strings, "{...}" placeholders emptied, trailing commas removed."""
    out, i, ins = [], 0, False
    while i < len(t):
        c = t[i]
        if ins:
            out.append(c)
            if c == "\\":
                out.append(t[i + 1]); i += 1
            elif c == '"':
                ins = False
        elif c == '"':
            ins = True; out.append(c)
        elif t.startswith("//", i):
            while i < len(t) and t[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out).replace("{...}", "{}"))
