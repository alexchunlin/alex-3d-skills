# cadcheck interference between sampled poses: the PR #3 review's `wedge` and `pantilt` scenes, where a 2 mm arm at
# 70 mm reach passed through a static cable between two 15 deg samples, two clear sweeps and a declared journal as negative controls, and the PR #14 review's scenes
# (tools/verify.d/sweep_guard_build.py). Sourced by tools/verify_all.sh (uses $ROOT $CAD $V; calls ok/bad). About 90 s.
# watch: @core tools/verify.d/sweep_guard_build.py
SG="$V/sweep_guard"; mkdir -p "$SG"
echo '{"fits": [{"a": "PRT_arm", "b": "PRT_base", "min_clearance": 0.1, "why": "hub running fit on the shaft"}]}' > "$SG/fit.json"
for sc in wedge pantilt clear beside blade_box blade_cyl multishell_a multishell_b fit_hide fit_journal; do
  $CAD build "$ROOT/tools/verify.d/sweep_guard_build.py" -- --scene $sc --out "$SG/$sc" > "$SG/$sc.log" 2>&1
  cfg=""; case $sc in fit_*) cfg="$SG/fit.json" ;; esac
  $CAD check "$SG/$sc/scene.blend" "$cfg" "$SG/$sc/cadcheck.json" --only interference > /dev/null 2>&1
done
# the guard switched off (max_guard_poses 0): the sampled poses alone miss the wedge, and the pair is listed unproven
echo '{"max_guard_poses": 0}' > "$SG/off.json"
$CAD check "$SG/wedge/scene.blend" "$SG/off.json" "$SG/wedge/off.json" --only interference > /dev/null 2>&1
sg() {   # sg "message" 'python condition on r (scene -> report)'
  python3 -I -c "
import json, sys
r = {}
for k in ('wedge', 'pantilt', 'clear', 'beside', 'blade_box', 'blade_cyl', 'multishell_a', 'multishell_b', 'fit_hide', 'fit_journal', 'off'):
    f = 'wedge/off.json' if k == 'off' else k + '/cadcheck.json'
    try:
        r[k] = json.load(open(sys.argv[1] + '/' + f))
    except Exception:
        r[k] = {'summary': {'fail_list': [], 'warn_list': []}, 'not_checked': [], 'checks': {}}
fl = lambda k: ' | '.join(r[k]['summary']['fail_list'])
wl = lambda k: ' | '.join(r[k]['summary']['warn_list'])
sys.exit(0 if ($2) else 1)" "$SG" 2>/dev/null && ok "$1" || bad "$1 (see $SG)"
}
sg "sweep guard: wedge, the arm through the cable between the 0 and 15 deg samples fails (between the sampled poses)" \
   "'PRT_arm x CAB_w collide' in fl('wedge') and 'between the sampled poses' in fl('wedge')"
sg "sweep guard: wedge collision found where the arm overlaps the cable (4.5..10.5 deg)" \
   "any(4.5 <= float(c['pose'].split('=')[1]) <= 10.5 and c['volume_mm3'] > 50 for c in r['wedge']['checks']['interference']['collisions'])"
sg "sweep guard: pantilt, the cable at pan 45 between the thinned pan samples fails" \
   "'PRT_arm x CAB_w collide' in fl('pantilt')"
sg "sweep guard: clear sweep (cable past the arm's reach) stays clean: 0 fails, 0 warns, nothing unproven" \
   "not fl('clear') and not wl('clear') and not r['clear']['checks']['interference']['between_samples']['unproven']"
sg "sweep guard: clear sweep is settled by the broad phase (the cable lies past the arm's ring sector)" \
   "r['clear']['checks']['interference']['between_samples']['broad_culled'] == 1"
sg "sweep guard: cable 3 mm past the arm's overtravel: broad phase can't settle it, the swept envelope does; clean" \
   "not fl('beside') and not wl('beside') and r['beside']['checks']['interference']['between_samples']['narrow_culled'] == 1"
sg "sweep guard off (max_guard_poses 0): the 15 deg samples miss the wedge, and the pair warns as unproven with its pose range" \
   "'collide' not in fl('off') and 'PRT_arm x CAB_w not proven clear between the sampled poses at arm=' in wl('off')"
# PR #14 review
sg "sweep guard: blade_box, refinement uses a lower bound (min_dist read 12.64 mm where the gap is 4.2): 14.7 mm3 at 37.5" \
   "'PRT_blade x PRT_post collide' in fl('blade_box') and any(abs(c['volume_mm3'] - 14.7) < 0.5 for c in r['blade_box']['checks']['interference']['collisions'])"
sg "sweep guard: blade_cyl (round post), the blade through the post between samples is caught" \
   "'PRT_blade x PRT_post collide' in fl('blade_cyl')"
sg "sweep guard: multishell_a, a placeholder's pin wholly inside the blade's envelope (far shell first) is caught" \
   "'PRT_blade x BUY_motor' in fl('multishell_a')"
sg "sweep guard: multishell_b, the same with the pin first" \
   "'PRT_blade x BUY_motor' in fl('multishell_b')"
sg "sweep guard: fit_hide, a declared running fit doesn't hide a lug on the same part in the arm's path" \
   "'PRT_arm x PRT_base collide' in fl('fit_hide') and 'between the sampled poses' in fl('fit_hide')"
sg "sweep guard: fit_journal, the declared journal alone stays clean, proven by the turning test" \
   "not fl('fit_journal') and not wl('fit_journal') and any(x.endswith(': turning') for x in r['fit_journal']['checks']['interference']['between_samples']['fits_flagged'])"
