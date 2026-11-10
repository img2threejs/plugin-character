// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { Bone, BufferGeometry, Float32BufferAttribute, Matrix4, MeshBasicMaterial, Skeleton, SkinnedMesh, Triangle, Uint16BufferAttribute, Vector3 } from 'three';
import { CONTACT_STEADY, CUP_LIFT, PANEL, PULL_PATCH, SKIN_GUARD, STRAP, STRAP_FIELD, TRANSITION, createGarments, fallProfile, limitPull, recolorPixels, strapCoordinate, transitionPhase } from '../../runtime/garment-character/garment.mjs';
import { buildGraph, distanceField, falloffSlope } from '../../runtime/garment-character/garment-field.mjs';


// Cup (7x7, 1.5 mm above the skin plane z=0.1) with a ribbon strip above it, on one skin plane.
function fixture() {
  const positions = [], indices = [], cupCount = 49;
  for (let j = 0; j < 7; j++) for (let i = 0; i < 7; i++) positions.push(0.03 + i * 0.015, 1.33 + j * 0.015, 0.1015);
  for (let r = 0; r < 7; r++) for (let c = 0; c < 2; c++) positions.push(0.07 + c * 0.006, 1.43 + r * 0.01, 0.1015);
  for (let j = 0; j < 6; j++) for (let i = 0; i < 6; i++) { const a = j * 7 + i; indices.push(a, a + 1, a + 7, a + 1, a + 8, a + 7); }
  for (let r = 0; r < 6; r++) { const v = cupCount + r * 2; indices.push(v, v + 1, v + 2, v + 1, v + 3, v + 2); }
  const total = positions.length / 3, geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Uint16Array(total * 4), 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: total * 4 }, (_, i) => i % 4 === 0 ? 1 : 0), 4));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  const material = new MeshBasicMaterial(), mesh = new SkinnedMesh(geometry, material), bone = new Bone();
  mesh.name = 'BikiniTop'; mesh.add(bone); mesh.bind(new Skeleton([bone])); mesh.updateMatrixWorld(true);
  const rest = geometry.attributes.position.array.slice();
  const bodyGeometry = new BufferGeometry();
  bodyGeometry.setAttribute('position', new Float32BufferAttribute([-0.3, 1.2, 0.1, 0.3, 1.2, 0.1, -0.3, 1.65, 0.1, 0.3, 1.65, 0.1], 3));
  bodyGeometry.setIndex([0, 1, 2, 1, 3, 2]); bodyGeometry.computeVertexNormals();
  const rig = { meshes: new Map([['BikiniTop', { geometry, rest, positions: geometry.attributes.position.array, fromShared: new Matrix4(), indices: geometry.index.array,
    masks: new Map([['chest-left', new Float32Array(total).fill(1)], ['chest-right', new Float32Array(total)]]) }],
    ['Body', { geometry: bodyGeometry, toShared: new Matrix4(), rest: bodyGeometry.attributes.position.array.slice(), positions: bodyGeometry.attributes.position.array, indices: bodyGeometry.index.array }]]),
    regions: new Map([['chest-left', { id: 'chest-left', profile: { cap: 0.008 } }]]), setTension() {} };
  const garments = createGarments({ bikini: mesh, rig });
  return { garments, mesh, geometry, rest, cupCount, rendered: mesh.geometry.attributes.position.array,
    dispose() { garments.dispose(); geometry.dispose(); bodyGeometry.dispose(); material.dispose(); mesh.skeleton.dispose(); } };
}
test('neck release comes first, ribbon and flap fall, recolor happens while fallen, then lift and reseat exactly', () => {
  const at = (t) => transitionPhase(t);
  assert.deepEqual([at(0).fold, at(0).cut, at(0).morph], [0, 0, 0]);
  assert.equal(at(TRANSITION.release[1]).cut, 1, 'ribbon fully released before anything falls');
  let previousMorph = 0;
  for (let t = 0; t <= TRANSITION.duration; t += 0.005) {
    const { fold, cut, morph } = at(t);
    assert.ok(fold >= 0 && fold <= 1 && cut >= 0 && cut <= 1 && morph >= previousMorph - 1e-12, `bounded at ${t}`);
    if (fold > 0) assert.equal(cut, 1, `nothing falls while the ribbon is attached (t=${t})`);
    if (morph > 0 && morph < 1) assert.ok(fold > 0.8 && cut === 1, `recolor only while fallen (t=${t})`);
    if (cut < 1 && t > TRANSITION.release[1]) assert.equal(fold, 0, `ribbon is back down before it reseats (t=${t})`);
    previousMorph = morph;
  }
  const end = at(TRANSITION.duration);
  assert.deepEqual([end.fold, end.cut, end.morph, end.done], [0, 0, 1, true]);
  for (let t = 0; t <= 0.4; t += 0.02) {
    const reduced = transitionPhase(t, true);
    assert.deepEqual([reduced.fold, reduced.cut, reduced.glow], [0, 0, 0], 'reduced motion never folds or flashes');
  }
  assert.equal(transitionPhase(0.4, true).done, true);
});

test('the fall accelerates to touchdown, bounces a little and settles on the cup', () => {
  assert.equal(fallProfile(0), 0); assert.equal(fallProfile(1), 1);
  let previous = 0;
  for (let x = 0; x <= 0.6; x += 0.01) { const v = fallProfile(x); assert.ok(v >= previous - 1e-12, 'monotonic until touchdown'); previous = v; }
  assert.ok(Math.abs(fallProfile(0.6) - 1) < 1e-9);
  let low = 1;
  for (let x = 0.6; x <= 1; x += 0.005) { const v = fallProfile(x); assert.ok(v <= 1 + 1e-12 && v > 0.8); low = Math.min(low, v); }
  assert.ok(low < 0.97, 'a visible bounce after landing');
});

