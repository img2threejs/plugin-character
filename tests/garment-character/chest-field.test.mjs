// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BufferAttribute, BufferGeometry, Float32BufferAttribute, Group, Mesh, MeshBasicMaterial } from 'three';
import { ROUND_CHEST, roundChestMasks, roundChestWeight } from '../../runtime/garment-character/chest-field.mjs';

const APEX = { 1: [0.08, 1.35, 0.14], [-1]: [-0.08, 1.35, 0.14] };

// A skin mesh whose authored chest masks are deliberately lopsided (painted only above the apex).
function scene(points) {
  const positions = [...APEX[1], ...APEX[-1], ...points.flat()];
  const count = positions.length / 3;
  const left = new Float32Array(count), right = new Float32Array(count);
  left[0] = 1; right[1] = 1;
  for (let i = 2; i < count; i++) { left[i] = positions[i * 3 + 1] > 1.35 ? 0.9 : 0.1; right[i] = 0; }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('_SOFT_CHEST_LEFT', new BufferAttribute(left, 1));
  geometry.setAttribute('_SOFT_CHEST_RIGHT', new BufferAttribute(right, 1));
  const mesh = new Mesh(geometry, new MeshBasicMaterial());
  mesh.name = 'Body';
  const root = new Group(); root.add(mesh); root.updateMatrixWorld(true);
  const sidecar = { version: 1, meshes: [{ name: 'Body', regions: [
    { id: 'chest-left', attribute: '_SOFT_CHEST_LEFT', bone: 'Spine' }, { id: 'chest-right', attribute: '_SOFT_CHEST_RIGHT', bone: 'Spine' }] }] };
  return { root, mesh, geometry, sidecar, left, right };
}
const weightsOf = (geometry, id) => geometry.getAttribute(`_SOFT_${id}_ROUND`);

test('equal distance from the apex weighs the same in every direction, whatever the authored paint says', () => {
  const ring = [];
  for (const r of [0.06, 0.08]) for (let k = 0; k < 8; k++) ring.push([APEX[1][0] + r * Math.cos(k * Math.PI / 4), APEX[1][1] + r * Math.sin(k * Math.PI / 4), APEX[1][2]]);
  const { root, geometry, sidecar } = scene(ring);
  // Midline fade disabled so only the circular footprint is under test.
  roundChestMasks(root, sidecar, { midline: -1, midlineFade: 0.05 });
  const w = weightsOf(geometry, 'CHEST_LEFT');
  for (const [ringIndex, r] of [[0, 0.06], [1, 0.08]]) {
    const expected = roundChestWeight(r);
    for (let k = 0; k < 8; k++) assert.ok(Math.abs(w.getX(2 + ringIndex * 8 + k) - expected) < 1e-4, `ring ${r} direction ${k * 45} deg`);
  }
  assert.ok(w.getX(2) > 0.5 && roundChestWeight(0.06) > roundChestWeight(0.08), 'weight falls with distance');
  // The authored paint is lopsided, the generated support is not: the lowest point of the ring
  // keeps the same weight as the highest.
  assert.ok(Math.abs(w.getX(2 + 2) - w.getX(2 + 6)) < 1e-4);
});

test('the support is zero at the sternum seam and behind the torso, and full at the apex', () => {
  const { root, geometry, sidecar } = scene([[0.003, 1.35, 0.14], [0.08, 1.35, 0.14 - 0.2], [0.08, 1.35, 0.14 - ROUND_CHEST.wallDepth + 0.001]]);
  roundChestMasks(root, sidecar);
  const w = weightsOf(geometry, 'CHEST_LEFT');
  assert.equal(w.getX(0), 1, 'apex');
  assert.equal(w.getX(2), 0, 'sternum seam slivers must not be sheared');
  assert.equal(w.getX(3), 0, 'back of the torso');
  assert.ok(w.getX(4) > 0.99, 'just inside the wall depth still counts');
});

test('where both breasts reach, the weight is shared so no vertex is driven at more than full strength', () => {
  const { root, geometry, sidecar } = scene([[0, 1.35, 0.14], [0.01, 1.3, 0.14]]);
  roundChestMasks(root, sidecar, { plateau: 0.1, reach: 0.2, midline: -1, midlineFade: 0.05 });
  const l = weightsOf(geometry, 'CHEST_LEFT'), r = weightsOf(geometry, 'CHEST_RIGHT');
  for (let i = 0; i < l.count; i++) assert.ok(l.getX(i) + r.getX(i) <= 1 + 1e-6, `vertex ${i}`);
  assert.ok(Math.abs(l.getX(2) - 0.5) < 1e-6 && Math.abs(r.getX(2) - 0.5) < 1e-6, 'equidistant vertex splits evenly');
});

test('the sidecar is patched to the round masks while authored data stays untouched', () => {
  const { root, geometry, sidecar, left } = scene([[0.1, 1.4, 0.13]]);
  const before = JSON.stringify(sidecar), authored = Float32Array.from(geometry.getAttribute('_SOFT_CHEST_LEFT').array);
  const result = roundChestMasks(root, sidecar);
  assert.equal(JSON.stringify(sidecar), before, 'input sidecar is not mutated');
  assert.deepEqual(result.sidecar.meshes[0].regions.map((r) => r.attribute), ['_SOFT_CHEST_LEFT_ROUND', '_SOFT_CHEST_RIGHT_ROUND']);
  assert.deepEqual(Array.from(geometry.getAttribute('_SOFT_CHEST_LEFT').array), Array.from(authored), 'authored mask attribute is unchanged');
  assert.deepEqual(Array.from(result.original.Body['chest-left']), Array.from(left), 'authored masks are returned for other layers');
  assert.deepEqual(result.apex['chest-left'].toArray().map((v) => +v.toFixed(3)), APEX[1], 'apex is the front-most painted vertex');
  for (const id of ['CHEST_LEFT', 'CHEST_RIGHT']) {
    const w = weightsOf(geometry, id);
    for (let i = 0; i < w.count; i++) assert.ok(Number.isFinite(w.getX(i)) && w.getX(i) >= 0 && w.getX(i) <= 1);
  }
  assert.throws(() => roundChestMasks(root, sidecar, { plateau: 0.1, reach: 0.05 }), /reach must exceed plateau/);
});
