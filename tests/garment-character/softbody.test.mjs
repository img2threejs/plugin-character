// SPDX-License-Identifier: Apache-2.0
// Small geometric fixtures exercise the solver, never character likeness.
import test from 'node:test';
import assert from 'node:assert/strict';
import { Bone, BoxGeometry, BufferAttribute, BufferGeometry, Group, Mesh, MeshBasicMaterial, Raycaster, Skeleton, SkinnedMesh, SphereGeometry, Vector3 } from 'three';
import { createSoftRig, PROFILES, REGION_IDS } from '../../runtime/garment-character/softbody.mjs';
import { createPicker } from '../../runtime/garment-character/picking.mjs';

function fixture({ garment = false, skinned = false, narrow = false, attach = true } = {}) {
  const root = new Group(), material = new MeshBasicMaterial();
  const sphere = new SphereGeometry(0.08, 12, 8);
  const positions = [], normals = [], uv = [], indices = [], masks = REGION_IDS.map(() => []);
  const ranges = [];
  for (let region = 0; region < 9; region++) {
    const start = positions.length / 3, p = sphere.attributes.position, n = sphere.attributes.normal;
    for (let i = 0; i < p.count; i++) {
      const scale = narrow && region === 0 ? 0.03 : 1;
      positions.push(Math.round(p.getX(i) * scale * 1e7) / 1e7 + region * 0.3, Math.round(p.getY(i) * scale * 1e7) / 1e7, Math.round(p.getZ(i) * scale * 1e7) / 1e7);
      normals.push(Math.round(n.getX(i) * 1e7) / 1e7, Math.round(n.getY(i) * 1e7) / 1e7, Math.round(n.getZ(i) * 1e7) / 1e7);
      uv.push(sphere.attributes.uv.getX(i), sphere.attributes.uv.getY(i));
      for (let j = 0; j < 9; j++) masks[j].push(region === j ? (narrow && region === 0 && p.getX(i) < 0 ? 0 : 1) : 0);
    }
    for (const index of sphere.index.array) indices.push(index + start);
    ranges.push([start, positions.length / 3]);
  }
  const protectedStart = positions.length / 3;
  positions.push(-1, 0, 0, -0.9, 0, 0, -1, 0.1, 0);
  normals.push(0, 0, 1, 0, 0, 1, 0, 0, 1); uv.push(0, 0, 1, 0, 0, 1);
  indices.push(protectedStart, protectedStart + 1, protectedStart + 2);
  for (const mask of masks) mask.push(0, 0, 0);
  sphere.dispose();
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute('normal', new BufferAttribute(new Float32Array(normals), 3));
  geometry.setAttribute('uv', new BufferAttribute(new Float32Array(uv), 2));
  geometry.setIndex(indices);
  for (let i = 0; i < 9; i++) geometry.setAttribute(`_soft_${REGION_IDS[i].replaceAll('-', '_')}`, new BufferAttribute(new Float32Array(masks[i]), 1));
  const morph = new Float32Array(positions.length);
  for (let i = 0; i < morph.length; i += 3) morph[i] = 0.002;
  geometry.morphAttributes.position = [new BufferAttribute(morph, 3)]; geometry.morphTargetsRelative = true;
  const body = skinned ? new SkinnedMesh(geometry, material) : new Mesh(geometry, material);
  body.name = 'Body'; root.add(body); body.morphTargetInfluences[0] = 0.35;
  let bone;
  if (skinned) {
    geometry.setAttribute('skinIndex', new BufferAttribute(new Uint16Array(positions.length / 3 * 4), 4));
    const weights = new Float32Array(positions.length / 3 * 4);
    for (let i = 0; i < weights.length; i += 4) weights[i] = 1;
    geometry.setAttribute('skinWeight', new BufferAttribute(weights, 4));
    bone = new Bone(); bone.name = 'ActualAnchor'; body.add(bone);
    body.bind(new Skeleton([bone]));
  }
  const specs = (name) => ({ name, regions: REGION_IDS.map((id) => ({ id, attribute: `_SOFT_${id.replaceAll('-', '_').toUpperCase()}`, ...(skinned ? { bone: bone.name } : {}) })) });
  const sidecar = { version: 1, meshes: [specs('Body')] };
  let cloth;
  if (garment) {
    assert.equal(skinned, false, 'this garment fixture intentionally tests unskinned coupling');
    cloth = new Mesh(geometry.clone(), material); cloth.name = 'Cloth'; cloth.morphTargetInfluences[0] = 0.35; root.add(cloth); sidecar.meshes.push(specs('Cloth'));
  }
  const rig = attach ? createSoftRig(root, sidecar) : null;
  return { root, body, cloth, bone, geometry, sidecar, rig, ranges, protectedStart, material };
}
function advance(rig, seconds) { for (let i = 0; i < Math.ceil(seconds * 120); i++) rig.update(1 / 120); }
function hit(f, region = 0) {
  f.root.updateWorldMatrix(true, false);
  f.root.updateMatrixWorld(true);
  if (f.body.isSkinnedMesh) { f.body.skeleton.update(); f.body.computeBoundingSphere(); }
  const center = new Vector3(), point = new Vector3(), [start, end] = f.ranges[region];
  for (let i = start; i < end; i++) center.add(f.body.getVertexPosition(i, point));
  center.divideScalar(end - start).applyMatrix4(f.body.matrixWorld);
  const direction = new Vector3(0, 0, 1).transformDirection(f.body.matrixWorld);
  const ray = new Raycaster(center.clone().addScaledVector(direction, 1), direction.clone().negate());
  const result = ray.intersectObject(f.body, false)[0];
  assert.ok(result, `actual ray hits region ${region}`);
  return result;
}
function meanDisplacement(entry, id) {
  const result = new Vector3(), mask = entry.masks.get(id); let count = 0;
  for (let i = 0; i < mask.length; i++) if (mask[i] === 1) { const k = i * 3; result.x += entry.positions[k] - entry.rest[k]; result.y += entry.positions[k + 1] - entry.rest[k + 1]; result.z += entry.positions[k + 2] - entry.rest[k + 2]; count++; }
  return result.divideScalar(count);
}
function assertTopology(entry) {
  const a = new Vector3(), b = new Vector3(), c = new Vector3(), pa = new Vector3(), pb = new Vector3(), pc = new Vector3();
  const n = new Vector3(), pn = new Vector3();
  for (let i = 0; i < entry.indices.length; i += 3) {
    const [ia, ib, ic] = entry.indices.subarray(i, i + 3);
    a.fromArray(entry.rest, ia * 3); b.fromArray(entry.rest, ib * 3); c.fromArray(entry.rest, ic * 3);
    pa.fromArray(entry.positions, ia * 3); pb.fromArray(entry.positions, ib * 3); pc.fromArray(entry.positions, ic * 3);
    n.crossVectors(b.clone().sub(a), c.clone().sub(a)); pn.crossVectors(pb.clone().sub(pa), pc.clone().sub(pa));
    assert.ok(n.dot(pn) / n.lengthSq() >= 0.199, 'positive projected area remains above guard');
    for (const [u, v, pu, pv] of [[a, b, pa, pb], [a, c, pa, pc], [b, c, pb, pc]]) {
      const ratio = pu.distanceTo(pv) / u.distanceTo(v);
      assert.ok(ratio >= 0.649 && ratio <= 1.451, `edge ratio ${ratio} within guard`);
    }
  }
}

