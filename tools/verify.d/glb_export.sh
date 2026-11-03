# GLB export (issue #31): cadlib.gltf.write_glb / `cad build ... --glb` writes <out>/model.glb, a node per part
# under a 0.001 root (a viewer read the v2 launcher as 433 m without it), a clip per joint, one for assembly_order.
# watch: @core tools/verify.d/glb_export_build.py tools/verify.d/glb_export_check.py examples/demo-turret/**
# watch: examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz examples/mm-launcher-v2a7/checks.json
# watch: skills/print-cad-blender/templates/project/**
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 12 s: three demo builds, one template build,
# one cad check --only insertion, two more GLB writes (demo flipped, v2a7). The GLB is read with the standard library
# (glb_export_check.py); the expected matrices come from cadlib.joints in Blender (glb_export_build.py).
GX="$V/glb"; rm -rf "$GX"; mkdir -p "$GX"
GB="$ROOT/tools/verify.d/glb_export_build.py"; GC="$ROOT/tools/verify.d/glb_export_check.py"
DC="$ROOT/examples/demo-turret/checks.json"
glb_rows() { while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; NOTE) echo "NOTE $msg" ;; esac; done < "$1"; }
draco_default() {   # the chosen default (Draco) is what was written
  python3 -I -c "import json,struct,sys; b=open(sys.argv[1],'rb').read(); n=struct.unpack_from('<I',b,12)[0]; j=json.loads(b[20:20+n])
print('PASS' if 'KHR_draco_mesh_compression' in j.get('extensionsUsed',[]) else 'FAIL', sys.argv[2] + ': written with Draco by default, %.2f MB' % (len(b)/1e6))" "$1" "$2"
}
flights() { sed -n "s/.*assembly flights {'insertion': \([0-9]*\).*/\1/p" "$1"; }
# 1 demo turret through `cad build --glb`: model.glb next to stl/, root, nodes = parts + PIVs, names, extent, FK, order.
# A stale cadcheck.json in the out dir is planted first: a plain --glb build must not read it (only --glb-report does).
mkdir -p "$GX/demo"; echo '{"checks": {"insertion": {"rows": [{"object": "PRT_base", "free_dir": "+X", "free_dir_vec": [1, 0, 0]}]}}}' > "$GX/demo/cadcheck.json"
$CAD build "$ROOT/examples/demo-turret/build.py" --out "$GX/demo" --glb > "$GX/demo_build.log" 2>&1
if [ -f "$GX/demo/model.glb" ] && [ -d "$GX/demo/stl" ]; then
  ok "glb: cad build --glb wrote model.glb next to stl/: $(sed -n 's/^GLB [^ ]* //p' "$GX/demo_build.log")"
  [ "$(flights "$GX/demo_build.log")" = 0 ] && ! grep -q '^glb: insertion directions' "$GX/demo_build.log" \
    && ok "glb: a plain --glb build ignores the (stale) cadcheck.json in its out dir: every flight radial" \
    || bad "glb: a plain --glb build read the cadcheck.json in its out dir ($(flights "$GX/demo_build.log") flights by insertion)"
  (cd "$GX" && $CAD py "$GB" "$GX/demo.json" "$GX/demo/model.glb" --blend "$GX/demo/demo.blend" --checks "$DC") > "$GX/demo_exp.log" 2>&1
  # extent in glTF's Y-up order (x, y up, z = -Blender y), from cad q list: x -40..43, Blender y -40..45, z -2.4..80 mm
  python3 -I "$GC" "$GX/demo/model.glb" "$GX/demo.json" "glb demo" --extent-m 0.083,0.0824,0.085 > "$GX/demo.txt" 2>&1 \
    || echo "FAIL glb demo: the reader crashed: $(tail -1 "$GX/demo.txt")" >> "$GX/demo.txt"
  glb_rows "$GX/demo.txt"
  draco_default "$GX/demo/model.glb" "glb demo" > "$GX/demo_draco.txt"; glb_rows "$GX/demo_draco.txt"
  # negative controls for the reader: the root's rotation dropped fails the root, extent and FK lines; one object
  # shown a step late fails the order line
  python3 -I "$GC" --tamper "$GX/demo/model.glb" "$GX/noroot.glb" root
  python3 -I "$GC" "$GX/noroot.glb" "$GX/demo.json" "glb demo" --extent-m 0.083,0.0824,0.085 > "$GX/noroot.txt" 2>&1
  n=$(grep -c -E '^FAIL .*(one root node|a viewer reads|world matrices)' "$GX/noroot.txt")
  [ "$n" = 3 ] && ok "glb demo: negative control: a root with no rotation fails the root, extent and FK lines" \
    || bad "glb demo: a root with no rotation failed $n of the 3 lines (root, extent, FK): $(grep -c ^FAIL "$GX/noroot.txt") FAIL lines"
  python3 -I "$GC" --tamper "$GX/demo/model.glb" "$GX/late.glb" order
  python3 -I "$GC" "$GX/late.glb" "$GX/demo.json" "glb demo" > "$GX/late.txt" 2>&1
  grep -q '^FAIL .*assembly clip: .*(NOT: ' "$GX/late.txt" && ok "glb demo: negative control: an object shown a step late fails the order line" \
    || bad "glb demo: an object shown a step late passed the order line: $(grep 'assembly clip' "$GX/late.txt")"
