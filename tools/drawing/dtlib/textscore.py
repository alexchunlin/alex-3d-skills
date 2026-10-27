"""Score text reads against hand labels (tools/verify.d/drawing_labels/<id>.json).

A read matches a label when its normalised text equals the label's (textparse.canon: case, spaces, Ø/° misreads)
and the boxes touch (centre distance under 60 px or overlap). Greedy, one-to-one.
"""
from __future__ import annotations
import re
from .textparse import canon


def _touch(a, b, tol=60):
    ca = ((a[0] + a[2]) / 2, (a[1] + a[3]) / 2); cb = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    if abs(ca[0] - cb[0]) < tol and abs(ca[1] - cb[1]) < tol:
        return True
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def is_dim(t):
    return bool(re.search(r"\d", t)) and len(t) <= 24


def score(pred, labels):
    """pred: [{'t','b'}]; labels: [{'t','b'}]. Returns dict with tp, n_pred, n_lab, P, R and dims-only P, R."""
    def run(P, L):
        used = set(); tp = 0; misses = []
        for p in P:
            k = canon(p["t"])
            for j, l in enumerate(L):
                if j not in used and canon(l["t"]) == k and _touch(p["b"], l["b"]):
                    used.add(j); tp += 1; break
        misses = [L[j]["t"] for j in range(len(L)) if j not in used]
        return tp, misses
    tp, misses = run(pred, labels)
    Pd = [p for p in pred if is_dim(canon(p["t"]))]; Ld = [l for l in labels if is_dim(canon(l["t"]))]
    tpd, _ = run(Pd, Ld)
    f = lambda a, b: round(a / b, 3) if b else 0.0
    return {"tp": tp, "n_pred": len(pred), "n_lab": len(labels), "P": f(tp, len(pred)), "R": f(tp, len(labels)),
            "dim_tp": tpd, "dim_pred": len(Pd), "dim_lab": len(Ld), "dim_P": f(tpd, len(Pd)), "dim_R": f(tpd, len(Ld)),
            "missed": misses}