test('strap coordinates cover the halter ribbon only, not cups or the neck loop', () => {
  assert.equal(strapCoordinate(0.07, 1.41, 0.08).side, 0, 'cup below the apex');
  const right = strapCoordinate(0.06, 1.47, 0.02), left = strapCoordinate(-0.06, 1.47, 0.02);
  assert.equal(right.side, 1); assert.equal(left.side, -1);
  assert.ok(right.s > 0 && right.s < 1); assert.equal(right.s, left.s);
  assert.equal(strapCoordinate(0.02, 1.5, -0.05).side, 0, 'neck loop behind the neck');
});

test('pulled strap never enters the body and stretches with increasing resistance', () => {
  const normal = new Vector3(0, 0, 1);
  const inward = limitPull(new Vector3(0.01, 0, -0.05), normal);
  assert.ok(inward.z >= 0 && Math.abs(inward.x - 0.01) < 1e-3);
  const small = limitPull(new Vector3(0.005, 0, 0), normal).length(), large = limitPull(new Vector3(1, 0, 0), normal).length();
  assert.ok(small > 0.0049 && small < 0.005, 'small pulls follow the pointer');
  assert.ok(large <= STRAP.maxPull && large > STRAP.maxPull * 0.99, 'far pulls saturate at the elastic limit');
});

test('fabric and strap grabs are independent, bounded, mutually exclusive per side, and recover exactly', () => {
  const geometry = new BufferGeometry(), positions = [], indices = [];
  for (let y = 0; y < 5; y++) for (let x = 0; x < 5; x++) positions.push(0.02 + x * 0.025, 1.32 + y * 0.025, 0.1);
  for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
    const i = y * 5 + x; indices.push(i, i + 1, i + 5, i + 1, i + 6, i + 5);
  }
  positions.push(0.05, 1.45, 0.04, 0.06, 1.46, 0.04, 0.05, 1.47, 0.04);
  indices.push(25, 26, 27);
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Uint16Array(28 * 4), 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: 28 * 4 }, (_, i) => i % 4 === 0 ? 1 : 0), 4));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  const material = new MeshBasicMaterial(), mesh = new SkinnedMesh(geometry, material), bone = new Bone();
  mesh.name = 'BikiniTop'; mesh.add(bone); mesh.bind(new Skeleton([bone])); mesh.updateMatrixWorld(true);
  const rest = geometry.attributes.position.array.slice(), mask = new Float32Array(28).fill(1);
  const bodyGeometry = new BufferGeometry();
  bodyGeometry.setAttribute('position', new Float32BufferAttribute([-0.3, 1.2, 0.099, 0.3, 1.2, 0.099, -0.3, 1.65, 0.099, 0.3, 1.65, 0.099], 3));
  bodyGeometry.setIndex([0, 1, 2, 1, 3, 2]); bodyGeometry.computeVertexNormals();
  const rig = { meshes: new Map([['BikiniTop', { geometry, rest, positions: geometry.attributes.position.array, fromShared: new Matrix4(), indices: geometry.index.array,
    masks: new Map([['chest-left', mask], ['chest-right', new Float32Array(28)]]) }], ['Body', { geometry: bodyGeometry, toShared: new Matrix4(),
      rest: bodyGeometry.attributes.position.array.slice(), positions: bodyGeometry.attributes.position.array, indices: bodyGeometry.index.array }]]),
    regions: new Map([['chest-left', { id: 'chest-left', profile: { cap: 0.008 } }]]), setTension() {} };
  const garments = createGarments({ bikini: mesh, rig });
  const hit = { object: mesh, faceIndex: 12, face: { a: indices[36], b: indices[37], c: indices[38] }, point: new Vector3(0.07, 1.37, 0.1) };
  const strapHit = { object: mesh, faceIndex: 32, face: { a: 25, b: 26, c: 27 }, point: new Vector3(0.05, 1.46, 0.04) };
  const advance = n => { for (let i = 0; i < n; i++) garments.update(1 / 120); garments.apply(); };
  assert.equal(garments.panelSide(hit), 1); assert.equal(garments.strapSide(hit), 0);
  assert.equal(garments.panelSide(strapHit), 0); assert.equal(garments.strapSide(strapHit), 1);
  assert.equal(mesh.geometry.attributes.aPanel.getX(12), 1, 'the cup vertices are tagged as cup'); assert.equal(mesh.geometry.attributes.aPanel.getX(25), 0, 'the ribbon is not cup');
  assert.ok(garments.grabPanel(hit, 1));
  assert.equal(garments.grabStrap(strapHit, 1), false, 'a second pointer cannot overwrite same-side tension');
  garments.dragPanel(1, hit.point.clone().add(new Vector3(1, 0.2, -1))); advance(120);
  const panel = garments.getState().panels[0];
  assert.ok(Math.hypot(...panel.offset) > 0.01 && Math.hypot(...panel.offset) <= PANEL.maxPull);
  assert.ok(panel.offset[2] >= 0, 'fabric cannot be dragged inward');
  assert.deepEqual(garments.getState().straps[0].offset, [0, 0, 0], 'panel does not stretch strap');
  const rendered = mesh.geometry.attributes.position.array;
  const strapDistance = new Vector3().fromArray(rest, 25 * 3).distanceTo(new Vector3(...panel.center)), strapMoved = Math.hypot(rendered[75] - rest[75], rendered[76] - rest[76], rendered[77] - rest[77]);
  if (strapDistance < 0.9 * panel.reach) assert.ok(strapMoved > 0.0001, 'a ribbon inside the pulled patch follows the cup');
  else if (strapDistance >= panel.reach) assert.equal(strapMoved, 0, 'a ribbon beyond the pulled patch stays put');
  assert.ok(rendered[12 * 3 + 2] >= 0.0998 && rendered[12 * 3 + 2] <= 0.1016, 'cloth remains close to the body plane');
  garments.releasePanel(1); advance(360);
  assert.deepEqual(garments.getState().panels[0].offset, [0, 0, 0]);
  assert.ok(garments.grabStrap(strapHit, 1));
  garments.dragStrap(1, strapHit.point.clone().add(new Vector3(0.02, 0, 0.01))); advance(120);
  assert.ok(Math.hypot(...garments.getState().straps[0].offset) > 0.01);
  assert.deepEqual(garments.getState().panels[0].offset, [0, 0, 0], 'strap does not pinch panel');
  assert.ok(Math.abs(rendered[12 * 3] - rest[12 * 3]) > 0.0001, 'pulling strap carries cup fabric');
  assert.deepEqual(geometry.attributes.position.array, rest, 'render deformation does not contaminate soft solver');
  garments.reset();
  garments.apply(); assert.deepEqual(rendered, rest, 'reset restores exact render positions');
  for (const part of [...garments.getState().panels, ...garments.getState().straps]) {
    assert.equal(part.grabbed, false); assert.deepEqual(part.offset, [0, 0, 0]);
  }
  assert.deepEqual(geometry.attributes.position.array, rest, 'garment mechanics preserve solver geometry');
  garments.dispose(); assert.equal(mesh.material, material);
  geometry.dispose(); bodyGeometry.dispose(); material.dispose(); mesh.skeleton.dispose();
});