test('squeeze produces broad actual axial compression and reciprocal lateral bulge', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body');
  const token = f.rig.grab(hit(f), 1, { mode: 'squeeze' }); assert.ok(token);
  advance(f.rig, 1.5);
  const r = f.rig.regions.get('chest-left'), v = new Vector3(), d = new Vector3();
  let axialBefore = 0, axialAfter = 0, lateralBefore = 0, lateralAfter = 0, expanded = 0, members = 0;
  for (let i = 0; i < entry.masks.get(r.id).length; i++) if (entry.masks.get(r.id)[i]) {
    v.fromArray(entry.rest, i * 3).sub(r.center); d.fromArray(entry.positions, i * 3).sub(r.center);
    const av = v.dot(r.axis), ad = d.dot(r.axis), lv = v.lengthSq() - av * av, ld = d.lengthSq() - ad * ad;
    axialBefore += av * av; axialAfter += ad * ad; lateralBefore += lv; lateralAfter += ld;
    if (ld > lv + 1e-10) expanded++; members++;
  }
  assert.ok(axialAfter < axialBefore * 0.8, 'whole lobe is axially compressed');
  assert.ok(lateralAfter > lateralBefore * 1.1, 'actual vertices bulge tangentially');
  assert.ok(expanded > members * 0.8, 'bulge is broad, not a point crater');
  const determinant = Math.sqrt(axialAfter / axialBefore) * (lateralAfter / lateralBefore);
  assert.ok(Math.abs(determinant - 1) < 0.015, `full-support modal determinant ${determinant}`);
  assertTopology(entry); f.rig.dispose();
});

test('off-surface captured-plane drag releases through neutral and settles exactly', () => {
  const f = fixture(), h = hit(f), entry = f.rig.meshes.get('Body');
  const token = f.rig.grab(h, 3, { mode: 'grab' });
  assert.ok(f.rig.drag(token, h.point.clone().add(new Vector3(0.2, 0, 0))));
  advance(f.rig, 1);
  assert.ok(meanDisplacement(entry, 'chest-left').x > PROFILES.chest.cap * .5);
  f.rig.release(token);
  let negative = 0, peak = 0;
  for (let i = 0; i < 300; i++) { f.rig.update(1 / 120); const x = meanDisplacement(entry, 'chest-left').x; negative = Math.min(negative, x); peak = Math.max(peak, Math.abs(x)); }
  assert.ok(negative < -PROFILES.chest.cap * .07, `signed rebound ${negative}`);
  assert.ok(peak <= PROFILES.chest.cap + 1e-6);
  advance(f.rig, 12);
  assert.deepEqual(entry.positions, entry.rest, 'settled positions are bit-exact rest');
  assert.deepEqual(entry.geometry.attributes.normal.array, entry.restNormals, 'settled shading restores authored normals exactly');
  advance(f.rig, 0.1);
  assert.deepEqual(entry.geometry.attributes.normal.array, entry.restNormals, 'idle shading stays at authored rest');
  f.rig.dispose();
});

