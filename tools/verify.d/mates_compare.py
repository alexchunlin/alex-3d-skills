"""Compare two cadcheck reports of the same design built two ways (absolute coordinates vs mates). Plain python3.

    python3 -I tools/verify.d/mates_compare.py abs/cadcheck.json mates/cadcheck.json
Prints CMP PASS|FAIL lines: fails and warns, the fail and warn lists, and every row (cad rows). Where a minimum is a
tie (a disc's clearance is the same at every pan angle), the two builds may report another pose or point for the same
value; those fields (pose, at, bridge_at, "at pan=...") are masked and counted, never the values.
"""
import json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "skills", "print-cad-blender", "scripts"))
import cadrows

MASK = [(re.compile(r"\b(pose|at|bridge_at)=\S+"), r"\1=*"), (re.compile(r" at (\w+)=-?[\d.]+"), r" at \1=*")]


def mask(s):
    for rx, rep in MASK:
        s = rx.sub(rep, s)
    return s


a, b = (json.load(open(p)) for p in sys.argv[1:3])
sa, sb = a["summary"], b["summary"]
print("CMP %s fails/warns %d/%d vs %d/%d" % ("PASS" if (sa["fails"], sa["warns"]) == (sb["fails"], sb["warns"]) else "FAIL",
                                             sa["fails"], sa["warns"], sb["fails"], sb["warns"]))
print("CMP %s fail lists identical (%d)" % ("PASS" if sa["fail_list"] == sb["fail_list"] else "FAIL", len(sa["fail_list"])))
wa, wb = sorted(sa["warn_list"]), sorted(sb["warn_list"])
same = sum(x in wb for x in wa)
print("CMP %s warn lists: %d of %d verbatim, all %d equal with tie poses masked" % (
    "PASS" if sorted(map(mask, wa)) == sorted(map(mask, wb)) else "FAIL", same, len(wa), len(wa)))
ra, rb = sorted(cadrows.report_rows(a, set())), sorted(cadrows.report_rows(b, set()))
same = len(set(ra) & set(rb))
ma, mb = sorted(map(mask, ra)), sorted(map(mask, rb))
print("CMP %s rows: %d vs %d, %d verbatim, the rest equal with tie poses/points masked" % (
    "PASS" if ma == mb else "FAIL", len(ra), len(rb), same))
for x, y in zip(ma, mb):
    if x != y:
        print("  differs:\n    %s\n    %s" % (x[:200], y[:200]))