test('a cup pull carries the nearest half of ALL garment vertices, and nothing beyond it moves', () => {
  const f = fixture(), total = f.rest.length / 3;
  const hit = { object: f.mesh, faceIndex: 42, face: { a: 24, b: 25, c: 31 }, point: new Vector3(0.09, 1.375, 0.1015) };
  assert.equal(f.garments.panelSide(hit), 1);
  assert.ok(f.garments.grabPanel(hit, 1));
  const { reach, reachCount, share } = f.garments.getState().panels[0];
  const center = new Vector3();
  for (const i of [24, 25, 31]) center.add(new Vector3().fromArray(f.rest, i * 3));
  center.divideScalar(3);
  const distances = Array.from({ length: total }, (_, i) => new Vector3().fromArray(f.rest, i * 3).distanceTo(center));
  const sorted = [...distances].sort((x, y) => x - y);
  // Distance is measured along the garment, so it can only be longer than the straight distance.
  assert.ok(reach >= sorted[Math.floor(total * PULL_PATCH.share)] - 1e-6, 'reach is at least the straight half-way distance');
  assert.ok(Math.abs(reachCount - Math.floor(total * PULL_PATCH.share)) <= 1, `the patch holds half of ALL garment vertices (${reachCount} of ${total})`);
  assert.equal(share, 0, 'no second cup in this fixture to carry along');
  f.garments.dragPanel(1, hit.point.clone().add(new Vector3(0.05, 0.03, 0.0)));
  for (let i = 0; i < 180; i++) f.garments.update(1 / 120);
  f.garments.apply();
  const moved = [];
  for (let i = 0; i < total; i++) if (Math.hypot(f.rendered[i * 3] - f.rest[i * 3], f.rendered[i * 3 + 1] - f.rest[i * 3 + 1], f.rendered[i * 3 + 2] - f.rest[i * 3 + 2]) > 1e-7) moved.push(i);
  assert.ok(moved.length >= 8, 'a patch moves, not one vertex');
  for (const i of moved) assert.ok(distances[i] <= reach + 1e-9, `vertex ${i} moved beyond the patch`);
  f.dispose();
});

test('both ribbons fold down with a small piece of cup, stay above the skin, leave the rest of the cup alone, and restore exactly', () => {
  const f = fixture(), { garments, rest, rendered } = f, total = rest.length / 3;
  const move = (i) => Math.hypot(rendered[i * 3] - rest[i * 3], rendered[i * 3 + 1] - rest[i * 3 + 1], rendered[i * 3 + 2] - rest[i * 3 + 2]);
  garments.apply();
  assert.deepEqual(rendered, rest, 'no fold, no change');
  garments.applyPhase({ fold: 1, cut: 1, glow: 0, morph: 0 }); garments.apply();
  const ribbon = [], cup = [];
  for (let i = 0; i < total; i++) (i >= f.cupCount ? ribbon : cup).push(i);
  for (const i of ribbon) assert.ok(move(i) > 0.02, `ribbon vertex ${i} falls with the flap`);
  for (const i of cup) if (rest[i * 3 + 1] <= 1.39 + 1e-9) assert.ok(move(i) < 1e-9, `cup vertex ${i} below the hinge stays put`);
  const flap = cup.filter((i) => move(i) > 0.003);
  assert.ok(flap.length >= 4 && flap.length <= Math.floor(cup.length * 0.35), `a small piece of cup falls (${flap.length} of ${cup.length})`);
  for (const i of flap) assert.ok(rest[i * 3 + 1] > 1.39, 'only cloth above the hinge folds');
  for (let i = 0; i < total; i++) assert.ok(rendered[i * 3 + 2] >= 0.1 + 0.0008 - 1e-9, `vertex ${i} stays above the skin plane`);
  garments.applyPhase({ fold: 0.4, cut: 1, glow: 0, morph: 0 }); garments.apply();
  const partial = ribbon.reduce((sum, i) => sum + move(i), 0);
  garments.applyPhase({ fold: 1, cut: 1, glow: 0, morph: 0 }); garments.apply();
  assert.ok(ribbon.reduce((sum, i) => sum + move(i), 0) > partial, 'more fold, more fall');
  garments.applyPhase({ fold: 0, cut: 0, glow: 0, morph: 0 }); garments.apply();
  assert.deepEqual(rendered, rest, 'unfold restores exact rest');
  assert.deepEqual(f.geometry.attributes.position.array, rest, 'the soft-tissue solver geometry is never touched');
  f.dispose();
});