test('squeeze release expands axially past neutral before damping out', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body'), h = hit(f);
  const token = f.rig.grab(h, 8, { mode: 'squeeze' }); advance(f.rig, 1);
  const r = f.rig.regions.get('chest-left'), axis = r.axis.clone(), center = r.center.clone();
  let chosen = 0, distance = 0;
  for (let i = 0; i < entry.masks.get(r.id).length; i++) if (entry.masks.get(r.id)[i]) {
    const d = new Vector3().fromArray(entry.rest, i * 3).sub(center).dot(axis);
    if (d > distance) { distance = d; chosen = i; }
  }
  const current = () => new Vector3().fromArray(entry.positions, chosen * 3).sub(center).dot(axis);
  assert.ok(current() < distance); f.rig.release(token);
  let greatest = distance;
  for (let i = 0; i < 240; i++) { f.rig.update(1 / 120); greatest = Math.max(greatest, current()); }
  assert.ok(greatest > distance * 1.02, 'surface itself crosses its neutral axial position'); f.rig.dispose();
});

test('all nine region surfaces visibly rebound after an impulse', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body');
  assert.equal(f.rig.regions.size, 9);
  const zeros = new Map();
  for (const id of REGION_IDS) f.rig.impulse(id, new Vector3(0.03, 0, 0));
  for (let frame = 1; frame <= 120; frame++) {
    f.rig.update(1 / 120);
    for (const id of REGION_IDS) if (!zeros.has(id) && meanDisplacement(entry, id).x < -1e-6) zeros.set(id, frame);
  }
  assert.equal(zeros.size, 9, 'each actual region surface rebounds');
  f.rig.dispose();
});

test('stationary abdomen presses move the broad surface inward and rebound outward', () => {
  for (const id of ['abdomen']) {
    const f = fixture(), entry = f.rig.meshes.get('Body');
    const h = hit(f, REGION_IDS.indexOf(id)), token = f.rig.grab(h, 1);
    advance(f.rig, .7);
    const axis = f.rig.regions.get(id).axis.clone();
    const minimum = .003;
    assert.ok(meanDisplacement(entry, id).dot(axis) < -minimum, `${id}: coherent inward motion, not only squash`);
    assertTopology(entry);
    f.rig.release(token);
    let outward = 0;
    for (let frame = 0; frame < 360; frame++) {
      f.rig.update(1 / 120);
      outward = Math.max(outward, meanDisplacement(entry, id).dot(axis));
    }
    assert.ok(outward > minimum * .1, `${id}: actual surface overshoots neutral`);
    advance(f.rig, 3);
    assert.deepEqual(entry.positions, entry.rest, `${id}: exact rest recovery`);
    f.rig.dispose();
  }
});

test('cheek lighting remains continuous when visible surface travel tends to zero', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body');
  f.rig.impulse('cheek-left', new Vector3(0, 0, 1e-5)); f.rig.update(1 / 120);
  const mask = entry.masks.get('cheek-left'), normals = entry.geometry.attributes.normal.array;
  let greatest = 0;
  for (let i = 0; i < mask.length; i++) if (mask[i]) {
    const k = i * 3;
    greatest = Math.max(greatest, Math.hypot(normals[k] - entry.restNormals[k], normals[k + 1] - entry.restNormals[k + 1], normals[k + 2] - entry.restNormals[k + 2]));
  }
  assert.ok(greatest < .001, 'infinitesimal travel must not replace authored smooth normals with faceted rest normals');
  f.rig.dispose();
});

test('cheek press and directional drags stay gently taut instead of squeezing or denting', () => {
  for (const id of ['cheek-left', 'cheek-right']) {
    const f = fixture(), entry = f.rig.meshes.get('Body'), h = hit(f, REGION_IDS.indexOf(id));
    for (const mode of ['squeeze', 'grab']) {
      f.rig.reset();
      const token = f.rig.grab(h, 1, { mode }); advance(f.rig, .6);
      if (mode === 'squeeze') assert.ok(meanDisplacement(entry, id).dot(f.rig.regions.get(id).axis) > .0003, 'press gently lifts/stretches, never dents inward');
      for (const direction of [new Vector3(1, 0, 0), new Vector3(-1, 0, 0), new Vector3(0, 1, 0), new Vector3(0, -1, 0)]) {
        f.rig.drag(token, h.point.clone().addScaledVector(direction, .02)); advance(f.rig, .5);
        const mean = meanDisplacement(entry, id), mask = entry.masks.get(id);
        assert.ok(mean.length() > .0008 && mean.length() <= PROFILES.cheek.cap + 1e-5, 'captured stretch is visible but stays within the taut cheek cap');
        for (let i = 0; i < mask.length; i++) if (mask[i]) {
          const delta = new Vector3().fromArray(entry.positions, i * 3).sub(new Vector3().fromArray(entry.rest, i * 3));
          assert.ok(delta.distanceTo(mean) < 1e-6, 'uniform supported patch has no squash or ring-shaped dent');
        }
        assertTopology(entry);
      }
      f.rig.release(token); advance(f.rig, 6); assert.deepEqual(entry.positions, entry.rest);
    }
    f.rig.dispose();
  }
});

