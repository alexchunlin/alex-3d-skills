#!/bin/sh
# Rebuild the vendored files `cad view` inlines into its page. Dev-only: needs network, npm and uv; `cad view` itself
# never touches the network. Run from anywhere: sh skills/print-cad-blender/scripts/viewer/vendor/build.sh
#   ax3.min.js                 three.js 0.170.0 (MIT), tree-shaken to what viewer/view.js uses, as the global AX3
#   draco_decoder.wasm + draco_wasm_wrapper.js   three's glTF Draco decoder build (Apache-2.0), for DRACOLoader
#   fonts/*.woff2              Roboto, Roboto Condensed, Roboto Mono (OFL) from the alex-style guide, Latin-1 subset
# The style guide is the same version as the one the page's look comes from (AX_STYLE, default ~/code-stuff/alex-style-guide).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
STYLE="${AX_STYLE:-$HOME/code-stuff/alex-style-guide}"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
cd "$T"
npm init -y >/dev/null
npm i --silent three@0.170.0 esbuild@0.24.0
cat > entry.js <<'EOF'
export { WebGLRenderer, Scene, PerspectiveCamera, Color, Vector2, Vector3, Matrix4, Box3, Group, Mesh, MeshStandardMaterial,
  MeshBasicMaterial, LineBasicMaterial, LineSegments, EdgesGeometry, BufferGeometry, Float32BufferAttribute,
  HemisphereLight, DirectionalLight, GridHelper, ArrowHelper, Raycaster, Plane, SRGBColorSpace, DoubleSide, Clock,
  Box3Helper, SphereGeometry, Sphere } from 'three';
export { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
export { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';
export { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
EOF
npx esbuild entry.js --bundle --minify --format=iife --global-name=AX3 --legal-comments=none --log-level=warning \
  --banner:js="/* three.js 0.170.0 (MIT, see LICENSE-three.txt), tree-shaken for cad view by vendor/build.sh */" --outfile="$HERE/ax3.min.js"
D=node_modules/three/examples/jsm/libs/draco/gltf
cp "$D/draco_decoder.wasm" "$D/draco_wasm_wrapper.js" "$HERE/"
cp node_modules/three/LICENSE "$HERE/LICENSE-three.txt"
cp "$STYLE/LICENSE" "$HERE/LICENSE-alex-style.txt"
cp "$STYLE/fonts/OFL.txt" "$HERE/fonts/OFL.txt"
for f in Roboto-400 Roboto-500 RobotoCondensed-500 RobotoCondensed-700 RobotoMono-400 RobotoMono-500; do
  uv run -q --with fonttools --with brotli pyftsubset "$STYLE/fonts/$f.ttf" --flavor=woff2 --layout-features='kern,tnum' \
    --unicodes="U+0020-007E,U+00A0-00FF,U+2010-2027,U+2190-2193,U+2212,U+2248,U+2264,U+2265,U+25A0,U+25CC" \
    --output-file="$HERE/fonts/$f.woff2"
done
cp "$STYLE/web/tokens.css" "$HERE/tokens.css"
# LICENSE-draco.txt: Apache-2.0 text from https://github.com/google/draco/blob/main/LICENSE (the npm builds ship none)
[ -f "$HERE/LICENSE-draco.txt" ] || curl -sfL https://raw.githubusercontent.com/google/draco/main/LICENSE -o "$HERE/LICENSE-draco.txt"
ls -l "$HERE" "$HERE/fonts"
