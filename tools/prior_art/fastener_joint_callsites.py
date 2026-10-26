"""Count what the v2 designer's screw() wrapper costs at its call sites, and what features.fastener_joint would.

    python3 -I tools/prior_art/fastener_joint_callsites.py [HW/v2/blender/parts]

Reads base.py, launcher.py and pan_stage.py (read-only). For each screw(...) call: source lines and characters, and
the numbers worked out by hand (the length argument and every clamp=/sink= expression). The "after" column is the
same call rewritten mechanically as one fastener_joint call (same name/at/into/step/joint/head/sink source text,
the parts that were cut lists, the size), wrapped at 120 columns, which is this repo's and v2's line length.
"""
import ast, os, sys, textwrap

D = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/code-stuff/mmlauncher/mm-launcher/mm-launch-hw/v2/blender/parts")
tot = dict(defs=0, calls=0, lines=0, chars=0, hand=0, after_lines=0, after_chars=0)
for fn in ("base.py", "launcher.py", "pan_stage.py"):
    src = open(os.path.join(D, fn)).read()
    lines = src.splitlines()
    seg = lambda n: ast.get_source_segment(src, n)
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "screw":
            tot["defs"] += node.end_lineno - node.lineno + 1
            print("%s:%d def screw(...): %d lines" % (fn, node.lineno, node.end_lineno - node.lineno + 1))
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "screw"):
            continue
        n_lines = node.end_lineno - node.lineno + 1
        chars = len(seg(node))
        a = node.args
        kw = {k.arg: k.value for k in node.keywords}
        cut = kw.get("cut")
        hand = 1                                  # the length
        parts, heads, sinks = [], set(), set()
        for el in (cut.elts if isinstance(cut, ast.List) else []):
            kind, kwd, lst = el.elts
            parts.append(seg(lst))
            for k in getattr(kwd, "keywords", []):
                hand += k.arg in ("clamp", "sink")
                if k.arg == "head":
                    heads.add(seg(k.value))
                if k.arg == "sink":
                    sinks.add(seg(k.value))
        spec = seg(a[4]).strip('"')
        head = spec.split("_")[-1]
        kinds = {seg(el.elts[0]).strip('"') for el in (cut.elts if isinstance(cut, ast.List) else [])}
        host = seg(a[5])
        # all-clearance + no host = through-bolt (the hinge); a BUY_ host = tapped purchased part (the motor)
        style = ', style="tapped"' if "BUY_" in host and "clamp" not in kinds else (', style="nut"' if host == "None" else "")
        after = 'F.fastener_joint(%s, "M3", %s, %s, [%s]%s%s%s, step=%s%s, cuts=CUT)' % (
            seg(a[0]), seg(a[1]), seg(a[2]), ", ".join(parts), style, "" if head == "cap" else ', head="%s"' % head,
            ", sink=%s" % sinks.pop() if sinks else "", seg(a[6]), ", joint=%s" % seg(kw["joint"]) if "joint" in kw else "")
        indent = len(lines[node.lineno - 1]) - len(lines[node.lineno - 1].lstrip())
        wrapped = textwrap.wrap(after, 120 - indent, subsequent_indent="    ", break_long_words=False)
        tot["calls"] += 1
        tot["lines"] += n_lines
        tot["chars"] += chars
        tot["hand"] += hand
        tot["after_lines"] += len(wrapped)
        tot["after_chars"] += len(after)
        print("%s:%d %s: %d lines, %d chars, %d hand numbers -> %d lines, %d chars" % (
            fn, node.lineno, seg(a[0]), n_lines, chars, hand, len(wrapped), len(after)))
print("TOTAL wrapper defs %(defs)d lines; %(calls)d calls: %(lines)d lines, %(chars)d chars, %(hand)d hand numbers"
      " -> fastener_joint %(after_lines)d lines, %(after_chars)d chars, 0 hand numbers" % tot)