test('held strap tension pulls the chest region, and clearing it rebounds past rest then settles exactly', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body'), r = f.rig.regions.get('chest-left');
  f.rig.setTension('chest-left', new Vector3(1, 0, 0));
  advance(f.rig, 1.5);
  assert.ok(Math.abs(r.displacement.x - r.profile.cap) < r.profile.cap * 0.05, 'tension is bounded by the region cap and held');
  assert.ok(meanDisplacement(entry, 'chest-left').x > r.profile.cap * 0.5, 'actual surface follows the strap');
  f.rig.setTension('chest-left', null);
  let rebound = 0;
  for (let i = 0; i < 240; i++) { f.rig.update(1 / 120); rebound = Math.min(rebound, r.displacement.x); }
  assert.ok(rebound < -r.profile.cap * 0.4, 'release springs back through rest');
  advance(f.rig, 12);
  assert.deepEqual(entry.positions, entry.rest);
  f.rig.setTension('chest-left', new Vector3(1, 0, 0)); f.rig.reset();
  assert.equal(r.tension.lengthSq(), 0, 'reset clears held tension');
  f.rig.dispose();
});

test('released chest and hip tissue keeps several visible rebounds', () => {
  for (const id of ['chest-left', 'chest-right', 'hips-left', 'hips-right']) {
    const f = fixture(), r = f.rig.regions.get(id);
    f.rig.impulse(id, new Vector3(r.profile.cap * 2 * Math.PI * r.profile.frequency * .5, 0, 0));
    let first = 0, swings = 0, sign = 0;
    for (let frame = 0; frame < 240; frame++) {
      f.rig.update(1 / 120);
      const x = r.displacement.x;
      first = Math.max(first, Math.abs(x));
      if (Math.abs(x) > first * .25 && Math.sign(x) !== sign) { swings++; sign = Math.sign(x); }
    }
    assert.ok(swings >= 4, `${id}: at least four swings above a quarter of the first peak within two seconds`);
    f.rig.dispose();
  }
});

test('thin abdominal triangles allow visible tangential travel without folding', () => {
  const root = new Group(), geometry = new BufferGeometry(), positions = [], masks = REGION_IDS.map(() => []);
  for (let region = 0; region < 9; region++) {
    const vertices = region === 6
      ? [[.00531705, 1.27823925, .09585121], [.00432754, 1.29493845, .09706767], [.00336244, 1.30652833, .09791733]]
      : [[region * .3, 0, 0], [region * .3 + .1, 0, 0], [region * .3, .1, 0]];
    vertices.forEach((p, j) => {
      positions.push(...p);
      masks.forEach((mask, r) => mask.push(r !== region ? 0 : region === 6 ? [.41822165, .14364034, .02475265][j] : 1));
    });
  }
  geometry.setAttribute('position', new BufferAttribute(new Float32Array(positions), 3));
  geometry.setIndex(Array.from({ length: positions.length / 3 }, (_, i) => i)); geometry.computeVertexNormals();
  REGION_IDS.forEach((id, i) => geometry.setAttribute(`_soft_${id.replaceAll('-', '_')}`, new BufferAttribute(new Float32Array(masks[i]), 1)));
  const body = new Mesh(geometry, new MeshBasicMaterial()); body.name = 'Body'; root.add(body);
  const rig = createSoftRig(root, { meshes: [{ name: 'Body', regions: REGION_IDS.map(id => ({ id, attribute: `_soft_${id.replaceAll('-', '_')}` })) }] });
  const center = new Vector3(.00433568, 1.29323534, .09694540);
  const h = new Raycaster(center.clone().add(new Vector3(0, 0, 1)), new Vector3(0, 0, -1)).intersectObject(body, false)[0];
  const token = rig.grab(h, 1, { mode: 'grab' }); assert.ok(token);
  rig.drag(token, h.point.clone().add(new Vector3(.012, .007, 0))); advance(rig, .7);
  const entry = rig.meshes.get('Body'); let greatest = 0;
  for (let i = 18; i < 21; i++) greatest = Math.max(greatest, new Vector3().fromArray(entry.positions, i * 3).distanceTo(new Vector3().fromArray(entry.rest, i * 3)));
  assert.ok(greatest > .0015, 'thin boundary geometry does not suppress the whole surface to a wrinkle');
  assertTopology(entry); rig.release(token); advance(rig, 6);
  assert.deepEqual(entry.positions, entry.rest); rig.dispose();
});

