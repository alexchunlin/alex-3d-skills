#!/usr/bin/env python3
"""Static doc cost of the skills at any git ref: bytes and approximate tokens per doc and per section.

Tokens are characters / the chars-per-token ratio measured on the v1/v2 transcripts' own usage numbers
(tools/bench/tokens.json, written by `cc_transcript.py calibrate --write`: about 2.25 on these docs, not 4). No
tokenizer; if tokens.json is missing the ratio falls back to 4 and the output says so. A doc is 'always'
read when tools/bench/docs.json says so (the SKILL.md body and the docs it tells the agent to read unconditionally);
the rest are conditional. Sections are the markdown headings; inside a section, each bold-lead list item
("- **Name.** ...", "3. **Build ...**") and each tool-table row ("| `cad rows ...` | ...") is an item of its own, so a
feature PR can see what its paragraph costs every session.

  python3 -I tools/bench/doccost.py                     # HEAD: per doc, always-read total per role
  python3 -I tools/bench/doccost.py origin/next --sections
  python3 -I tools/bench/doccost.py HEAD --base origin/next   # "adds N always-read tokens", per doc and section
  python3 -I tools/bench/doccost.py HEAD --json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = json.load(open(Path(__file__).resolve().parent / "docs.json"))

def _ratio() -> tuple[float, str]:
    try:
        d = json.load(open(Path(__file__).resolve().parent / "tokens.json"))
        return float(d["chars_per_token"]), "measured: median of %d doc reads, IQR %s (tools/bench/tokens.json)" % (d["n"], d["iqr"])
    except Exception:
        return 4.0, "DEFAULT 4.0: tools/bench/tokens.json missing, run cc_transcript.py calibrate --write"


CHARS_PER_TOKEN, TOKENS_SOURCE = _ratio()

HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
ITEM_RE = re.compile(r"^(?:\s*[-*]|\s*\d+\.)\s+\*\*(.+?)\*\*")
TROW_RE = re.compile(r"^\|(?!\s*-{3})\s*`?([^`|]+?)`?\s*\|")   # a table row (not the --- rule); the first cell is its title


def git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *a], check=True, capture_output=True, text=True).stdout


def tok(n_chars: int) -> int:
    return int(round(n_chars / CHARS_PER_TOKEN))


def docs_at(ref: str) -> dict[str, str]:
    """{path: text} for every .md under skills/ at ref ('WORKTREE' reads the working tree)."""
    if ref == "WORKTREE":
        return {str(p.relative_to(ROOT)): p.read_text() for p in sorted((ROOT / "skills").rglob("*.md"))}
    paths = [p for p in git("ls-tree", "-r", "--name-only", ref, "--", "skills").splitlines() if p.endswith(".md")]
    return {p: git("show", "%s:%s" % (ref, p)) for p in paths}


def sections(text: str) -> list[dict]:
    """[{title, level, chars, items: [{title, chars}]}]; text before the first heading is '(front matter)'."""
    out = [{"title": "(front matter)", "level": 0, "chars": 0, "items": [], "text": ""}]
    fence = False
    item = None
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fence = not fence
        m = None if fence else HEAD_RE.match(line)
        if m:
            out.append({"title": m.group(2).strip(), "level": len(m.group(1)), "chars": len(line), "items": [], "text": line})
            item = None
            continue
        out[-1]["chars"] += len(line)
        out[-1]["text"] += line
        if not fence:
            im = ITEM_RE.match(line) or TROW_RE.match(line)
            if im:
                item = {"title": im.group(1).strip().rstrip(".:"), "chars": 0, "text": ""}
                out[-1]["items"].append(item)
            elif not line.strip() or re.match(r"^([-*]|\d+\.)\s", line) or line.startswith("|"):
                item = None   # a blank line, a plain top-level bullet or another table row ends the item
        if item is not None:
            item["chars"] += len(line)
            item["text"] += line
    if out[0]["chars"] == 0:
        out.pop(0)
    return out


def classify(path: str) -> tuple[str, str]:
    if path in CONF["always"]:
        return "always", CONF["always"][path]
    if path in CONF["conditional"]:
        return "conditional", CONF["conditional"][path]
    return "unclassified", "not in tools/bench/docs.json: counted as conditional"


def role_of(path: str) -> str | None:
    m = re.match(r"skills/([^/]+)/", path)
    return CONF["skills"].get(m.group(1), {}).get("role") if m else None


def report(ref: str, keep_text: bool = False) -> dict:
    docs = docs_at(ref)
    rows = []
    for p, t in sorted(docs.items()):
        cls, why = classify(p)
        strip = (lambda d: d) if keep_text else (lambda d: {k: v for k, v in d.items() if k != "text"})
        rows.append({"path": p, "role": role_of(p), "class": cls, "why": why, "bytes": len(t.encode()), "chars": len(t),
                     "tokens": tok(len(t)), "sections": [strip({**s, "tokens": tok(s["chars"]),
                                                                "items": [strip({**i, "tokens": tok(i["chars"])}) for i in s["items"]]})
                                                         for s in sections(t)]})
    per_role = {}
    for r in rows:
        if r["class"] == "always" and r["role"]:
            per_role[r["role"]] = per_role.get(r["role"], 0) + r["tokens"]
    return {"ref": ref, "commit": git("rev-parse", "--short=9", ref).strip() if ref != "WORKTREE" else "WORKTREE",
            "chars_per_token": CHARS_PER_TOKEN, "tokens_source": TOKENS_SOURCE, "docs": rows, "always_tokens_per_session": per_role,
            "always_tokens_total": sum(per_role.values())}


def print_report(rep: dict, show_sections: bool) -> None:
    print("doc cost at %s (%s); tokens ~ chars/%g (%s)" % (rep["ref"], rep["commit"], rep["chars_per_token"], rep["tokens_source"]))
    print("| doc | role | read | bytes | ~tokens |\n|---|---|---|---|---|")
    for r in rep["docs"]:
        print("| %s | %s | %s | %d | %d |" % (r["path"], r["role"] or "-", r["class"], r["bytes"], r["tokens"]))
    print("always-read per session: " + ", ".join("%s %d tokens" % kv for kv in rep["always_tokens_per_session"].items()))
    if show_sections:
        for r in rep["docs"]:
            print("\n%s (%s, %d tokens)" % (r["path"], r["class"], r["tokens"]))
            for s in r["sections"]:
                print("  %5d  %s%s" % (s["tokens"], "  " * max(0, s["level"] - 1), s["title"][:90]))
                for i in s["items"]:
                    print("  %5d  %s  - %s" % (i["tokens"], "  " * max(0, s["level"] - 1), i["title"][:86]))


def diff(new: dict, old: dict) -> dict:
    o = {r["path"]: r for r in old["docs"]}
    n = {r["path"]: r for r in new["docs"]}
    rows = []
    for p in sorted(set(o) | set(n)):
        a, b = o.get(p), n.get(p)
        cls = (b or a)["class"]
        d = (b["tokens"] if b else 0) - (a["tokens"] if a else 0)
        secs = []
        if d or (a and b and a["sections"] != b["sections"]):
            sa = {s["title"]: s["tokens"] for s in (a["sections"] if a else [])}
            sb = {s["title"]: s["tokens"] for s in (b["sections"] if b else [])}
            for t in list(dict.fromkeys(list(sb) + list(sa))):
                if sb.get(t, 0) != sa.get(t, 0):
                    secs.append({"section": t, "old": sa.get(t, 0), "new": sb.get(t, 0), "delta": sb.get(t, 0) - sa.get(t, 0)})
        if d or secs:
            rows.append({"path": p, "class": cls, "old": a["tokens"] if a else 0, "new": b["tokens"] if b else 0, "delta": d,
                         "sections": secs})
    roles = set(new["always_tokens_per_session"]) | set(old["always_tokens_per_session"])
    return {"ref": new["ref"], "base": old["ref"], "docs": rows,
            "always_delta_per_session": {r: new["always_tokens_per_session"].get(r, 0) - old["always_tokens_per_session"].get(r, 0)
                                         for r in sorted(roles)}}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ref", nargs="?", default="HEAD", help="git ref, or WORKTREE for uncommitted docs")
    p.add_argument("--base", help="compare with this ref: always-read tokens added per session")
    p.add_argument("--sections", action="store_true")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    rep = report(a.ref)
    if a.base:
        d = diff(rep, report(a.base))
        if a.json:
            print(json.dumps(d, indent=1))
            return 0
        print("doc cost %s vs %s (tokens ~ chars/%g, %s)" % (a.ref, a.base, CHARS_PER_TOKEN, TOKENS_SOURCE))
        for role, v in d["always_delta_per_session"].items():
            print("  %s: %+d always-read tokens per session" % (role, v))
        for r in d["docs"]:
            print("  %-52s %-12s %6d -> %6d (%+d)" % (r["path"], r["class"], r["old"], r["new"], r["delta"]))
            for s in r["sections"]:
                print("      %+6d  %s" % (s["delta"], s["section"][:80]))
        return 0
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        print_report(rep, a.sections)
    return 0


if __name__ == "__main__":
    sys.exit(main())
