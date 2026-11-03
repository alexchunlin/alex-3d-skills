# GLB export (issue #31): cadlib.export.write_glb / `cad build ... --glb` writes <out>/model.glb, a node per part
# under a 0.001 root (a viewer read the v2 launcher as 433 m without it), a clip per joint, one for assembly_order.
# watch: @core tools/verify.d/glb_export_build.py tools/verify.d/glb_export_check.py examples/demo-turret/**
# watch: examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz examples/mm-launcher-v2a7/checks.json
# Sourced by tools/verify_all.sh (uses $ROOT $CAD $V, calls ok/bad). About 10 s: one demo build, one cad check
# --only insertion, four GLB writes (demo x3, v2a7). The GLB is read with the standard library (glb_export_check.py).
GX="$V/glb"; rm -rf "$GX"; mkdir -p "$GX"
GB="$ROOT/tools/verify.d/glb_export_build.py"; GC="$ROOT/tools/verify.d/glb_export_check.py"
DC="$ROOT/examples/demo-turret/checks.json"
glb_rows() { while read -r st msg; do case "$st" in PASS) ok "$msg" ;; FAIL) bad "$msg" ;; esac; done < "$1"; }
draco_default() {   # the chosen default (Draco) is what was written
  python3 -I -c "import json,struct,sys; b=open(sys.argv[1],'rb').read(); n=struct.unpack_from('<I',b,12)[0]; j=json.loads(b[20:20+n])
print('PASS' if 'KHR_draco_mesh_compression' in j.get('extensionsUsed',[]) else 'FAIL', sys.argv[2] + ': written with Draco by default, %.2f MB' % (len(b)/1e6))" "$1" "$2"
}
# 1 demo turret through `cad build --glb`: model.glb next to stl/, root scale, nodes = parts + PIVs, names, FK
$CAD build "$ROOT/examples/demo-turret/build.py" --out "$GX/demo" --glb > "$GX/demo_build.log" 2>&1
if [ -f "$GX/demo/model.glb" ] && [ -d "$GX/demo/stl" ]; then
  ok "glb: cad build --glb wrote model.glb next to stl/: $(sed -n 's/^GLB [^ ]* //p' "$GX/demo_build.log")"
  (cd "$GX" && $CAD py "$GB" "$GX/demo.json" "$GX/demo/model.glb" --blend "$GX/demo/demo.blend" --checks "$DC") > "$GX/demo_exp.log" 2>&1
  python3 -I "$GC" "$GX/demo/model.glb" "$GX/demo.json" "glb demo" > "$GX/demo.txt" 2>&1 || echo "FAIL glb demo: the reader crashed: $(tail -1 "$GX/demo.txt")" >> "$GX/demo.txt"
  glb_rows "$GX/demo.txt"
  draco_default "$GX/demo/model.glb" "glb demo" > "$GX/demo_draco.txt"; glb_rows "$GX/demo_draco.txt"
else
  bad "glb: cad build --glb wrote no model.glb next to stl/: $(tail -3 "$GX/demo_build.log")"
fi
# the assembly clip takes each part's way in from the insertion check when a report has it
$CAD check "$GX/demo/demo.blend" "$DC" "$GX/demo/ins.json" --only insertion > "$GX/ins.log" 2>&1
(cd "$GX" && $CAD py "$GB" "$GX/ins_exp.json" "$GX/ins.glb" --blend "$GX/demo/demo.blend" --checks "$DC" --report "$GX/demo/ins.json" --write) > "$GX/ins_glb.log" 2>&1
n_ins=$(sed -n "s/.*assembly flights {'insertion': \([0-9]*\).*/\1/p" "$GX/ins_glb.log")
[ "${n_ins:-0}" -ge 5 ] && ok "glb: with a cadcheck report the assembly clip flies $n_ins demo parts in along their insertion free_dir" \
  || bad "glb: the assembly clip ignored the insertion rows (${n_ins:-none} parts by insertion): $(tail -2 "$GX/ins_glb.log")"
# 3 negative control: PIV_tilt's sign flipped at export (a test-only env) must fail the FK check
(cd "$GX" && _CADLIB_GLB_TEST_FLIP=PIV_tilt $CAD py "$GB" "$GX/neg.json" "$GX/neg.glb" --blend "$GX/demo/demo.blend" --checks "$DC" --write) > "$GX/neg.log" 2>&1
python3 -I "$GC" "$GX/neg.glb" "$GX/neg.json" "glb demo" --expect-fail > "$GX/neg.txt" 2>&1 || echo "FAIL glb demo: the reader crashed on the flipped GLB" >> "$GX/neg.txt"
glb_rows "$GX/neg.txt"
# 2 + 4 v2a7: 188 nodes, 8 joint clips, PIV_feeder_pinion coupled at -1.4667, read as 0.43 m (issue #31: 245 x 432.6 x 300.2 mm); time, size
mkdir -p "$GX/v2a7"; gunzip -c "$ROOT/examples/mm-launcher-v2a7/mm_launcher_v2a7.blend.gz" > "$GX/v2a7/model.blend"
(cd "$GX" && $CAD py "$GB" "$GX/v2a7.json" "$GX/v2a7/model.glb" --blend "$GX/v2a7/model.blend" \
  --checks "$ROOT/examples/mm-launcher-v2a7/checks.json" --write) > "$GX/v2a7.log" 2>&1
python3 -I "$GC" "$GX/v2a7/model.glb" "$GX/v2a7.json" "glb v2a7" --require-joint PIV_feeder_pinion --extent-m 0.245,0.3002,0.4326 > "$GX/v2a7.txt" 2>&1 \
  || echo "FAIL glb v2a7: the reader crashed: $(tail -1 "$GX/v2a7.txt") $(tail -2 "$GX/v2a7.log")" >> "$GX/v2a7.txt"
glb_rows "$GX/v2a7.txt"
draco_default "$GX/v2a7/model.glb" "glb v2a7" > "$GX/v2a7_draco.txt" 2>&1; glb_rows "$GX/v2a7_draco.txt"
echo "NOTE glb v2a7: write_glb took $(python3 -I -c "import json,sys; print(json.load(open(sys.argv[1]))['info'].get('seconds'))" "$GX/v2a7.json" 2>/dev/null) s"
# 5 an offline glTF validator, if one happens to be installed (none is a dependency)
command -v gltf_validator > /dev/null 2>&1 && { gltf_validator "$GX/v2a7/model.glb" > "$GX/validator.txt" 2>&1 \
  && ok "glb: gltf_validator accepts the v2a7 GLB" || bad "glb: gltf_validator: $(tail -3 "$GX/validator.txt")"; } \
  || echo "NOTE glb: no gltf_validator on PATH: the GLB is not validated externally"