test('pulling a ribbon carries its cup along the skin, lifts it off the skin more toward the pull, never into the skin, and settles back exactly', () => {
  const f = fixture(), { garments, rest, rendered } = f, cup = Array.from({ length: f.cupCount }, (_, i) => i), restHeight = 0.0015;
  const height = (i) => rendered[i * 3 + 2] - 0.1;
  const hit = { object: f.mesh, faceIndex: 0, face: { a: 51, b: 52, c: 53 }, point: new Vector3(0.07, 1.44, 0.1015) };
  assert.equal(garments.strapSide(hit), 1);
  assert.ok(garments.grabStrap(hit, 1));
  garments.dragStrap(1, hit.point.clone().add(new Vector3(0.03, 0.02, 0.01)));
  for (let i = 0; i < 240; i++) garments.update(1 / 120);
  garments.apply();
  const [ox, oy, oz] = garments.getState().straps[0].offset, length = Math.hypot(ox, oy, oz);
  assert.ok(length > 0.015, 'the ribbon is genuinely pulled');
  const lifted = cup.filter((i) => height(i) - restHeight > 0.002);
  assert.ok(lifted.length >= 3, 'the cup opens a gap above the skin');
  for (const i of cup) {
    assert.ok(height(i) >= restHeight - 1e-6, `cup vertex ${i} never goes into the skin`);
    assert.ok(height(i) - restHeight <= CUP_LIFT.gap + 1e-4, `cup vertex ${i} gap stays bounded`);
  }
  // The cup follows the pull along the skin, bounded so the apex stays covered, and its edge is free.
  const shift = (i) => Math.hypot(rendered[i * 3] - rest[i * 3], rendered[i * 3 + 1] - rest[i * 3 + 1]);
  const alongPull = (i) => ((rendered[i * 3] - rest[i * 3]) * ox + (rendered[i * 3 + 1] - rest[i * 3 + 1]) * oy) / Math.hypot(ox, oy);
  assert.ok(Math.max(...cup.map(alongPull)) > 0.005, 'the cup follows the pull');
  for (const i of cup) assert.ok(shift(i) <= length + 1e-6, `cup vertex ${i} never moves farther than the pull itself`);
  assert.ok(shift(0) > 0, 'the cup edge is free, not pinned');
  assert.ok(shift(24) < Math.max(...cup.map(shift)) + 1e-9, 'the cup is carried by distance, so nothing outruns the vertex nearest the grab');
  // The gap is larger on the side of the cup the pull points toward.
  const centre = [0, 0, 0];
  for (const i of cup) for (let k = 0; k < 3; k++) centre[k] += rest[i * 3 + k] / cup.length;
  const towards = (i) => (rest[i * 3] - centre[0]) * ox + (rest[i * 3 + 1] - centre[1]) * oy;
  const mean = (list) => list.reduce((sum, i) => sum + height(i) - restHeight, 0) / list.length;
  assert.ok(mean(cup.filter((i) => towards(i) > 0)) > mean(cup.filter((i) => towards(i) < 0)), 'the gap opens toward the pull');
  garments.releaseStrap(1);
  for (let i = 0; i < 600; i++) garments.update(1 / 120);
  garments.apply();
  assert.deepEqual(rendered, rest, 'releasing closes the gap exactly');
  f.dispose();
});