test('body and garment use one state and one common topology attenuation', () => {
  const f = fixture({ garment: true, narrow: true });
  f.rig.impulse('chest-left', new Vector3(2, 0, 0));
  for (let i = 0; i < 12; i++) f.rig.update(1 / 120);
  const body = f.rig.meshes.get('Body'), cloth = f.rig.meshes.get('Cloth');
  assert.deepEqual(body.positions, cloth.positions, 'identical shared support never jiggles independently');
  assert.equal(f.rig.regions.get('chest-left').meshes.length, 2);
  const d = f.rig.getDiagnostics();
  assert.ok(d.guards.hits > 0 && d.guards.minimumScale < 1, 'narrow support genuinely exercises guard');
  assert.equal(d.regions['chest-left'].topologyScale, d.guards.topologyScale);
  assertTopology(body); assertTopology(cloth); f.rig.dispose();
});

test('protected vertices, UV, skin, morph, index and material are preserved; reset cancels contacts', () => {
  const f = fixture({ skinned: true }), original = f.geometry, originalUV = original.attributes.uv.array.slice();
  const entry = f.rig.meshes.get('Body'), h = hit(f), token = f.rig.grab(h, 4, { mode: 'squeeze' });
  f.rig.drag(token, h.point.clone().add(new Vector3(0.02, 0.01, 0))); advance(f.rig, 0.4);
  assert.deepEqual(entry.positions.subarray(f.protectedStart * 3), entry.rest.subarray(f.protectedStart * 3));
  for (const name of ['uv', 'skinIndex', 'skinWeight']) assert.equal(entry.geometry.attributes[name], original.attributes[name]);
  assert.deepEqual(original.attributes.uv.array, originalUV);
  assert.equal(entry.geometry.morphAttributes, original.morphAttributes); assert.equal(entry.geometry.index, original.index);
  assert.equal(f.body.material, f.material); assert.equal(f.body.morphTargetInfluences[0], 0.35);
  f.rig.reset(); assert.deepEqual(entry.positions, entry.rest); assert.equal(f.rig.getDiagnostics().contactCount, 0);
  assert.equal(f.rig.drag(token, h.point), false); assert.equal(f.rig.release(token), false);
  assert.equal(f.body.morphTargetInfluences[0], 0.35);
  let materialDisposals = 0, geometryDisposals = 0;
  f.material.addEventListener('dispose', () => materialDisposals++); original.addEventListener('dispose', () => geometryDisposals++);
  f.rig.dispose(); f.rig.dispose();
  assert.equal(f.body.geometry, original); assert.equal(materialDisposals, 0); assert.equal(geometryDisposals, 0);
});

test('real ray picking follows rotated GLTF frame, skinned pose and live morphs', () => {
  const f = fixture({ skinned: true }); f.root.rotation.x = -Math.PI / 2; f.bone.rotation.y = 0.6; f.bone.position.y = 0.12;
  const h = hit(f, 3); assert.equal(f.rig.pick(h), 'hips-right');
  const token = f.rig.grab(h, 11, { mode: 'grab' }); assert.ok(token);
  advance(f.rig, 1);
  const held = meanDisplacement(f.rig.meshes.get('Body'), 'hips-right');
  const axis = new Vector3(1, 0, 0).applyQuaternion(f.bone.quaternion).applyQuaternion(f.root.quaternion);
  f.rig.drag(token, h.point.clone().addScaledVector(axis, 0.015)); advance(f.rig, 1);
  const delta = meanDisplacement(f.rig.meshes.get('Body'), 'hips-right').sub(held);
  assert.ok(delta.x > 0.01, 'world drag is inverted through actual pose to rest-local x');
  assert.ok(Math.abs(delta.y) < 1e-5 && Math.abs(delta.z) < 1e-5, 'no coordinate-conversion cross-axis leakage'); f.rig.dispose();
});

test('accelerated selection matches exact posed rays and respects nearer protected occluders', () => {
  const f = fixture({ skinned: true }), picker = createPicker([f.body], f.rig.meshes);
  f.root.rotation.y = .35; f.root.scale.set(1.2, .9, 1.1);
  for (const pose of [0, .7, -.4]) {
    f.bone.rotation.y = pose; f.bone.position.y = pose * .2;
    f.body.morphTargetInfluences[0] = pose;
    f.rig.impulse('abdomen', new Vector3(.03, .01, .01)); advance(f.rig, .04);
    f.root.updateMatrixWorld(true); f.body.skeleton.update(); f.body.computeBoundingSphere();
    for (let region = 0; region < 9; region++) {
      const expected = hit(f, region), direction = new Vector3(0, 0, -1).transformDirection(f.body.matrixWorld);
      const ray = new Raycaster(expected.point.clone().addScaledVector(direction, -1), direction);
      const standard = ray.intersectObject(f.body, false)[0], actual = picker.cast(ray);
      assert.ok(actual); assert.equal(actual.object, standard.object);
      assert.ok(actual.point.distanceTo(standard.point) < 1e-8);
      assert.equal(f.rig.pick(actual), f.rig.pick(standard));
    }
  }
  f.root.rotation.set(0, 0, 0); f.root.scale.setScalar(1); f.bone.rotation.set(0, 0, 0); f.bone.position.set(0, 0, 0); f.rig.reset(); f.root.updateMatrixWorld(true);
  const blocker = new Mesh(new BoxGeometry(.3, .3, .03), f.material); blocker.position.z = .3; blocker.updateMatrixWorld();
  const blocked = createPicker([f.body, blocker], f.rig.meshes).cast(new Raycaster(new Vector3(0, 0, 1), new Vector3(0, 0, -1)));
  assert.equal(blocked.object, blocker, 'protected hair/clothing must block tissue behind it');
  assert.equal(f.rig.pick(blocked), null);
  blocker.geometry.dispose(); f.rig.dispose();
});

