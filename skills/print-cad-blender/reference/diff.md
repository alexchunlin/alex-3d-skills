# cad diff: what changed between two cadcheck runs

```sh
cad diff OLD/cadcheck.json NEW/cadcheck.json            # manifest.json next to each is diffed too
cad diff cadcheck.json                                  # against cadcheck.prev.json, kept by the last cad check
cad diff a.json b.json --manifest a/manifest.json b/manifest.json --max 60
```

`cad check` prints the short form at the end when it overwrites a report: counts, the requirements that weakened
(first, up to 10, so findings never push one out), then up to 20 lines of new, worse and fixed findings. `--no-diff` skips the
print. Every run keeps the report it overwrote as `<out>.prev.json`, and removes that file when there was no
readable report, so `cad diff cadcheck.json` always compares against the run just before. The one-argument form
refuses a `.prev.json` newer than the report. The manifest is not in the short form, because the build has already
overwritten it.

What each line means:

| tag | meaning |
|---|---|
| `new` / `fixed` | a finding whose key is in one run only. A new accepted warn shows as `warn(accepted)` |
| `worse` / `better` | same key, and the measured number moved or the status changed (warn -> fail is worse, fail -> warn better). `[136.8 -> 150.2]` gives the numbers |
| `changed` | same key, the number moved, but its direction is not known |
| `still` | an untriaged finding in both runs: what a reviewer marks NOT FIXED (full form only) |
| `accept` | a warn newly accepted, or no longer accepted |
| `REQ-` | a requirement removed: a check row (distances, slide_out, drop test, ...) or a config key gone |
| `REQ~` | a requirement loosened: an allow, accept or fit added; an `ignore` or `*_ok` list grown; a `min*` limit lowered or a `max*` / `*tol` limit raised; fewer poses sampled (`max_poses_per_group`, `max_guard_poses`, `envelope_max_poses` lowered) or less overtravel; an `*_ok` turned on |
| `req+` / `req` | rows added (a new requirement), rows renamed, other config changes. A row pairs with a renamed one only when it names the same objects; otherwise it is `REQ-` plus `req+` |
| `part` | manifest: parts added or removed, a fastener's spec or length, host, step, joint ranges, params, parts moved at home |

**Key.** A finding's key is its check, its objects and its kind: cadcfg's `accepted_warns` matching. The objects
come from the finding's `object`, `a`/`b` and `test` fields, or else from the object names in the text. The kind
comes from `cadcfg.kind_of`. Messages carry numbers, so matching on the text would report every changed value as
one fixed finding plus one new one. When findings share a key (one drop test at two poses), identical text pairs
first, then the closest text.

**Direction.** For each number in the message, smaller is worse after "only" or "min", and for a gap ("0.50 mm at").
Bigger is worse for the rest: volumes, areas, counts and exposed lengths. Limits ("< 1.6", "max 1.0", "needs 6.0",
"/13") are skipped. So are poses (`pan=-90`) and coordinates (`[..]`). Limits move only with the config, and the
requirements part lists those changes.

**Not compared.** Checks that ran in only one of the two runs (`--only`) are not compared and are named in the
headline. Rows that pass are not compared either, so a margin that shrinks but still passes prints nothing. V2R7's
A6-02 PARTIAL cites a distances row that now reads 0.916 against max 1.0 (0.133 in A6). The diff shows that issue
as one A6-02 warn fixed and one `still` (the launcher bundle's 5.7 mm drift).

Exit status: 1 when something got worse (a new untriaged finding, `worse`, `REQ-`, `REQ~` or a newly accepted
warn), 0 otherwise, 2 on bad input or any error. Plain python3, about 0.2 s on the 775 KB v2 launcher report.