// One connected halter chain on a flat skin plane (z = -0.021): ribbon + , neck loop, ribbon - ,
// plus a short under-band stub below each ribbon. Ribbons are z = -0.0195 (strap), the loop
// z = -0.0205 (behind the neck, so not a strap), the band is below the strap start (pinned).
function chainFixture() {
  const positions = [], indices = [], at = {};
  const add = (name, x, y, z) => { at[name] = positions.length / 3; positions.push(x, y, z); };
  const rows = 7, columns = 11;
  for (const side of [1, -1]) {
    for (let r = 0; r < rows; r++) for (const dx of [0.07, 0.076]) add(`rib${side}_${r}_${dx}`, side * dx, 1.43 + r * 0.01, -0.0195);
    for (const dx of [0.07, 0.076]) add(`band${side}_${dx}`, side * dx, 1.42, -0.0195);
  }
  for (let c = 0; c < columns; c++) for (const [r, y] of [[0, 1.5], [1, 1.51]]) add(`loop_${c}_${r}`, 0.073 - c * (0.146 / (columns - 1)), y, -0.0205);
  const tri = (a, b, c) => indices.push(at[a], at[b], at[c]);
  for (const side of [1, -1]) {
    for (let r = 0; r < rows - 1; r++) {
      const a = `rib${side}_${r}_0.07`, b = `rib${side}_${r}_0.076`, c = `rib${side}_${r + 1}_0.07`, d = `rib${side}_${r + 1}_0.076`;
      tri(a, b, c); tri(b, d, c);
    }
    tri(`band${side}_0.07`, `band${side}_0.076`, `rib${side}_0_0.07`); tri(`band${side}_0.076`, `rib${side}_0_0.076`, `rib${side}_0_0.07`);
  }
  for (let c = 0; c < columns - 1; c++) { tri(`loop_${c}_0`, `loop_${c + 1}_0`, `loop_${c}_1`); tri(`loop_${c + 1}_0`, `loop_${c + 1}_1`, `loop_${c}_1`); }
  const top = rows - 1;
  tri(`rib1_${top}_0.07`, `rib1_${top}_0.076`, 'loop_0_0'); tri(`rib1_${top}_0.07`, 'loop_0_0', 'loop_0_1');
  tri(`rib-1_${top}_0.07`, `rib-1_${top}_0.076`, `loop_${columns - 1}_0`); tri(`rib-1_${top}_0.07`, `loop_${columns - 1}_0`, `loop_${columns - 1}_1`);
  const total = positions.length / 3, geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Uint16Array(total * 4), 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: total * 4 }, (_, i) => i % 4 === 0 ? 1 : 0), 4));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  const material = new MeshBasicMaterial(), mesh = new SkinnedMesh(geometry, material), bone = new Bone();
  mesh.name = 'BikiniTop'; mesh.add(bone); mesh.bind(new Skeleton([bone])); mesh.updateMatrixWorld(true);
  const rest = geometry.attributes.position.array.slice();
  const bodyGeometry = new BufferGeometry();
  bodyGeometry.setAttribute('position', new Float32BufferAttribute([-0.3, 1.2, -0.021, 0.3, 1.2, -0.021, -0.3, 1.65, -0.021, 0.3, 1.65, -0.021], 3));
  bodyGeometry.setIndex([0, 1, 2, 1, 3, 2]); bodyGeometry.computeVertexNormals();
  const rig = { meshes: new Map([['BikiniTop', { geometry, rest, positions: geometry.attributes.position.array, fromShared: new Matrix4(), indices: geometry.index.array,
    masks: new Map([['chest-left', new Float32Array(total)], ['chest-right', new Float32Array(total)]]) }],
    ['Body', { geometry: bodyGeometry, toShared: new Matrix4(), rest: bodyGeometry.attributes.position.array.slice(), positions: bodyGeometry.attributes.position.array, indices: bodyGeometry.index.array }]]),
    regions: new Map(), setTension() {} };
  const garments = createGarments({ bikini: mesh, rig });
  const names = Object.keys(at), group = (prefix) => names.filter((n) => n.startsWith(prefix)).map((n) => at[n]);
  return { garments, mesh, geometry, rest, indices, at, rendered: mesh.geometry.attributes.position.array, loop: group('loop_'), ribbonPlus: group('rib1_'), ribbonMinus: group('rib-1_'), band: group('band'),
    dispose() { garments.dispose(); geometry.dispose(); bodyGeometry.dispose(); material.dispose(); mesh.skeleton.dispose(); } };
}
const moved = (f, i) => Math.hypot(f.rendered[i * 3] - f.rest[i * 3], f.rendered[i * 3 + 1] - f.rest[i * 3 + 1], f.rendered[i * 3 + 2] - f.rest[i * 3 + 2]);
const mean = (list, fn) => list.reduce((sum, i) => sum + fn(i), 0) / list.length;
function pullRibbonPlus(f) {
  const a = f.at['rib1_3_0.07'], b = f.at['rib1_3_0.076'], c = f.at['rib1_4_0.07'];
  const hit = { object: f.mesh, faceIndex: 0, face: { a, b, c }, point: new Vector3(0.073, 1.46, -0.0195) };
  assert.equal(f.garments.strapSide(hit), 1);
  assert.ok(f.garments.grabStrap(hit, 1));
  f.garments.dragStrap(1, hit.point.clone().add(new Vector3(0.03, 0.02, 0)));
  for (let i = 0; i < 240; i++) f.garments.update(1 / 120);
  f.garments.apply();
}

test('pulling one ribbon carries the whole chain: ribbon, neck loop and the other ribbon, less with distance along the garment, while the under band stays', () => {
  const f = chainFixture();
  pullRibbonPlus(f);
  const state = f.garments.getState().straps.find((s) => s.side === 1);
  assert.ok(Math.hypot(...state.offset) > 0.02, 'the ribbon is genuinely pulled');
  const ribbonMean = mean(f.ribbonPlus, (i) => moved(f, i)), loopMean = mean(f.loop, (i) => moved(f, i)), otherMean = mean(f.ribbonMinus, (i) => moved(f, i));
  assert.ok(ribbonMean > loopMean && loopMean > otherMean && otherMean > 0, `influence falls along the garment: ribbon ${ribbonMean}, loop ${loopMean}, other ribbon ${otherMean}`);
  assert.ok(loopMean > 0.003, 'the neck loop is genuinely carried, not pinned');
  // The loop weakens steadily from the pulled side to the far side.
  const column = (c) => mean([f.at[`loop_${c}_0`], f.at[`loop_${c}_1`]], (i) => moved(f, i));
  for (let c = 1; c < 11; c++) assert.ok(column(c) <= column(c - 1) + 1e-4, `loop column ${c} moves no more than column ${c - 1}`);
  for (const i of f.band) assert.equal(moved(f, i), 0, 'the under band is held');
  f.garments.releaseStrap(1);
  for (let i = 0; i < 800; i++) f.garments.update(1 / 120);
  f.garments.apply();
  assert.deepEqual(f.rendered, f.rest, 'releasing restores the chain exactly');
  f.dispose();
});