test('actual anchor acceleration drives inertia, warm starts and reset suppress stale motion', () => {
  const f = fixture({ skinned: true }), entry = f.rig.meshes.get('Body');
  advance(f.rig, 0.1); assert.deepEqual(entry.positions, entry.rest, 'stationary anchor does not synthesize sine jiggle');
  f.bone.position.x = 0.01; f.rig.update(1 / 120);
  assert.ok(meanDisplacement(entry, 'chest-left').x < -1e-5, 'surface lags accelerating actual anchor');
  f.rig.reset(); f.bone.position.x = 0.5;
  f.rig.update(1 / 120); f.rig.update(1 / 120);
  assert.deepEqual(entry.positions, entry.rest, 'pose jump after reset warm-starts instead of kicking');
  f.rig.dispose();
});

test('idle tissue remains pickable when bones and morphs move beyond cached bounds', () => {
  const f = fixture({ skinned: true, attach: false });
  const morph = f.geometry.morphAttributes.position[0];
  for (let i = 0; i < morph.count; i++) morph.setXYZ(i, 0, 4, 0);
  f.body.morphTargetInfluences[0] = 0;
  f.rig = createSoftRig(f.root, f.sidecar);
  const entry = f.rig.meshes.get('Body');
  const rayAt = (y) => new Raycaster(new Vector3(0, y, 1), new Vector3(0, 0, -1)).intersectObject(f.body, false)[0];
  f.rig.update(1 / 60);
  assert.ok(rayAt(0));
  f.body.computeBoundingBox();
  // A warm-start pose jump leaves tissue at rest, but must invalidate posed bounds.
  f.bone.position.y = 4;
  f.rig.update(1 / 60);
  assert.deepEqual(entry.positions, entry.rest);
  assert.ok(rayAt(4), 'ray hits bone-moved surface outside the previous sphere and box');
  f.rig.reset();
  f.body.computeBoundingSphere();
  f.body.computeBoundingBox();
  f.body.morphTargetInfluences[0] = 1;
  f.rig.update(1 / 60);
  assert.deepEqual(entry.positions, entry.rest);
  assert.ok(rayAt(8), 'ray hits morph-moved surface while tissue stays idle');
  assert.equal(f.body.frustumCulled, false, 'animated surface cannot disappear behind stale rest bounds');
  f.rig.dispose();
});

test('reset keeps conservative visibility and disposal restores caller bounds and culling', () => {
  for (const culled of [true, false]) {
    const f = fixture({ skinned: true, attach: false });
    f.body.frustumCulled = culled;
    f.body.computeBoundingBox(); f.body.computeBoundingSphere();
    const box = f.body.boundingBox, sphere = f.body.boundingSphere;
    const savedBox = box.clone(), savedSphere = sphere.clone();
    f.rig = createSoftRig(f.root, f.sidecar);
    f.rig.impulse('chest-left', new Vector3(0.05, 0, 0));
    f.rig.update(1 / 60);
    f.rig.reset();
    const entry = f.rig.meshes.get('Body');
    assert.deepEqual(entry.positions, entry.rest);
    assert.deepEqual(entry.geometry.attributes.normal.array, entry.restNormals);
    assert.equal(f.body.frustumCulled, false);
    f.rig.dispose();
    assert.equal(f.body.geometry, f.geometry);
    assert.equal(f.body.frustumCulled, culled);
    assert.equal(f.body.boundingBox, box); assert.equal(f.body.boundingSphere, sphere);
    assert.deepEqual(box, savedBox); assert.deepEqual(sphere, savedSphere);
  }
});

test('long dt is bounded, contacts cancel safely and invalid dt cannot poison state', () => {
  const f = fixture(), h = hit(f), entry = f.rig.meshes.get('Body');
  const token = f.rig.grab(h, 1, { mode: 'squeeze' });
  f.rig.drag(token, h.point.clone().add(new Vector3(1e6, -1e6, 1e6)));
  f.rig.update(1e6); f.rig.update(NaN); f.rig.update(Infinity); f.rig.update(-1);
  assert.ok(entry.positions.every(Number.isFinite)); assertTopology(entry);
  const d = f.rig.getDiagnostics(); assert.ok(d.solver.lastSubsteps <= 12); assert.ok(d.solver.droppedTime > 999999);
  assert.ok(new Vector3(...d.regions['chest-left'].displacement).length() <= 0.030001);
  f.rig.releaseAll(); assert.equal(f.rig.getDiagnostics().contactCount, 0);
  f.rig.update(1 / 120); f.rig.reset(); assert.deepEqual(entry.positions, entry.rest); f.rig.dispose();
});

