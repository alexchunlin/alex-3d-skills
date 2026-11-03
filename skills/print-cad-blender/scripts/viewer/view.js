// cad view page logic. cadview.py inlines this into viewer/page.html with the model data (#cv-data) and four gzip+base64
// payloads: the three.js bundle (vendor/ax3.min.js, global AX3), the Draco decoder (wrapper JS + wasm) and the GLB.
// Posing mirrors cadlib/joints.py (values / world_at): a joint's local matrix is matrix_parent_inverse @ basis(value),
// every other node keeps the local matrix Blender's glTF exporter wrote. #selftest compares the result with Blender.
(async function () {
'use strict';
const $ = s => document.querySelector(s);
const DATA = JSON.parse($('#cv-data').textContent);
const TEST = location.hash === '#selftest';
const errors = [];
addEventListener('error', e => errors.push(String(e.message || e)));
addEventListener('unhandledrejection', e => errors.push(String((e.reason && e.reason.stack) || e.reason)));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const css = v => getComputedStyle(document.documentElement).getPropertyValue('--ax-' + v).trim();
const REP = DATA.report;
const FINDS = REP ? REP.findings : [];

// ── header ──
document.title = DATA.title + ' · cad view';
$('#cv-title').textContent = DATA.title;
const meta = [`<span>${esc(DATA.blend)}</span>`, `<span>saved ${esc(DATA.saved)}</span>`,
  `<span>${Object.keys(DATA.objects).length} objects</span>`, `<span>${DATA.joints.length} joints</span>`];
if (REP) {
  const nf = FINDS.filter(f => f.status === 'fail').length, nw = FINDS.length - nf;
  meta.push(`<span>${esc(REP.file)} ${esc(REP.generated || '')}</span>`,
    `<span class="ax-status ${nf ? 'critical' : 'good'}">${nf} fail</span>`, `<span class="ax-status ${nw ? 'warning' : 'good'}">${nw} warn${REP.untriaged != null && REP.untriaged !== nw ? `, ${REP.untriaged} untriaged` : ''}</span>`);
}
$('#cv-meta').innerHTML = meta.join('');
$('#cv-made').textContent = `Made by cad view from ${DATA.blend}. Display mesh (Draco, 14-bit): measure with cad q.`;
const banner = [...DATA.warn];
if (DATA.skipped.length) banner.push(`${DATA.skipped.length} object(s) not in the view layer, not shown: ${DATA.skipped.slice(0, 6).join(', ')}`);
if (banner.length) { const b = $('#cv-banner'); b.hidden = false; b.innerHTML = banner.map(t => `<div class="cv-banner">${esc(t)}</div>`).join(''); }

// ── spinner while the payloads decode ──
const view = $('#view');
view.classList.add('ax-viewport', 'ax-loading');
const spin = document.createElement('div');
spin.className = 'ax-spin-wrap';
spin.innerHTML = '<span class="ax-spin lg"></span><span>Loading model</span>';
view.appendChild(spin);

function bytes(id) {
  const s = document.getElementById(id).textContent.trim(), bin = atob(s), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return u;
}
const gunzip = id => new Response(new Blob([bytes(id)]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
const [threeBuf, dracoJs, dracoWasm, glbBuf] = await Promise.all(['cv-three', 'cv-draco-js', 'cv-draco-wasm', 'cv-glb'].map(gunzip));
(0, eval)(new TextDecoder().decode(threeBuf));   // defines the global AX3 (indirect eval: global scope)
const T = window.AX3;

// ── pose maths (cadlib/joints.py) on row-major 4x4 arrays ──
const DEG = Math.PI / 180;
const mul = (a, b) => { const o = new Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { let s = 0; for (let k = 0; k < 4; k++) s += a[i * 4 + k] * b[k * 4 + j]; o[i * 4 + j] = s; } return o; };
const rot1 = (ax, t) => { const c = Math.cos(t), s = Math.sin(t);
  return ax === 'X' ? [1, 0, 0, 0, c, -s, 0, s, c] : ax === 'Y' ? [c, 0, s, 0, 1, 0, -s, 0, c] : [c, -s, 0, s, c, 0, 0, 0, 1]; };
const mul3 = (a, b) => { const o = new Array(9); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) o[i * 3 + j] = a[i * 3] * b[j] + a[i * 3 + 1] * b[3 + j] + a[i * 3 + 2] * b[6 + j]; return o; };
// mathutils Euler(r, mode).to_matrix(): the first letter's rotation is applied first, so R = R[m2] R[m1] R[m0]
const euler = (r, m) => { const R = { X: rot1('X', r[0]), Y: rot1('Y', r[1]), Z: rot1('Z', r[2]) }; return mul3(R[m[2]], mul3(R[m[1]], R[m[0]])); };
const EULER = ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'];
const basisRot = b => { const c = [0, 1, 2].map(j => Math.hypot(b[j], b[4 + j], b[8 + j]) || 1); return [0, 1, 2].flatMap(i => [0, 1, 2].map(j => b[i * 4 + j] / c[j])); };
const lrs = (l, R, s) => [R[0] * s[0], R[1] * s[1], R[2] * s[2], l[0], R[3] * s[0], R[4] * s[1], R[5] * s[2], l[1], R[6] * s[0], R[7] * s[1], R[8] * s[2], l[2], 0, 0, 0, 1];
function values(pose) {   // joints.values: unlisted joints at home, coupled joints follow their driver
  const v = {};
  for (const j of DATA.joints) v[j.name] = j.name in pose ? pose[j.name] : (j.home || 0);
  for (const [n, to, ratio, off] of DATA.couplings) v[n] = (v[to] ?? 0) * ratio + off;
  return v;
}
function jointLocal(j, val) {   // matrix_parent_inverse @ basis, basis as joints.world_at builds it
  let basis = j.basis;
  if (j.axis) {
    const ai = 'XYZ'.indexOf(j.axis), isE = EULER.includes(j.mode);
    let loc = j.loc, R = isE ? euler(j.rot, j.mode) : basisRot(j.basis);
    if (j.kind === 'prismatic') {
      const Rb = euler(j.base_rot, 'XYZ');
      loc = [0, 1, 2].map(i => j.base_loc[i] + Rb[i * 3 + ai] * val);
    } else if (isE) {
      const r = j.base_rot.slice(); r[ai] = val * DEG; R = euler(r, j.mode);
    }
    basis = lrs(loc, R, j.scale);
  }
  return mul(j.mpi, basis);
}

// ── viewport: adapted from alex-style web/ax-three.js axScene() for a Z-up CAD frame and inlined three.js ──
const col = v => new T.Color(css(v));
const renderer = new T.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: TEST });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = T.SRGBColorSpace;
renderer.localClippingEnabled = true;
view.appendChild(renderer.domElement);
const labels = new T.CSS2DRenderer();
Object.assign(labels.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' });
view.appendChild(labels.domElement);
const scene = new T.Scene();
const camera = new T.PerspectiveCamera(35, 1, 1, 1e5);
camera.up.set(0, 0, 1);
const controls = new T.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotateSpeed = 0.6;
controls.autoRotate = !TEST && !matchMedia('(prefers-reduced-motion: reduce)').matches;
let idle;
controls.addEventListener('start', () => { controls.autoRotate = false; clearTimeout(idle); });
const hemi = new T.HemisphereLight(0xffffff, 0x202020, 1.2);
hemi.position.set(0, 0, 1);   // sky above in Z-up
scene.add(hemi);
const key = new T.DirectionalLight(0xffffff, 1.3);
scene.add(key);
const fill = new T.DirectionalLight(0xffffff, 0.5);
scene.add(fill);

// load the GLB through GLTFLoader + DRACOLoader, the decoder handed over from memory instead of fetched
const draco = new T.DRACOLoader();
draco.setDecoderConfig({ type: 'wasm' });
const dracoText = new TextDecoder().decode(dracoJs);
draco._loadLibrary = (url, type) => Promise.resolve(type === 'arraybuffer' ? dracoWasm.slice(0) : dracoText);
const loader = new T.GLTFLoader();
loader.setDRACOLoader(draco);
const gltf = await new Promise((res, rej) => loader.parse(glbBuf, '', res, rej));
draco.dispose();
const root = gltf.scene;
scene.add(root);
const byName = {};   // Blender object name -> Object3D (GLTFLoader sanitises names, so go through the node index)
root.traverse(o => { const a = gltf.parser.associations.get(o); if (a && a.nodes !== undefined) byName[gltf.parser.json.nodes[a.nodes].name] = o; });
root.traverse(o => { o.updateMatrix(); o.matrixAutoUpdate = false; });

const P = {};     // per view object: node, meshes, materials, local matrix, home bbox
const edgeMat = () => new T.LineBasicMaterial({ color: col('ink'), transparent: true, opacity: 0.45 });
const pickables = [];
for (const [name, info] of Object.entries(DATA.objects)) {
  const node = byName[name];
  if (!node) { errors.push('object missing from the GLB: ' + name); continue; }
  const [r, g, b, a] = info.rgba;
  const meshes = [];
  node.traverse(m => { if (m.isMesh && (m === node || m.parent === node)) meshes.push(m); });
  // cadlib's PALETTE holds sRGB hex values typed into diffuse_color (terracotta is alex-style #c4532a): read them as sRGB
  const mat = new T.MeshStandardMaterial({ color: new T.Color().setRGB(r, g, b, T.SRGBColorSpace), roughness: 0.62, metalness: info.role === 'FST' ? 0.45 : 0.08,
    flatShading: true, transparent: a < 1, opacity: a, side: T.DoubleSide });
  const em = edgeMat();
  const box = new T.Box3();
  for (const m of meshes) {
    m.material = mat;
    const tris = m.geometry.index ? m.geometry.index.count / 3 : m.geometry.attributes.position.count / 3;
    if (tris < 150000) m.add(new T.LineSegments(new T.EdgesGeometry(m.geometry, 30), em));   // a 250k-tri PCB gets no edges
    m.userData.cv = name;
    m.geometry.computeBoundingBox();
    box.union(m.geometry.boundingBox.clone().applyMatrix4(m === node ? new T.Matrix4() : m.matrix));
    pickables.push(m);
  }
  P[name] = { name, info, node, meshes, mat, em, local: node.matrix.clone(), box, base: { color: mat.color.clone(), opacity: a } };
}
const jointNode = {};
for (const j of DATA.joints) if (byName[j.name]) jointNode[j.name] = byName[j.name];
const J = Object.fromEntries(DATA.joints.map(j => [j.name, j]));
const coupled = Object.fromEntries(DATA.couplings.map(([n, to, ratio, off]) => [n, { to, ratio, off }]));

// ── state ──
const clipPlane = new T.Plane(new T.Vector3(1, 0, 0), 0);
const rows = {};                // joint name -> slider row (filled below)
const markers = new T.Group();  // the selected finding's points and box
scene.add(markers);
const S = { pose: { ...DATA.pose }, explode: 0, xray: false, section: null, cut: 0.5, failTint: true, sel: null, hover: null, partFilter: null };
const failNames = new Set(FINDS.filter(f => f.status === 'fail').flatMap(f => f.names));
const tmp = new T.Vector3(), M4 = new T.Matrix4(), M4b = new T.Matrix4();
const setRowMajor = (m, a) => m.set(...a);

function worldBox(name) {
  const p = P[name], b = new T.Box3();
  b.copy(p.box).applyMatrix4(p.node.matrixWorld);
  return b;
}
function applyPose() {
  const v = values(S.pose);
  for (const [n, node] of Object.entries(jointNode)) { setRowMajor(node.matrix, jointLocal(J[n], v[n])); }
  for (const p of Object.values(P)) p.node.matrix.copy(p.local);
  root.updateMatrixWorld(true);
  if (S.explode > 0) {   // radial explode about the assembly centre, applied in world space on top of the pose
    const all = new T.Box3();
    const cs = {};
    for (const n in P) { const b = worldBox(n); cs[n] = b.getCenter(new T.Vector3()); all.union(b); }
    const c0 = all.getCenter(new T.Vector3()), k = S.explode * 1.2;
    for (const n in P) {
      const p = P[n], d = cs[n].clone().sub(c0).multiplyScalar(k);
      M4.copy(p.node.parent.matrixWorld).invert();
      M4b.makeTranslation(d.x, d.y, d.z).multiply(p.node.parent.matrixWorld).multiply(p.local);
      p.node.matrix.multiplyMatrices(M4, M4b);
    }
    root.updateMatrixWorld(true);
  }
  updateReadouts();
  updateMarkers();
}

// ── look: base colour, fail tint, selected finding, ghosting, hover ──
function restyle() {
  const sel = S.sel, hit = new Set(sel ? sel.names : []);
  const selCol = sel ? col(sel.status === 'fail' ? 'critical' : 'warning') : null;
  for (const p of Object.values(P)) {
    const m = p.mat, e = p.em;
    m.color.copy(p.base.color);
    m.emissive.setRGB(0, 0, 0);
    e.color.copy(col('ink')); e.opacity = 0.45;
    let ghost = S.xray || (sel && hit.size && !hit.has(p.name));
    if (S.failTint && failNames.has(p.name)) { m.emissive.copy(col('critical')).multiplyScalar(0.1); e.color.copy(col('critical')); e.opacity = 1; }
    if (hit.has(p.name)) { m.emissive.copy(selCol).multiplyScalar(0.45); e.color.copy(selCol); e.opacity = 1; ghost = false; }
    if (S.hover === p.name) { m.emissive.copy(col('accent')).multiplyScalar(0.35); e.color.copy(col('accent')); e.opacity = 1; }
    const tr = !!(ghost || p.base.opacity < 1), clip = !!S.section;
    if (m.transparent !== tr || p.clip !== clip) {   // a program change: only when transparency or clipping flips
      m.transparent = tr; p.clip = clip;
      m.clippingPlanes = e.clippingPlanes = clip ? [clipPlane] : [];
      m.needsUpdate = e.needsUpdate = true;
    }
    m.opacity = ghost ? 0.12 : p.base.opacity;
    m.depthWrite = !ghost;
    e.opacity *= ghost ? 0.35 : 1;
  }
}

// ── floor grid and XYZ triad, sized from the model ──
applyPose();
const home = new T.Box3();
for (const n in P) home.union(worldBox(n));
const size = home.getSize(new T.Vector3()), centre = home.getCenter(new T.Vector3());
const R = Math.max(size.x, size.y, size.z, 10);
const step = Math.pow(10, Math.floor(Math.log10(R / 2)));
const span = Math.ceil(R * 1.6 / step) * step;
const grid = new T.GridHelper(span, Math.round(span / step), col('axis'), col('grid'));
grid.rotation.x = Math.PI / 2;
grid.position.set(centre.x, centre.y, home.min.z);
grid.material.transparent = true; grid.material.opacity = 0.9;
scene.add(grid);
{
  const L = R * 0.18, corner = new T.Vector3(home.min.x - R * 0.12, home.min.y - R * 0.12, home.min.z);
  [['X', [1, 0, 0], 's2'], ['Y', [0, 1, 0], 's3'], ['Z', [0, 0, 1], 's1']].forEach(([n, d, c]) => {
    const dir = new T.Vector3(...d);
    scene.add(new T.ArrowHelper(dir, corner, L, col(c), L * 0.18, L * 0.1));
    const tag = document.createElement('div');
    tag.className = 'ax-3d-label'; tag.textContent = `${n}, mm`;
    const o = new T.CSS2DObject(tag); o.position.copy(dir.multiplyScalar(L * 1.25).add(corner)); scene.add(o);
  });
}
key.position.set(centre.x + R * 2, centre.y - R * 1.5, centre.z + R * 3);
fill.position.set(centre.x - R * 2, centre.y + R * 2, centre.z + R);
camera.near = R / 200; camera.far = R * 60; camera.updateProjectionMatrix();
$('#cv-legend').innerHTML = (REP ? [['critical', 'named in a fail (outline)'], ['warning', 'selected warn'], ['accent', 'under the mouse']] : [['accent', 'under the mouse']])
  .map(([c, t]) => `<span style="--c:var(--ax-${c})">${t}</span>`).join('');

// ── camera framing ──
let fly = null;
function frame(box, now) {
  const s = box.getBoundingSphere(new T.Sphere());
  const r = Math.max(s.radius, R * 0.04);
  const dir = camera.position.clone().sub(controls.target);
  if (dir.lengthSq() < 1e-9) dir.set(1.1, -1.6, 0.9);
  dir.normalize();
  const dist = r / Math.sin(camera.fov * DEG / 2) * 1.15;
  const to = { target: s.center.clone(), pos: s.center.clone().add(dir.multiplyScalar(dist)) };
  if (now || TEST || matchMedia('(prefers-reduced-motion: reduce)').matches) { controls.target.copy(to.target); camera.position.copy(to.pos); controls.update(); fly = null; return; }
  fly = { t: 0, from: { target: controls.target.clone(), pos: camera.position.clone() }, to };
}
camera.position.copy(centre).add(new T.Vector3(1.1, -1.6, 0.9).multiplyScalar(R));
controls.target.copy(centre);
frame(home, true);
const endPos = camera.position.clone();
camera.position.sub(controls.target).multiplyScalar(TEST ? 1 : 1.6).add(controls.target);   // ax-three's dolly-in
fly = TEST ? null : { t: 0, from: { target: controls.target.clone(), pos: camera.position.clone() }, to: { target: controls.target.clone(), pos: endPos } };

// ── joint sliders ──
const rowsEl = $('#joints');
const unit = j => (j.kind === 'prismatic' ? 'mm' : '°');
for (const j of DATA.joints) {
  const row = document.createElement('div');
  row.className = 'joint';
  const c = coupled[j.name];
  let lo = j.lo, hi = j.hi, note = '';
  if (j.continuous) { lo = 0; hi = 360; note = 'continuous'; }
  const ranged = j.axis && lo != null && !c;
  const label = j.name.replace(/^PIV_/, '');
  if (c) note = `follows ${c.to.replace(/^PIV_/, '')} × ${+c.ratio.toFixed(4)}`;
  else if (!j.axis) note = 'no axis: fixed';
  else if (lo == null) note = 'no range: cadcheck holds it at home';
  row.innerHTML = `<div class="row"><span class="ax-label">${esc(label)} · ${j.kind === 'prismatic' ? 'slide' : 'turn'} ${j.axis || ''}</span><b><span>0</span><small>${unit(j)}</small></b></div>` +
    (ranged ? `<input class="ax-range" type="range" min="${lo}" max="${hi}" step="any" aria-label="${esc(label)}">` +
      `<div class="lim"><span>${+(+lo).toFixed(2)}</span><span>${note}</span><span>${+(+hi).toFixed(2)}</span></div>` : `<div class="lim"><span>${esc(note)}</span></div>`);
  if (!ranged) row.classList.add('follow');
  rowsEl.appendChild(row);
  const input = row.querySelector('input');
  if (input) input.addEventListener('input', () => { S.pose[j.name] = +input.value; applyPose(); });
  row.addEventListener('pointerdown', () => focusJoint(j.name));
  rows[j.name] = { row, input, out: row.querySelector('b span'), b: row.querySelector('b'), j, lo, hi };
}
if (!DATA.joints.length) rowsEl.innerHTML = '<div class="cv-empty">No PIV_ joints in this blend: nothing moves.</div>';
function updateReadouts() {
  const v = values(S.pose);
  for (const [n, r] of Object.entries(rows)) {
    const x = v[n];
    r.out.textContent = (+x.toFixed(2)).toString();
    const past = r.lo != null && !r.j.continuous && (x < r.lo - 1e-6 || x > r.hi + 1e-6);
    r.b.classList.toggle('past', past);
    r.b.title = past ? 'past the joint limit (cadcheck overtravel pose)' : '';
    if (r.input && document.activeElement !== r.input) r.input.value = r.j.continuous ? ((x % 360) + 360) % 360 : x;
  }
}
function focusJoint(n) {
  for (const [k, r] of Object.entries(rows)) r.row.classList.toggle('focus', k === n);
  if (n && rows[n]) rows[n].row.scrollIntoView({ block: 'nearest', behavior: TEST ? 'auto' : 'smooth' });
}

// ── findings list ──
const fl = $('#findings');
let filt = 'all';
if (REP) {
  $('#cv-filter').hidden = false;
  const acc = FINDS.filter(f => f.accepted).length;
  $('#cv-fcap').textContent = FINDS.length ? `${FINDS.length} from ${REP.file}${acc ? `, ${acc} accepted` : ''}. Click one to pose the model there.` : `${REP.file}: no fails or warns.`;
}
const els = FINDS.map((f, i) => {
  const d = document.createElement('div');
  d.className = 'cv-f ' + f.status + (f.accepted ? ' accepted' : '');
  const st = f.status === 'fail' ? '<span class="ax-status critical">Fail</span>' : `<span class="ax-status warning">${f.accepted ? 'Warn, accepted' : 'Warn'}</span>`;
  d.innerHTML = `<div class="hd">${st}<span>${esc(f.check)}</span><span class="pose">${esc(f.pose_s || '')}</span></div><div class="msg">${esc(f.msg)}</div>` +
    (f.missing.length ? `<div class="miss">not in this model: ${esc(f.missing.join(', '))}</div>` : '') +
    (f.accepted ? `<div class="msg">why: ${esc(f.accepted)}</div>` : '');
  d.title = f.names.length ? f.names.join(', ') : 'names no object';
  d.addEventListener('click', () => selectFinding(S.sel === f ? null : f));
  fl.appendChild(d);
  return d;
});
function listFilter() {
  const q = $('#cv-q').value.trim().toLowerCase();
  let shown = 0;
  FINDS.forEach((f, i) => {
    const ok = (filt === 'all' || f.status === filt) && (!q || (f.check + ' ' + f.msg).toLowerCase().includes(q)) && (!S.partFilter || f.names.includes(S.partFilter));
    els[i].hidden = !ok; shown += ok;
  });
  let e = $('#cv-none');
  if (!e) { e = document.createElement('div'); e.id = 'cv-none'; e.className = 'cv-empty'; fl.appendChild(e); }
  e.hidden = shown > 0 || !REP;
  e.textContent = S.partFilter ? `No findings name ${S.partFilter}. Click it again to show all.` : 'Nothing matches the filter.';
}
$('#cv-filter').addEventListener('click', e => {
  const b = e.target.closest('[data-f]'); if (!b) return;
  filt = b.dataset.f;
  document.querySelectorAll('#cv-filter [data-f]').forEach(x => x.classList.toggle('on', x === b));
  listFilter();
});
$('#cv-q').addEventListener('input', listFilter);
listFilter();

// markers: a finding's points and box, shown only at its pose (they are world coordinates at that pose)
function updateMarkers() {
  const f = S.sel;
  markers.visible = !!f && S.explode === 0 && samePose(f.pose || {}, S.pose);
}
function samePose(a, b) {
  const va = values(a), vb = values(b);
  return Object.keys(va).every(k => Math.abs(va[k] - vb[k]) < 1e-6);
}
function selectFinding(f) {
  S.sel = f;
  els.forEach((e, i) => e.classList.toggle('on', FINDS[i] === f));
  markers.clear();
  if (f) {
    S.pose = { ...(f.pose || {}) };
    S.explode = 0; $('#cv-explode').value = 0;
    const c = col(f.status === 'fail' ? 'critical' : 'warning');
    for (const p of f.points) {
      const s = new T.Mesh(new T.SphereGeometry(R * 0.008, 16, 12), new T.MeshBasicMaterial({ color: c, depthTest: false, transparent: true }));
      s.position.set(...p); s.renderOrder = 10; markers.add(s);
    }
    if (f.box) { const h = new T.Box3Helper(new T.Box3(new T.Vector3(...f.box[0]), new T.Vector3(...f.box[1])), c); h.material.depthTest = false; h.renderOrder = 10; markers.add(h); }
    applyPose();
    const b = new T.Box3();
    for (const n of f.names) if (P[n]) b.union(worldBox(n));
    for (const p of f.points) b.expandByPoint(new T.Vector3(...p));
    if (f.box) { b.expandByPoint(new T.Vector3(...f.box[0])); b.expandByPoint(new T.Vector3(...f.box[1])); }
    frame(b.isEmpty() ? home : b);
    const jn = Object.keys(f.pose || {})[0] || (f.names.map(n => P[n] && P[n].info.body).find(Boolean));
    focusJoint(jn);
  } else applyPose();
  restyle();
}

// ── hover, tooltip and click ──
const ray = new T.Raycaster(), mouse = new T.Vector2();
let mouseEv = null, down = null;
let tip = document.querySelector('.ax-tip');
if (!tip) { tip = document.createElement('div'); tip.className = 'ax-tip'; document.body.appendChild(tip); }
let pickDirty = false;   // raycast only when the mouse or the camera moved: v2a7 has 424k triangles
renderer.domElement.addEventListener('pointermove', e => { mouseEv = e; pickDirty = true; });
controls.addEventListener('change', () => (pickDirty = true));
renderer.domElement.addEventListener('pointerleave', () => { mouseEv = null; setHover(null); });
renderer.domElement.addEventListener('pointerdown', e => (down = [e.clientX, e.clientY]));
renderer.domElement.addEventListener('click', e => {
  if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;   // that was an orbit drag
  clickPart(S.hover);
});
function pick() {
  if (!mouseEv) return null;
  const r = renderer.domElement.getBoundingClientRect();
  mouse.set(((mouseEv.clientX - r.left) / r.width) * 2 - 1, -((mouseEv.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  for (const h of ray.intersectObjects(pickables, false)) {
    const n = h.object.userData.cv;
    if (S.section && clipPlane.distanceToPoint(h.point) < 0) continue;   // cut away
    if (P[n].mat.opacity < 0.5) continue;                                // ghosted
    return n;
  }
  return null;
}
function setHover(n) {
  if (S.hover === n) return;
  S.hover = n;
  renderer.domElement.style.cursor = n ? 'pointer' : '';
  if (!n) tip.style.display = 'none';
  restyle();
}
const ROLE = { PRT: 'printed', BUY: 'purchased', FST: 'fastener', CAB: 'cable' };
function tipHtml(n) {
  const o = DATA.objects[n], pr = o.props, nf = FINDS.filter(f => f.names.includes(n));
  const fails = nf.filter(f => f.status === 'fail').length, warns = nf.length - fails;
  const lines = [`<b>${esc(n)}</b> · ${ROLE[o.role]}${o.body ? ' · on ' + esc(o.body.replace(/^PIV_/, '')) : ''}`];
  if (pr.orient) lines.push('print: ' + esc(pr.orient));
  const bits = [pr.supports && 'supports ' + pr.supports, pr.infill && 'infill ' + pr.infill + '%', pr.material].filter(Boolean);
  if (bits.length) lines.push(esc(bits.join(' · ')));
  if (nf.length) lines.push(`<span style="color:var(--ax-${fails ? 'critical' : 'warning'})">■</span> ${fails} fail, ${warns} warn: click to list`);
  return lines.join('<br>');
}
function clickPart(n) {
  if (!n) { if (S.partFilter) { S.partFilter = null; listFilter(); } return; }
  focusJoint(P[n].info.body);
  S.partFilter = S.partFilter === n ? null : n;
  listFilter();
}

// ── toolbar ──
$('#cv-home').onclick = () => { S.pose = {}; selectFinding(null); };
$('#cv-fit').onclick = () => { const b = new T.Box3(); for (const n in P) b.union(worldBox(n)); frame(b); };
$('#cv-explode').addEventListener('input', e => { S.explode = +e.target.value; applyPose(); });
const xb = $('#cv-xray');
xb.onclick = () => { S.xray = !S.xray; xb.classList.toggle('on', S.xray); restyle(); };
const fb = $('#cv-fails');
fb.onclick = () => { S.failTint = !S.failTint; fb.classList.toggle('on', S.failTint); fb.textContent = S.failTint ? 'Fails' : 'Fails off'; restyle(); };
if (!failNames.size) fb.hidden = true;
const sb = $('#cv-section'), cut = $('#cv-cut');
function setSection(ax) {
  S.section = ax;
  sb.textContent = 'Section ' + (ax || 'off'); sb.classList.toggle('on', !!ax); cut.hidden = !ax;
  if (ax) {
    const i = 'XYZ'.indexOf(ax), n = new T.Vector3(); n.setComponent(i, -1);
    const lo = home.min.getComponent(i), hi = home.max.getComponent(i);
    clipPlane.normal.copy(n); clipPlane.constant = lo + (hi - lo) * S.cut;   // keeps the side below the cut
  }
  restyle();
}
sb.onclick = () => setSection({ null: 'X', X: 'Y', Y: 'Z', Z: null }[S.section]);
cut.addEventListener('input', () => { S.cut = +cut.value; setSection(S.section); });
addEventListener('keydown', e => {
  if (e.target.closest('input')) return;
  const k = e.key.toLowerCase();
  if (k === 'escape') selectFinding(null);
  else if (k === 'h') $('#cv-home').click();
  else if (k === 'f') $('#cv-fit').click();
  else if (k === 'x') xb.click();
  else if (k === 's') sb.click();
});

// ── loop ──
function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h, false); labels.setSize(w, h);
  renderer.domElement.style.width = '100%'; renderer.domElement.style.height = '100%';
  camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(view);
resize();
const clock = new T.Clock();
let lastHover = null;
renderer.setAnimationLoop(() => {
  const dt = clock.getDelta();
  if (fly) {
    fly.t = Math.min(1, fly.t + dt / 0.6);
    const k = 1 - Math.pow(1 - fly.t, 3);
    controls.target.lerpVectors(fly.from.target, fly.to.target, k);
    camera.position.lerpVectors(fly.from.pos, fly.to.pos, k);
    if (fly.t >= 1) fly = null;
  }
  controls.update();
  if (pickDirty) { pickDirty = false; setHover(pick()); }
  const n = S.hover;
  if (n && mouseEv) {
    if (lastHover !== n) tip.innerHTML = tipHtml(n);
    tip.style.display = 'block'; tip.style.left = mouseEv.clientX + 14 + 'px'; tip.style.top = mouseEv.clientY + 14 + 'px';
  }
  lastHover = n;
  renderer.render(scene, camera);
  labels.render(scene, camera);
});
view.classList.remove('ax-loading');
spin.remove();
restyle();
applyPose();

// ── #selftest: Blender's matrix_world at a spread of poses against this page's, then the UI paths ──
if (TEST) {
  const out = { pass: false, errors, objects: Object.keys(P).length, expected_objects: Object.keys(DATA.objects).length, poses: 0, max_err_mm: 0, worst: null, ui: {} };
  try {
    const corners = b => [0, 1, 2, 3, 4, 5, 6, 7].map(i => new T.Vector3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z));
    for (const e of DATA.expect || []) {
      S.pose = { ...e.pose }; S.explode = 0; applyPose();
      for (const [n, mw] of Object.entries(e.mw)) {
        if (!P[n]) continue;
        setRowMajor(M4, mw);
        for (const c of corners(P[n].box)) {
          const d = c.clone().applyMatrix4(P[n].node.matrixWorld).distanceTo(c.clone().applyMatrix4(M4));
          if (d > out.max_err_mm) { out.max_err_mm = d; out.worst = [n, e.pose]; }
        }
      }
      out.poses++;
    }
    // a slider moves the parts on its joint
    const jr = Object.values(rows).find(r => r.input && Object.values(P).some(p => p.info.body === r.j.name));
    if (jr) {
      S.pose = {}; applyPose();
      const p = Object.values(P).find(q => q.info.body === jr.j.name), cs = corners(p.box), w0 = p.node.matrixWorld.clone();
      jr.input.value = jr.hi; jr.input.dispatchEvent(new Event('input'));
      const moved = Math.max(...cs.map(c => c.clone().applyMatrix4(p.node.matrixWorld).distanceTo(c.clone().applyMatrix4(w0))));
      out.ui.slider = { joint: jr.j.name, to: jr.hi, part: p.name, moved_mm: +moved.toFixed(3) };
      // every slider reaches its limits and home exactly (a fixed step missed hood's 0.327 limit: review)
      out.ui.reach = [];
      for (const r of Object.values(rows)) {
        if (!r.input) continue;
        for (const x of r.j.continuous ? [0, 359.5] : [r.lo, r.hi, r.j.home || 0]) {
          r.input.value = x; r.input.dispatchEvent(new Event('input'));
          if (Math.abs(values(S.pose)[r.j.name] - x) > 1e-9) out.ui.reach.push([r.j.name, x, values(S.pose)[r.j.name]]);
        }
      }
    }
    // clicking the first finding with a pose (a fail if there is one) poses the model there and lights its objects
    const posed = f => f.pose && Object.keys(f.pose).length && f.names.length;
    let fi = FINDS.findIndex(f => f.status === 'fail' && posed(f));
    if (fi < 0) fi = FINDS.findIndex(posed);
    if (fi >= 0) {
      els[fi].click();
      const f = FINDS[fi], v = values(S.pose);
      out.ui.finding = { msg: f.msg.slice(0, 80), pose: f.pose, page_pose: Object.fromEntries(Object.keys(f.pose).map(k => [k, v[k]])),
        sliders: Object.fromEntries(Object.keys(f.pose).filter(k => rows[k] && rows[k].input).map(k => [k, +rows[k].input.value])),
        lit: f.names.filter(n => P[n] && P[n].mat.emissive.r > 0.1), markers: markers.children.length, markers_visible: markers.visible };
    }
    out.ui.explode = (() => { S.pose = {}; selectFinding(null); const n = Object.keys(P)[0], a = worldBox(n).getCenter(new T.Vector3());
      $('#cv-explode').value = 1; $('#cv-explode').dispatchEvent(new Event('input')); const d = worldBox(n).getCenter(new T.Vector3()).distanceTo(a);
      $('#cv-explode').value = 0; $('#cv-explode').dispatchEvent(new Event('input')); return +d.toFixed(2); })();
    sb.click(); xb.click(); restyle(); renderer.render(scene, camera); sb.click(); sb.click(); sb.click(); xb.click();
    out.pass = !errors.length && out.objects === out.expected_objects && out.poses > 0 && out.max_err_mm < 0.01 &&
      (!out.ui.slider || out.ui.slider.moved_mm > 0.01) && !(out.ui.reach || []).length &&
      (!out.ui.finding || (Object.keys(out.ui.finding.pose).every(k => Math.abs(out.ui.finding.pose[k] - out.ui.finding.page_pose[k]) < 1e-6) && out.ui.finding.lit.length > 0));
  } catch (err) { errors.push(String(err.stack || err)); }
  const pre = document.createElement('pre');
  pre.id = 'cv-selftest'; pre.textContent = 'CVTEST ' + JSON.stringify(out);
  document.body.appendChild(pre);
  document.title = 'CVTEST ' + (out.pass ? 'PASS' : 'FAIL');
}
window.cadview = { S, P, rows, FINDS, selectFinding, applyPose, values };
})().catch(err => {
  const pre = document.createElement('pre');
  pre.id = 'cv-selftest'; pre.textContent = 'CVTEST ' + JSON.stringify({ pass: false, errors: [String(err.stack || err)] });
  document.body.appendChild(pre);
  const v = document.getElementById('view');
  if (v) { v.classList.remove('ax-loading'); v.querySelectorAll('.ax-spin-wrap').forEach(e => e.remove()); v.insertAdjacentHTML('beforeend', `<div class="cv-empty" style="padding:16px">Could not load the model: ${String(err).replace(/</g, '&lt;')}</div>`); }
});