test('the garment stays in one piece: along the skin no edge stretches more than the field slope allows, and the standoff stays within its cap', () => {
  const f = chainFixture();
  pullRibbonPlus(f);
  const state = f.garments.getState().straps.find((x) => x.side === 1), pull = Math.hypot(...state.offset);
  // Two smooth weights multiply: the pull kernel and the fade toward the pinned band.
  const slope = falloffSlope(0, state.reach) + 1.5 / STRAP_FIELD.pinRange;
  let worstStretch = 0, checked = 0;
  const inPlane = (P, a, b) => Math.hypot(P[a * 3] - P[b * 3], P[a * 3 + 1] - P[b * 3 + 1]);
  for (let t = 0; t < f.indices.length; t += 3) for (let k = 0; k < 3; k++) {
    const a = f.indices[t + k], b = f.indices[t + (k + 1) % 3];
    const restLength = inPlane(f.rest, a, b), nowLength = inPlane(f.rendered, a, b);
    const bound = restLength * (1 + pull * slope) + 1e-6;
    assert.ok(nowLength <= bound, `edge ${a}-${b} stretched along the skin from ${restLength} to ${nowLength}, bound ${bound}`);
    worstStretch = Math.max(worstStretch, nowLength / restLength); checked++;
  }
  assert.ok(checked > 100, 'every edge was checked');
  assert.ok(worstStretch > 1.05, 'the pull really stretched something, so the bound above is not vacuous');
  let maxStandoff = 0;
  for (let i = 0; i < f.rest.length / 3; i++) maxStandoff = Math.max(maxStandoff, f.rendered[i * 3 + 2] - f.rest[i * 3 + 2]);
  assert.ok(maxStandoff > 0.002 && maxStandoff <= CUP_LIFT.gap + 1e-6, `the garment stands off the skin, within the cap (${maxStandoff})`);
  f.dispose();
});

test('how far a ribbon pull reaches is computed from the garment: the surface distance to the mirror point on the other ribbon', () => {
  const f = chainFixture();
  pullRibbonPlus(f);
  const total = f.rest.length / 3, ids = [f.at['rib1_3_0.07'], f.at['rib1_3_0.076'], f.at['rib1_4_0.07']];
  const centre = new Vector3();
  for (const i of ids) centre.add(new Vector3().fromArray(f.rest, i * 3));
  centre.divideScalar(3);
  const welded = Uint32Array.from({ length: total }, (_, i) => i);
  const graph = buildGraph(welded, total, f.rest, f.indices), dist = distanceField(graph, f.rest, ids, centre, new Float32Array(total));
  let mirror = -1, best = Infinity;
  for (const i of f.ribbonMinus) { const d = Math.hypot(f.rest[i * 3] + centre.x, f.rest[i * 3 + 1] - centre.y, f.rest[i * 3 + 2] - centre.z); if (d < best) { best = d; mirror = i; } }
  const { reach } = f.garments.getState().straps.find((s) => s.side === 1);
  assert.ok(Math.abs(reach - Math.max(STRAP_FIELD.minReach, STRAP_FIELD.reachFactor * dist[mirror])) < 1e-6, 'reach = reachFactor x surface distance to the mirror point');
  const straight = Math.hypot(2 * centre.x, 0, 0);
  assert.ok(dist[mirror] > straight * 1.5, 'the distance runs around the neck loop, not through the air');
  f.dispose();
});

test('orange colorway re-hues painted green fabric and keeps white stripes and skin', () => {
  const px = new Uint8ClampedArray([25, 190, 140, 255, 245, 245, 245, 255, 240, 200, 170, 255, 10, 110, 70, 255]);
  recolorPixels(px);
  const hue = (r, g, b) => { const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min; return max === r ? (((g - b) / d) % 6) * 60 : max === g ? ((b - r) / d + 2) * 60 : ((r - g) / d + 4) * 60; };
  assert.ok(Math.abs(hue(px[0], px[1], px[2]) - 22) < 3, 'green fabric becomes orange');
  assert.deepEqual([...px.slice(4, 8)], [245, 245, 245, 255], 'white stripe unchanged');
  assert.deepEqual([...px.slice(8, 12)], [240, 200, 170, 255], 'skin-tone pixels unchanged');
  assert.ok(px[12] > px[13] && px[13] > px[14] && px[12] < 200, 'shaded green becomes shaded orange, keeping darkness');
});

// ---- Skin guard: the garment is the outer layer, so no pull may ever put cloth inside the body. ----