test('missing, non-scalar, nonfinite and out-of-range masks fail without mutating source geometry', () => {
  for (const variant of ['missing', 'scalar', 'nan', 'negative', 'above']) {
    const f = fixture({ attach: false }), name = '_soft_chest_left';
    if (variant === 'missing') f.geometry.deleteAttribute(name);
    else if (variant === 'scalar') f.geometry.setAttribute(name, new BufferAttribute(new Float32Array(f.geometry.attributes.position.count * 2), 2));
    else f.geometry.attributes[name].setX(0, variant === 'nan' ? NaN : variant === 'negative' ? -0.01 : 1.01);
    assert.throws(() => createSoftRig(f.root, f.sidecar), /mask/);
    assert.equal(f.body.geometry, f.geometry);
  }
  const f = fixture({ attach: false }); f.sidecar.meshes[0].regions.pop();
  assert.throws(() => createSoftRig(f.root, f.sidecar), /missing required region/); assert.equal(f.body.geometry, f.geometry);
});

test('coincident smooth UV seams retain normal continuity without changing protected normals', () => {
  const f = fixture(), entry = f.rig.meshes.get('Body'), originalUV = entry.geometry.attributes.uv.array.slice();
  const token = f.rig.grab(hit(f), 9, { mode: 'squeeze' }); advance(f.rig, 0.5);
  const seen = new Map(); let seams = 0;
  for (let i = f.ranges[0][0]; i < f.ranges[0][1]; i++) {
    const k = i * 3, key = `${entry.rest[k]},${entry.rest[k + 1]},${entry.rest[k + 2]}|${entry.restNormals[k]},${entry.restNormals[k + 1]},${entry.restNormals[k + 2]}`;
    if (seen.has(key)) {
      const other = seen.get(key);
      assert.deepEqual(entry.positions.slice(k, k + 3), entry.positions.slice(other * 3, other * 3 + 3));
      assert.deepEqual(entry.geometry.attributes.normal.array.slice(k, k + 3), entry.geometry.attributes.normal.array.slice(other * 3, other * 3 + 3)); seams++;
    } else seen.set(key, i);
  }
  assert.ok(seams > 5, 'fixture contains real split-UV duplicate vertices');
  assert.deepEqual(entry.geometry.attributes.uv.array, originalUV); f.rig.release(token); f.rig.dispose();
  // Protected hard triangle retains its authored normal exactly, not a seam average.
  assert.deepEqual(f.geometry.attributes.normal.array.slice(f.protectedStart * 3), new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]));
});

test('hard face boundaries are not welded into smooth UV seams', () => {
  const f = fixture({ attach: false }), geometry = new BoxGeometry(0.1, 0.1, 0.1);
  const mask = new Float32Array(geometry.attributes.position.count).fill(1);
  geometry.setAttribute('_soft_chest_left', new BufferAttribute(mask, 1));
  const mesh = new Mesh(geometry, f.material); mesh.name = 'HardCloth'; f.root.add(mesh);
  f.sidecar.meshes.push({ name: mesh.name, regions: [{ id: 'chest-left', attribute: '_SOFT_CHEST_LEFT' }] });
  f.rig = createSoftRig(f.root, f.sidecar);
  f.rig.grab(hit(f), 17, { mode: 'squeeze' }); advance(f.rig, 0.5);
  const entry = f.rig.meshes.get(mesh.name), seen = new Map();
  let hardPairs = 0;
  for (let i = 0; i < mask.length; i++) {
    const k = i * 3, key = `${entry.rest[k]},${entry.rest[k + 1]},${entry.rest[k + 2]}`;
    const prior = seen.get(key);
    if (prior !== undefined) {
      const first = new Vector3().fromArray(entry.geometry.attributes.normal.array, prior * 3);
      const second = new Vector3().fromArray(entry.geometry.attributes.normal.array, k);
      assert.ok(Math.abs(first.dot(second)) < 0.5, 'perpendicular authored faces remain distinct');
      assert.deepEqual(entry.positions.slice(k, k + 3), entry.positions.slice(prior * 3, prior * 3 + 3));
      hardPairs++;
    } else seen.set(key, i);
  }
  assert.ok(hardPairs >= 8); f.rig.dispose();
});

