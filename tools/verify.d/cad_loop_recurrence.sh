# cad-loop recurrence, snapshots and best (#41, #42; PR #52): negative controls for tools/test_workflow_template.py.
# Each line below plants one bug in a copy of templates/cad-loop.workflow.js under $V; the dry-run test must fail on it.
# watch: templates/cad-loop.workflow.js tools/test_workflow_template.py
# Sourced by tools/verify_all.sh (uses $ROOT $V, calls ok/bad). About 15 s of node, no Blender.
CLR="$V/cad_loop_recurrence"; mkdir -p "$CLR"
if python3 -I "$ROOT/tools/test_workflow_template.py" "$ROOT/templates/cad-loop.workflow.js" > "$CLR/clean.txt" 2>&1; then
  ok "cad-loop: template dry run passes unmutated"
else
  bad "cad-loop: template dry run fails unmutated (see $CLR/clean.txt)"
fi
while read -r clr_name clr_sed; do
  [ -n "$clr_name" ] || continue
  sed "$clr_sed" "$ROOT/templates/cad-loop.workflow.js" > "$CLR/$clr_name.js"
  if cmp -s "$CLR/$clr_name.js" "$ROOT/templates/cad-loop.workflow.js"; then
    bad "cad-loop control $clr_name: the mutation no longer applies (template changed; update the sed)"
  elif python3 -I "$ROOT/tools/test_workflow_template.py" "$CLR/$clr_name.js" > "$CLR/$clr_name.txt" 2>&1; then
    bad "cad-loop control $clr_name: planted bug not caught by test_workflow_template.py"
  else
    ok "cad-loop control $clr_name: caught ($(grep -m1 FAIL "$CLR/$clr_name.txt" | cut -c1-90))"
  fi
done <<'EOF'
best-ties-to-earliest s/>= b.f + b.m + b.a/> b.f + b.m + b.a/
escalate-at-three s/misses\[id\] >= 2/misses[id] >= 3/
misses-not-cumulative s/(prev\[s.id\] || 0) + 1/1/
not-fixed-not-a-miss s/const MISSED = \['PARTIAL', 'NOT FIXED'\]/const MISSED = ['PARTIAL']/
no-snapshot-dir s#/snapshot/#/snap/#g
latest-not-marked s/ + ' (latest)'//
no-text-only-line s/text-only mismatches/textual mismatches/g
parallel-text-not-routed s/goes in not_done as "text: ..."/goes in not_done/
no-escalation-warning s/if (unescalated.length) log/if (0) log/
partial-check-reviewed s/if ((design.check.run_only || \[\]).length)/if (0)/
no-resume-warning s/if (CONFIG.start_attempt > 1 \&\& !Object.keys(misses).length) log/if (0) log/
misses-arg-unchecked s/if (!isPlain(m)) throw new Error(`cad-loop: args.misses/if (0) throw new Error(`cad-loop: args.misses/
misses-count-unchecked s/if (!Number.isInteger(v) || v < 1) throw/if (0) throw/
resume-line-no-misses s/ misses=${JSON.stringify(misses)}//
EOF