// Same cup + ribbon as fixture(), but on a steep gaussian bump (15 mm high, 12 mm sigma) so that cloth dragged
// down its flank would sink several mm into the skin unless the guard lifts it. Skin triangles wind outward (+z).
const bumpHeight = (x, y) => 0.1 + 0.015 * Math.exp(-((x - 0.075) ** 2 + (y - 1.4) ** 2) / (2 * 0.012 ** 2));
function curvedFixture() {
  const positions = [], indices = [], cupCount = 169, standoff = 0.0009;
  const put = (x, y) => positions.push(x, y, bumpHeight(x, y) + standoff);
  for (let j = 0; j < 13; j++) for (let i = 0; i < 13; i++) put(0.03 + i * 0.0075, 1.33 + j * 0.0075);
  for (let r = 0; r < 15; r++) for (let c = 0; c < 2; c++) put(0.07 + c * 0.006, 1.43 + r * 0.005);
  for (let j = 0; j < 12; j++) for (let i = 0; i < 12; i++) { const a = j * 13 + i; indices.push(a, a + 1, a + 13, a + 1, a + 14, a + 13); }
  for (let r = 0; r < 14; r++) { const v = cupCount + r * 2; indices.push(v, v + 1, v + 2, v + 1, v + 3, v + 2); }
  const total = positions.length / 3, geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('skinIndex', new Uint16BufferAttribute(new Uint16Array(total * 4), 4));
  geometry.setAttribute('skinWeight', new Float32BufferAttribute(Array.from({ length: total * 4 }, (_, i) => i % 4 === 0 ? 1 : 0), 4));
  geometry.setIndex(indices); geometry.computeVertexNormals();
  const material = new MeshBasicMaterial(), mesh = new SkinnedMesh(geometry, material), bone = new Bone();
  mesh.name = 'BikiniTop'; mesh.add(bone); mesh.bind(new Skeleton([bone])); mesh.updateMatrixWorld(true);
  const rest = geometry.attributes.position.array.slice();
  const nx = 49, ny = 71, skin = [], skinIndices = []; // x -0.04..0.2, y 1.25..1.6, 5 mm cells
  for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) { const x = -0.04 + i * 0.005, y = 1.25 + j * 0.005; skin.push(x, y, bumpHeight(x, y)); }
  for (let j = 0; j < ny - 1; j++) for (let i = 0; i < nx - 1; i++) { const a = j * nx + i; skinIndices.push(a, a + 1, a + nx, a + 1, a + nx + 1, a + nx); }
  const bodyGeometry = new BufferGeometry();
  bodyGeometry.setAttribute('position', new Float32BufferAttribute(skin, 3));
  bodyGeometry.setIndex(skinIndices); bodyGeometry.computeVertexNormals();
  const rig = { meshes: new Map([['BikiniTop', { geometry, rest, positions: geometry.attributes.position.array, fromShared: new Matrix4(), indices: geometry.index.array,
    masks: new Map([['chest-left', new Float32Array(total).fill(1)], ['chest-right', new Float32Array(total)]]) }],
    ['Body', { geometry: bodyGeometry, toShared: new Matrix4(), rest: bodyGeometry.attributes.position.array.slice(), positions: bodyGeometry.attributes.position.array, indices: bodyGeometry.index.array }]]),
    regions: new Map([['chest-left', { id: 'chest-left', profile: { cap: 0.008 } }]]), setTension() {} };
  const garments = createGarments({ bikini: mesh, rig });
  return { garments, mesh, geometry, rest, cupCount, indices, rendered: mesh.geometry.attributes.position.array,
    skin: { positions: skin, indices: skinIndices },
    dispose() { garments.dispose(); geometry.dispose(); bodyGeometry.dispose(); material.dispose(); mesh.skeleton.dispose(); } };
}

// Signed height above the true skin surface: distance to the closest skin triangle, positive on its outward (+normal) side.
function skinHeightMeter(skin) {
  const { positions, indices } = skin, buckets = new Map(), a = new Vector3(), b = new Vector3(), c = new Vector3(), closest = new Vector3(), p = new Vector3(), n = new Vector3();
  for (let t = 0; t < indices.length; t += 3) {
    const tri = new Triangle(new Vector3().fromArray(positions, indices[t] * 3), new Vector3().fromArray(positions, indices[t + 1] * 3), new Vector3().fromArray(positions, indices[t + 2] * 3));
    const centre = tri.getMidpoint(new Vector3()), key = `${Math.floor(centre.x / 0.02)},${Math.floor(centre.y / 0.02)}`;
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push({ tri, normal: tri.getNormal(new Vector3()) });
  }
  return (x, y, z) => {
    p.set(x, y, z);
    let best = Infinity, sign = 1;
    const bx = Math.floor(x / 0.02), by = Math.floor(y / 0.02); // 3x3 buckets of 2 cm: every triangle within ~2 cm
    for (let i = bx - 1; i <= bx + 1; i++) for (let j = by - 1; j <= by + 1; j++) for (const { tri, normal } of buckets.get(`${i},${j}`) ?? []) {
      tri.closestPointToPoint(p, closest);
      const d = closest.distanceTo(p);
      if (d < best) { best = d; sign = n.copy(p).sub(closest).dot(normal) >= 0 ? 1 : -1; }
    }
    return best === Infinity ? Infinity : sign * best;
  };
}

// Lowest height above the skin over every garment vertex that has moved from rest and every triangle centre that has a
// moved corner (the guard's contract: cloth that stays put keeps its rest gap, whatever that is).
function lowestClearance(f, height) {
  const r = f.rendered, ix = f.indices, rest = f.rest, count = r.length / 3;
  const movedVertex = Array.from({ length: count }, (_, i) => r[i * 3] !== rest[i * 3] || r[i * 3 + 1] !== rest[i * 3 + 1] || r[i * 3 + 2] !== rest[i * 3 + 2]);
  let worst = Infinity, where = '', moved = 0;
  for (let i = 0; i < count; i++) {
    if (!movedVertex[i]) continue;
    moved++;
    const h = height(r[i * 3], r[i * 3 + 1], r[i * 3 + 2]);
    if (h < worst) { worst = h; where = `vertex ${i}`; }
  }
  for (let t = 0; t < ix.length; t += 3) {
    if (!movedVertex[ix[t]] && !movedVertex[ix[t + 1]] && !movedVertex[ix[t + 2]]) continue;
    const x = (r[ix[t] * 3] + r[ix[t + 1] * 3] + r[ix[t + 2] * 3]) / 3, y = (r[ix[t] * 3 + 1] + r[ix[t + 1] * 3 + 1] + r[ix[t + 2] * 3 + 1]) / 3, z = (r[ix[t] * 3 + 2] + r[ix[t + 1] * 3 + 2] + r[ix[t + 2] * 3 + 2]) / 3;
    const h = height(x, y, z);
    if (h < worst) { worst = h; where = `triangle ${t / 3} centre (vertices ${ix[t]},${ix[t + 1]},${ix[t + 2]})`; }
  }
  return { worst, where, moved };
}

