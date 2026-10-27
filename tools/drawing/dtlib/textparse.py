"""Normalise OCR strings from mechanical drawings and parse them into dimension callouts.

General OCR has no diameter sign and misreads the degree sign; on these sheets RapidOCR reads
"Ø230" as "Q230" / "0230" / "@230" and "92.8°" as "92.8*". norm() undoes that; parse() splits a callout
into count ("4X", "(6X)"), kind (dia, radius, thread, chamfer, angle, linear, note), values and flags.
"""
from __future__ import annotations
import re

NUM = r"\d+(?:[.,]\d+)?"
_DIA_CHARS = "QDØøΦφ⌀@⊘β"
# arrowheads and dimension-line ends read as glyphs: "- 53.4", "T 114 -", "—130—", "R4 TYP.-"
_LEAD_JUNK = re.compile(r"^(?:[-—–_|+~:;,'`/\\]+\s*|T\s+(?=\d))")
_TAIL_JUNK = re.compile(r"(?:\s*[-—–_|~/:;,'`>]+|\s+T)$")
ARROW_ONLY = re.compile(r"^[T+|\-—–_~.]{1,3}$")


def clean(s: str) -> str:
    t = s.strip()
    for _ in range(3):
        t2 = _TAIL_JUNK.sub("", _LEAD_JUNK.sub("", t)).strip()
        if t2 == t:
            break
        t = t2
    t = re.sub(r"^D(?=THRU)", "", t)
    return t


def norm(s: str) -> str:
    t = clean(s)
    t = t.replace("×", "x").replace("Х", "X").replace("（", "(").replace("）", ")")
    t = t.replace("º", "°").replace("˚", "°")
    t = re.sub(r"\+\s*/?\s*-", "±", t)
    # diameter sign misreads at the start of a value: Q12, @12, 012 (a leading zero before a digit is never a value)
    t = re.sub(rf"(^|[\s(xX])[{_DIA_CHARS}]\s*(?=\d)", r"\1Ø", t)
    t = re.sub(r"(^|[\s(xX])[0O](?=[1-9]\d*(?:[.,]\d+)?(?:\s|$|[A-Za-z(]))", r"\1Ø", t)
    # degree sign: 45*, 45o, 45" at the end of a number
    t = re.sub(rf"({NUM})\s*[*°'\"·•˙](?=\s|$|[),xX(])", r"\1°", t)
    t = re.sub(rf"({NUM})\s*o(?=\s|$)", r"\1°", t)
    # count prefixes: "4 X", "4x" -> "4X "
    t = re.sub(r"^(\d+)\s*[xX]\s*(?=[ØRM]\s*\d)", r"\1X ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def canon(s: str) -> str:
    """Comparison key: normalised, upper case, no spaces."""
    return re.sub(r"\s+", "", norm(s).upper()).replace(",", ".")


def _f(x):
    return float(x.replace(",", "."))


def parse(s: str) -> dict:
    t = norm(s)
    u = t.upper()
    d = {"text": t, "kind": "note"}
    m = re.match(r"^(\d+)X\s+", u) or re.search(r"\((\d+)\s*X\)", u) or re.search(r"[\s\-](\d+)\s*X\s*$", u)
    if m:
        d["count"] = int(m.group(1))
    u = re.sub(r"^\d+X\s+", "", u)  # the rest is the callout itself
    u = re.sub(r"\s*\(\d+\s*X\)|[\s\-]+\d+\s*X\s*$", "", u).strip()
    m = re.search(r"\b(\d+)\s*PLACES\b|\b(\d+)\s*PL\b", u)
    if m:
        d["count"] = int(m.group(1) or m.group(2))
    u = re.sub(r"\bTHROUGH\b", "THRU", u)
    flags = [f for f in ("TYP", "THRU", "DEEP", "DRAFT", "FILLET", "CHAMFER", "EQ", "SPACED", "ALL AROUND")
             if re.search(rf"\b{f}\b", u)]
    if flags:
        d["flags"] = flags
    m = re.search(rf"(?:DEEP|DP|↧)\s*({NUM})|({NUM})\s*(?:DEEP|DP)\b", u)
    if m:
        d["depth"] = _f(m.group(1) or m.group(2))
    m = re.search(rf"±\s*({NUM})", u)
    if m:
        d["tol"] = f"±{m.group(1)}"
    else:
        m = re.search(rf"([+-]{NUM})\s*/?\s*([+-]{NUM})", u)
        if m:
            d["tol"] = f"{m.group(1)}/{m.group(2)}"
    m = re.search(rf"\bM({NUM})(?:\s*X\s*({NUM}))?", u)
    if m:
        d["kind"] = "thread"; d["value"] = _f(m.group(1))
        if m.group(2):
            d["pitch"] = _f(m.group(2))
        return d
    m = re.search(rf"(?:Ø|\bDIA\.?)\s*({NUM})", u)
    if m:
        d["kind"] = "dia"; d["value"] = _f(m.group(1))
        return d
    m = re.search(rf"(?:^|[\s(X])R\s*({NUM})", u)
    if m:
        d["kind"] = "radius"; d["value"] = _f(m.group(1))
        return d
    m = re.search(rf"({NUM})\s*X\s*({NUM})\s*°", u)
    if m:
        d["kind"] = "chamfer"; d["value"] = _f(m.group(1)); d["angle"] = _f(m.group(2))
        return d
    m = re.search(rf"({NUM})\s*°", u)
    if m:
        d["kind"] = "angle"; d["value"] = _f(m.group(1))
        return d
    m = re.fullmatch(rf"\(?\s*({NUM})\s*\)?(?:\s*(?:TYP\.?|±\s*{NUM}|[+-]{NUM}\s*/?\s*[+-]{NUM}))*\.?", u)
    if m:
        d["kind"] = "linear"; d["value"] = _f(m.group(1))
        if u.startswith("("):
            d["ref"] = True
        return d
    return d