test('a triangle with only one painted corner remains guarded and updates its supported normal', () => {
  const f = fixture({ attach: false }), geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([
    0, 0, 0, 0.001, 0, 0, 0, 0.001, 0,
    1, 0, 0, 1.001, 0, 0, 1, 0.001, 0,
  ]), 3));
  geometry.computeVertexNormals();
  geometry.setAttribute('_soft_chest_left', new BufferAttribute(new Float32Array([1, 0, 0, 0, 0, 0]), 1));
  const mesh = new Mesh(geometry, f.material); mesh.name = 'BoundaryCloth'; f.root.add(mesh);
  f.sidecar.meshes.push({ name: mesh.name, regions: [{ id: 'chest-left', attribute: '_SOFT_CHEST_LEFT' }] });
  f.rig = createSoftRig(f.root, f.sidecar);
  f.rig.impulse('chest-left', new Vector3(0, 0, 0.5));
  f.rig.update(1 / 60);
  const entry = f.rig.meshes.get(mesh.name), p = entry.positions;
  assert.ok(f.rig.getDiagnostics().guards.hits > 0, 'mixed-support boundary constrains the shared displacement');
  assertTopology(entry);
  const a = new Vector3().fromArray(p), b = new Vector3().fromArray(p, 3), c = new Vector3().fromArray(p, 6);
  const expected = b.sub(a).cross(c.sub(a)).normalize();
  const actual = new Vector3().fromArray(entry.geometry.attributes.normal.array);
  assert.ok(expected.distanceTo(actual) < 1e-6, 'painted corner includes the deformed boundary triangle normal');
  assert.ok(Math.abs(actual.x) > 0.01, 'boundary normal visibly changes');
  assert.deepEqual(p.subarray(3), entry.rest.subarray(3), 'unpainted corners and disconnected triangle stay fixed');
  assert.deepEqual(entry.geometry.attributes.normal.array.subarray(3), entry.restNormals.subarray(3), 'unpainted shading stays authored');
  f.rig.dispose();
});

test('captured contact pad dents locally while distant skin stays unchanged, then recovers', () => {
  const f = fixture(), h = hit(f), entry = f.rig.meshes.get('Body');
  const point = new Vector3(), before = new Vector3(), after = new Vector3();
  let nearest = h.face.a, nearestDistance = Infinity, distant = -1;
  for (let i = f.ranges[0][0]; i < f.ranges[0][1]; i++) {
    f.body.getVertexPosition(i, point);
    const distance = point.distanceTo(h.point);
    if (distance < nearestDistance) { nearest = i; nearestDistance = distance; }
    if (distance > .10) distant = i;
  }
  f.body.getVertexPosition(nearest, before);
  const token = f.rig.grab(h, 71, { mode: 'grab' });
  advance(f.rig, .8);
  f.body.getVertexPosition(nearest, after);
  assert.ok(after.sub(before).dot(h.face.normal) < -.0005, 'actual captured skin indents under a held grab');
  assert.ok(distant >= 0);
  assert.deepEqual(entry.positions.slice(distant*3,distant*3+3), entry.rest.slice(distant*3,distant*3+3), 'distant material is outside the contact pad');
  assert.deepEqual(entry.positions.subarray(f.protectedStart*3),entry.rest.subarray(f.protectedStart*3));
  f.rig.release(token);
  let crossed = false;
  for (let i=0;i<240;i++) { f.rig.update(1/120); if (f.rig.getDiagnostics().contactPads.states.some(p=>p.depth<0)) crossed=true; }
  assert.ok(crossed,'released pad crosses neutral before damping out');
  advance(f.rig,6);
  assert.deepEqual(entry.positions,entry.rest);
  assert.deepEqual(entry.geometry.attributes.normal.array,entry.restNormals);
  assert.equal(f.rig.getDiagnostics().contactPads.count,0);
  f.rig.dispose();
});

test('rapid released presses have bounded live storage and reset cannot leave a stale contact', () => {
  const f=fixture(),entry=f.rig.meshes.get('Body');
  for(let i=0;i<16;i++){const token=f.rig.grab(hit(f),i,{mode:'squeeze'});assert.ok(token);f.rig.update(1/120);f.rig.release(token);}
  assert.equal(f.rig.grab(hit(f),99,{mode:'squeeze'}),null,'refuse rather than abruptly erase an unsettled pad');
  assert.equal(f.rig.getDiagnostics().contactCount,0);
  assertTopology(entry);
  f.rig.reset();
  assert.equal(f.rig.getDiagnostics().contactPads.count,0);
  assert.deepEqual(entry.positions,entry.rest);
  const token=f.rig.grab(hit(f),100,{mode:'squeeze'});
  assert.ok(token,'released storage is reusable');
  // Lively chest damping (zeta 0.11) needs ~10 s to reach the exact sleep threshold.
  advance(f.rig,.3); f.rig.releaseAll(); advance(f.rig,12);
  assert.deepEqual(entry.positions,entry.rest);
  f.rig.dispose();
});

test('a stationary captured hand holds material when the actual bone moves underneath', () => {
  const f=fixture({skinned:true}),entry=f.rig.meshes.get('Body');
  const token=f.rig.grab(hit(f),901,{mode:'grab'});
  advance(f.rig,.3);
  const shift=PROFILES.chest.cap*.75;f.bone.position.x=shift;
  advance(f.rig,1.5);
  const displacement=meanDisplacement(entry,'chest-left');
  assert.ok(displacement.x<-shift*.9 && displacement.x>-shift*1.1,'skin counters the moved bone without requiring another pointermove');
  assertTopology(entry);
  f.rig.release(token);advance(f.rig,12);
  assert.deepEqual(entry.positions,entry.rest);
  f.rig.dispose();
});