const guardDirections = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]];
function guardedPull(kind, dir) {
  // The guard measures height along the interpolated skin normal; this test measures the true nearest
  // distance, and the guard prunes with a few-tenths-of-a-millimetre slack. On this steep bump that can cost
  // ~0.2 mm, so the test demands the cloth stay strictly above the skin by 0.1 mm: far above the
  // -0.5..-5 mm an unguarded pull gives.
  const f = curvedFixture(), { garments, rest, rendered } = f, height = skinHeightMeter(f.skin), clearance = 0.0001;
  const strap = kind === 'strap', side = 1;
  const hit = strap
    ? { object: f.mesh, faceIndex: 0, face: { a: 179, b: 180, c: 181 }, point: new Vector3(0.07, 1.455, bumpHeight(0.07, 1.455) + 0.0009) }
    : { object: f.mesh, faceIndex: 0, face: { a: 47, b: 48, c: 60 }, point: new Vector3(0.09, 1.3525, bumpHeight(0.09, 1.3525) + 0.0009) };
  assert.equal(strap ? garments.strapSide(hit) : garments.panelSide(hit), side, `${kind} hit is on the left chest`);
  assert.ok(strap ? garments.grabStrap(hit, side) : garments.grabPanel(hit, side), `${kind} grabbed`);
  const target = hit.point.clone().add(new Vector3(...dir).multiplyScalar(0.25)); // far past the elastic limit
  (strap ? garments.dragStrap : garments.dragPanel).call(garments, side, target);
  const check = (when, minMoved = 0) => {
    garments.apply();
    const { worst, where, moved } = lowestClearance(f, height);
    assert.ok(moved >= minMoved, `${kind} pull dir [${dir}] ${when}: a patch of cloth moved (${moved} vertices)`);
    assert.ok(worst >= clearance, `${kind} pull dir [${dir}] ${when}: ${where} is ${(worst * 1000).toFixed(2)} mm above the skin, need >= ${(clearance * 1000).toFixed(2)} mm`);
  };
  for (let i = 0; i < 240; i++) { garments.update(1 / 120); if (i % 120 === 59) check(`held, step ${i + 1}`, 10); }
  check('held, step 240', 10);
  const part = (strap ? garments.getState().straps : garments.getState().panels)[0], length = Math.hypot(...part.offset);
  assert.ok(length > 0.01, `${kind} is genuinely pulled (${(length * 1000).toFixed(1)} mm)`);
  for (let i = 0; i < rendered.length / 3; i++) {
    const shift = Math.hypot(rendered[i * 3] - rest[i * 3], rendered[i * 3 + 1] - rest[i * 3 + 1], rendered[i * 3 + 2] - rest[i * 3 + 2]);
    assert.ok(shift <= length + 0.015 + SKIN_GUARD.floor + 0.003, `vertex ${i} moved ${(shift * 1000).toFixed(2)} mm, more than the pull ${(length * 1000).toFixed(2)} mm + 15 mm of skin relief + guard`);
  }
  (strap ? garments.releaseStrap : garments.releasePanel).call(garments, side);
  for (let i = 0; i < 240; i++) { garments.update(1 / 120); if (i % 30 === 29) check(`rebound, step ${i + 1}`); }
  for (let i = 0; i < 360; i++) garments.update(1 / 120);
  garments.apply();
  assert.deepEqual(rendered, rest, `${kind} pull dir [${dir}]: releasing restores the rest pose exactly`);
  f.dispose();
}

test('skin guard: the curved fixture rests just above its steep skin with a thin gap, so only the guard keeps the cloth out of the skin under a pull', () => {
  const f = curvedFixture(), height = skinHeightMeter(f.skin);
  let lowest = Infinity, highest = -Infinity;
  for (let i = 0; i < f.rest.length / 3; i++) { const h = height(f.rest[i * 3], f.rest[i * 3 + 1], f.rest[i * 3 + 2]); lowest = Math.min(lowest, h); highest = Math.max(highest, h); }
  assert.ok(lowest > 0.0004 && highest < 0.0012, `rest vertex gaps ${(lowest * 1000).toFixed(2)}..${(highest * 1000).toFixed(2)} mm: outside the skin, within about a millimetre of it`);
  const bump = Math.max(...Array.from({ length: f.skin.positions.length / 3 }, (_, i) => f.skin.positions[i * 3 + 2])) - 0.1;
  assert.ok(bump > 0.014, 'the skin is steeply curved');
  f.garments.apply(); assert.deepEqual(f.rendered, f.rest, 'no pull, no change');
  f.dispose();
});

for (const kind of ['strap', 'panel']) {
  test(`skin guard: a ${kind} dragged far past its limit in ${guardDirections.length} directions never puts a vertex or triangle centre inside the curved skin, held or rebounding, and restores exactly`, () => {
    for (const dir of guardDirections) guardedPull(kind, dir);
  });
}