else
  bad "glb: cad build --glb wrote no model.glb next to stl/: $(tail -3 "$GX/demo_build.log")"
fi
# --glb-report: the assembly clip takes each part's way in from the insertion check's free_dir_vec
$CAD check "$GX/demo/demo.blend" "$DC" "$GX/ins.json" --only insertion > "$GX/ins.log" 2>&1
$CAD build "$ROOT/examples/demo-turret/build.py" --out "$GX/demo_ins" --glb --glb-report "$GX/ins.json" > "$GX/ins_build.log" 2>&1
n_ins=$(flights "$GX/ins_build.log")
n_vec=$(python3 -I -c "import json,sys; print(sum(isinstance(r.get('free_dir_vec'), list) for r in json.load(open(sys.argv[1]))['checks']['insertion']['rows']))" "$GX/ins.json" 2>/dev/null)
[ "${n_ins:-0}" -ge 5 ] && grep -q "^glb: insertion directions from $GX/ins.json (" "$GX/ins_build.log" \
  && ok "glb: --glb-report flies $n_ins demo parts in along the insertion check's free_dir_vec ($n_vec rows carry one) and logs the report and its time" \
  || bad "glb: --glb-report: ${n_ins:-no} flights by insertion: $(tail -2 "$GX/ins_build.log")"
# 3 negative control: joints.values patched in the test (glb_export_build.py --flip) to mirror PIV_tilt at export
(cd "$GX" && $CAD py "$GB" "$GX/neg.json" "$GX/neg.glb" --blend "$GX/demo/demo.blend" --checks "$DC" --write --flip PIV_tilt) > "$GX/neg.log" 2>&1
python3 -I "$GC" "$GX/neg.glb" "$GX/neg.json" "glb demo" --expect-fail > "$GX/neg.txt" 2>&1 || echo "FAIL glb demo: the reader crashed on the flipped GLB" >> "$GX/neg.txt"
glb_rows "$GX/neg.txt"
# the template's --glb branch: model.glb next to its stl/, and the same checks
mkdir -p "$GX/tpl"; cp -R "$ROOT/skills/print-cad-blender/templates/project" "$GX/tpl/blender"
$CAD build "$GX/tpl/blender/build_assembly.py" -- --out "$GX/tplout" --glb > "$GX/tpl_build.log" 2>&1
if [ -f "$GX/tplout/model.glb" ] && [ -d "$GX/tplout/stl" ]; then
  (cd "$GX" && $CAD py "$GB" "$GX/tpl.json" "$GX/tplout/model.glb" --blend "$GX/tplout/model.blend" --checks "$GX/tpl/blender/checks.json") > "$GX/tpl_exp.log" 2>&1
  python3 -I "$GC" "$GX/tplout/model.glb" "$GX/tpl.json" "glb template" > "$GX/tpl.txt" 2>&1 || echo "FAIL glb template: the reader crashed: $(tail -1 "$GX/tpl.txt")" >> "$GX/tpl.txt"
  glb_rows "$GX/tpl.txt"
else
  bad "glb: the template's --glb wrote no model.glb next to stl/: $(tail -3 "$GX/tpl_build.log")"
fi
# 2 + 4 v2a7: 188 nodes, 8 joint clips, PIV_feeder_pinion coupled at -1.4667, read as 0.43 m tall (issue #31: 245 x
# 432.6 x 300.2 mm with Blender's Z = 432.6, so Y-up x, y, z = 0.245, 0.4326, 0.3002); time, size
mkdir -p "$GX/v2a7"; gunzip -c "$ROOT/examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz" > "$GX/v2a7/model.blend"
(cd "$GX" && $CAD py "$GB" "$GX/v2a7.json" "$GX/v2a7/model.glb" --blend "$GX/v2a7/model.blend" \
  --checks "$ROOT/examples/mm-launcher-v2a7/checks.json" --write) > "$GX/v2a7.log" 2>&1
python3 -I "$GC" "$GX/v2a7/model.glb" "$GX/v2a7.json" "glb v2a7" --require-joint PIV_feeder_pinion --extent-m 0.245,0.4326,0.3002 > "$GX/v2a7.txt" 2>&1 \
  || echo "FAIL glb v2a7: the reader crashed: $(tail -1 "$GX/v2a7.txt") $(tail -2 "$GX/v2a7.log")" >> "$GX/v2a7.txt"
glb_rows "$GX/v2a7.txt"
draco_default "$GX/v2a7/model.glb" "glb v2a7" > "$GX/v2a7_draco.txt" 2>&1; glb_rows "$GX/v2a7_draco.txt"
echo "NOTE glb v2a7: write_glb took $(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['info'].get('seconds'))" "$GX/v2a7.json" 2>/dev/null) s"
# 5 an offline glTF validator, if one happens to be installed (none is a dependency)
command -v gltf_validator > /dev/null 2>&1 && { gltf_validator "$GX/v2a7/model.glb" > "$GX/validator.txt" 2>&1 \
  && ok "glb: gltf_validator accepts the v2a7 GLB" || bad "glb: gltf_validator: $(tail -3 "$GX/validator.txt")"; } \
  || echo "NOTE glb: no gltf_validator on PATH: the GLB is not validated externally"
