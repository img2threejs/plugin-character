import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import { SoftBody, attachSoftBodies } from '../runtime/softbody.mjs';

const GRID = 21; // 21 x 21 vertices over [-1,1]^2 in the XY plane, spacing 0.1
const FPS = 60;
const X_AXIS = new THREE.Vector3(1, 0, 0);

/**
 * Skinned diagnostic sheet. Two bones: b0 at y=-1 and child b1 at the origin.
 * Skin weights blend linearly between y=-0.5 and y=0.5, so y >= 0.5 follows b1
 * fully. Region mask is a cone centred at (0, 0.6). Not a human; mechanics only.
 */
function makeFixture({ indexed = true, hair = false, interleave = false, morph = true } = {}) {
  const count = GRID * GRID;
  const position = new Float32Array(count * 3);
  const uv = new Float32Array(count * 2);
  const custom = new Float32Array(count * 2);
  const normal = new Float32Array(count * 3);
  const skinIndex = new Uint16Array(count * 4);
  const skinWeight = new Float32Array(count * 4);
  const mask = new Float32Array(count);
  const zero = new Float32Array(count);
  const one = new Float32Array(count).fill(1);
  const bad = new Float32Array(count).fill(0.5);
  const hairMask = new Float32Array(count);
  const hairOnly = new Float32Array(count);
  const morphOffsets = new Float32Array(count * 3);
  for (let iy = 0; iy < GRID; iy++) {
    for (let ix = 0; ix < GRID; ix++) {
      const i = iy * GRID + ix;
      const x = (ix - 10) / 10;
      const y = (iy - 10) / 10;
      position.set([x, y, 0], i * 3);
      normal.set([0, 0, 1], i * 3);
      uv.set([x * 0.5 + 0.5, y * 0.5 + 0.5], i * 2);
      custom.set([x, y * 2], i * 2);
      const w1 = Math.min(1, Math.max(0, y + 0.5));
      skinIndex.set([0, 1, 0, 0], i * 4);
      skinWeight.set([1 - w1, w1, 0, 0], i * 4);
      mask[i] = Math.max(0, 1 - Math.hypot(x, y - 0.6) / 0.5);
      if (hair && y > 0.75) {
        hairMask[i] = 1;
        if (Math.abs(x) < 0.3) hairOnly[i] = 0.5;
      }
      morphOffsets.set([0, 0, 0.2], i * 3);
    }
  }
  bad[5] = 1.5;
  const geometry = new THREE.BufferGeometry();
  if (interleave) {
    const data = new Float32Array(count * 5);
    for (let i = 0; i < count; i++) {
      data.set(position.subarray(i * 3, i * 3 + 3), i * 5);
      data.set(uv.subarray(i * 2, i * 2 + 2), i * 5 + 3);
    }
    const buffer = new THREE.InterleavedBuffer(data, 5);
    geometry.setAttribute('position', new THREE.InterleavedBufferAttribute(buffer, 3, 0));
    geometry.setAttribute('uv', new THREE.InterleavedBufferAttribute(buffer, 2, 3));
  } else {
    geometry.setAttribute('position', new THREE.BufferAttribute(position, 3));
    geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  }
  geometry.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
  geometry.setAttribute('_custom', new THREE.BufferAttribute(custom, 2));
  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(skinIndex, 4));
  geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(skinWeight, 4));
  // GLTFLoader lowercases custom attribute names.
  geometry.setAttribute('_soft_r', new THREE.BufferAttribute(mask, 1));
  geometry.setAttribute('_soft_zero', new THREE.BufferAttribute(zero, 1));
  geometry.setAttribute('_soft_one', new THREE.BufferAttribute(one, 1));
  geometry.setAttribute('_soft_bad', new THREE.BufferAttribute(bad, 1));
  if (hair) {
    geometry.setAttribute('_hair', new THREE.BufferAttribute(hairMask, 1));
    geometry.setAttribute('_soft_haironly', new THREE.BufferAttribute(hairOnly, 1));
  }
  const indices = [];
  for (let iy = 0; iy < GRID - 1; iy++) {
    for (let ix = 0; ix < GRID - 1; ix++) {
      const a = iy * GRID + ix;
      const b = a + 1;
      const c = a + GRID;
      const d = c + 1;
      indices.push(a, b, d, a, d, c);
    }
  }
  geometry.setIndex(indices);
  // Split at y = 0.5 so the cone mask (y in 0.1..1.0) touches both materials.
  geometry.addGroup(0, 1800, 0);
  geometry.addGroup(1800, 600, 1);
  if (morph) {
    geometry.morphAttributes.position = [new THREE.BufferAttribute(morphOffsets, 3)];
    geometry.morphTargetsRelative = true;
  }
  const finalGeometry = indexed ? geometry : geometry.toNonIndexed();
  const materials = [
    new THREE.MeshStandardMaterial({ side: THREE.DoubleSide }),
    new THREE.MeshStandardMaterial({ side: THREE.DoubleSide }),
  ];
  const mesh = new THREE.SkinnedMesh(finalGeometry, materials);
  mesh.name = 'Body';
  const b0 = new THREE.Bone();
  b0.name = 'b0';
  b0.position.set(0, -1, 0);
  const b1 = new THREE.Bone();
  b1.name = 'b1';
  b1.position.set(0, 1, 0);
  b0.add(b1);
  const scene = new THREE.Scene();
  scene.add(mesh);
  scene.add(b0);
  scene.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton([b0, b1]));
  return { scene, mesh, b0, b1, materials, geometry: finalGeometry };
}

function makePlain(name = 'Plain') {
  const geometry = new THREE.PlaneGeometry(2, 2, 10, 10);
  const pos = geometry.getAttribute('position');
  const mask = new Float32Array(pos.count);
  for (let i = 0; i < pos.count; i++) {
    mask[i] = Math.max(0, 1 - Math.hypot(pos.getX(i), pos.getY(i)) / 0.7);
  }
  geometry.setAttribute('_SOFT_P', new THREE.BufferAttribute(mask, 1));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.name = name;
  return mesh;
}

function run(body, seconds) {
  const steps = Math.round(seconds * FPS);
  for (let i = 0; i < steps; i++) body.update(1 / FPS);
}

function snapshot(body) {
  return Float32Array.from(body.dynamicMesh.geometry.getAttribute('position').array);
}

function positions(body) {
  return body.dynamicMesh.geometry.getAttribute('position').array;
}

function findVertex(snap, x, y) {
  for (let i = 0; i < snap.length / 3; i++) {
    if (Math.abs(snap[i * 3] - x) < 1e-4 && Math.abs(snap[i * 3 + 1] - y) < 1e-4) return i;
  }
  assert.fail(`no dynamic vertex at (${x}, ${y})`);
  return -1;
}

function displacement(body, snap, i) {
  const p = positions(body);
  return new THREE.Vector3(p[i * 3] - snap[i * 3], p[i * 3 + 1] - snap[i * 3 + 1], p[i * 3 + 2] - snap[i * 3 + 2]);
}

function maxDisplacement(body, snap) {
  let best = 0;
  let which = -1;
  const p = positions(body);
  for (let i = 0; i < snap.length / 3; i++) {
    const d = Math.hypot(p[i * 3] - snap[i * 3], p[i * 3 + 1] - snap[i * 3 + 1], p[i * 3 + 2] - snap[i * 3 + 2]);
    if (d > best) {
      best = d;
      which = i;
    }
  }
  return { best, which };
}

function castAlong(scene, body, origin, direction) {
  scene.updateMatrixWorld(true);
  const raycaster = new THREE.Raycaster(origin, direction.clone().normalize());
  const hits = raycaster.intersectObject(body.dynamicMesh, false);
  assert.ok(hits.length > 0, 'ray must hit the dynamic mesh');
  return hits[0];
}

function castDown(scene, body, x, y) {
  return castAlong(scene, body, new THREE.Vector3(x, y, 5), new THREE.Vector3(0, 0, -1));
}

/** Sorted per-triangle keys (material + posed, morphed centroid). */
function triangleKeys(mesh) {
  const geometry = mesh.geometry;
  const index = geometry.index;
  const total = index ? index.count : geometry.getAttribute('position').count;
  const vs = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const keys = [];
  for (let t = 0; t < total / 3; t++) {
    for (let k = 0; k < 3; k++) mesh.getVertexPosition(index ? index.getX(t * 3 + k) : t * 3 + k, vs[k]);
    const cx = (vs[0].x + vs[1].x + vs[2].x) / 3;
    const cy = (vs[0].y + vs[1].y + vs[2].y) / 3;
    const cz = (vs[0].z + vs[1].z + vs[2].z) / 3;
    const group = geometry.groups.find((g) => t * 3 >= g.start && t * 3 < g.start + g.count);
    keys.push(`${group ? group.materialIndex : '-'}|${cx.toFixed(4)},${cy.toFixed(4)},${cz.toFixed(4)}`);
  }
  return keys;
}

function cornerTotal(geometry) {
  return geometry.index ? geometry.index.count : geometry.getAttribute('position').count;
}

const REGION = [{ id: 'r', attribute: '_SOFT_R' }];

// ---------------------------------------------------------------------------

test('partition is disjoint, complete and preserves materials, groups, attributes and rig', () => {
  const f = makeFixture();
  f.mesh.morphTargetInfluences[0] = 0.5;
  f.b1.rotation.x = -0.5;
  f.scene.updateMatrixWorld(true);
  const before = triangleKeys(f.mesh).sort();
  const original = f.mesh.geometry;
  const body = new SoftBody(f.mesh, REGION);
  const dyn = body.dynamicMesh;

  assert.notEqual(f.mesh.geometry, original);
  assert.equal(dyn.parent, f.mesh);
  assert.ok(dyn.isSkinnedMesh);
  assert.equal(dyn.skeleton, f.mesh.skeleton);
  assert.equal(dyn.material, f.mesh.material);
  assert.equal(dyn.morphTargetInfluences, f.mesh.morphTargetInfluences);
  assert.ok(dyn.matrix.equals(new THREE.Matrix4()));

  const after = [...triangleKeys(f.mesh), ...triangleKeys(dyn)].sort();
  assert.deepEqual(after, before, 'static + dynamic triangles equal the original set, no duplicates');
  assert.equal(cornerTotal(f.mesh.geometry) + cornerTotal(dyn.geometry), cornerTotal(original));
  assert.ok(cornerTotal(dyn.geometry) > 0 && cornerTotal(f.mesh.geometry) > 0);
  const materialIndices = new Set(dyn.geometry.groups.map((g) => g.materialIndex));
  assert.deepEqual([...materialIndices].sort(), [0, 1]);
  assert.deepEqual(
    Object.keys(dyn.geometry.attributes).sort(),
    Object.keys(original.attributes).sort(),
  );
  assert.ok(dyn.geometry.getAttribute('skinIndex').array instanceof Uint16Array);
  assert.equal(dyn.geometry.morphAttributes.position.length, 1);

  const snap = snapshot(body);
  const uv = dyn.geometry.getAttribute('uv');
  const custom = dyn.geometry.getAttribute('_custom');
  const skinWeight = dyn.geometry.getAttribute('skinWeight');
  const morphOffset = dyn.geometry.morphAttributes.position[0];
  for (let i = 0; i < snap.length / 3; i++) {
    const x = snap[i * 3];
    const y = snap[i * 3 + 1];
    assert.ok(Math.abs(uv.getX(i) - (x * 0.5 + 0.5)) < 1e-5);
    assert.ok(Math.abs(custom.getY(i) - y * 2) < 1e-5);
    assert.ok(Math.abs(skinWeight.getY(i) - Math.min(1, Math.max(0, y + 0.5))) < 1e-5);
    assert.ok(Math.abs(morphOffset.getZ(i) - 0.2) < 1e-6);
  }
  body.dispose();
});

test('indexed, non-indexed and interleaved sources keep triangle parity', () => {
  for (const options of [{ indexed: false }, { interleave: true }, { morph: false }]) {
    const f = makeFixture(options);
    f.b1.rotation.x = 0.4;
    f.scene.updateMatrixWorld(true);
    const before = triangleKeys(f.mesh).sort();
    const body = new SoftBody(f.mesh, REGION);
    const after = [...triangleKeys(f.mesh), ...triangleKeys(body.dynamicMesh)].sort();
    assert.deepEqual(after, before, JSON.stringify(options));
    const pos = body.dynamicMesh.geometry.getAttribute('position');
    assert.ok(!pos.isInterleavedBufferAttribute && pos.array instanceof Float32Array);
    const uv = body.dynamicMesh.geometry.getAttribute('uv');
    const snap = snapshot(body);
    for (let i = 0; i < snap.length / 3; i++) {
      assert.ok(Math.abs(uv.getX(i) - (snap[i * 3] * 0.5 + 0.5)) < 1e-5);
    }
    body.dispose();
  }
});

test('neutral update and reset are exact parity; reset retains caller morph state', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  const normals = Float32Array.from(body.dynamicMesh.geometry.getAttribute('normal').array);
  run(body, 0.5);
  assert.deepEqual(Array.from(positions(body)), Array.from(snap));

  f.mesh.morphTargetInfluences[0] = 0.3;
  body.setSize('r', 1.4);
  body.impulse('r', new THREE.Vector3(0.5, 0, 0));
  body.press(castDown(f.scene, body, 0, 0.6));
  run(body, 0.3);
  assert.ok(maxDisplacement(body, snap).best > 0.01);

  body.reset();
  assert.deepEqual(Array.from(positions(body)), Array.from(snap));
  assert.deepEqual(Array.from(body.dynamicMesh.geometry.getAttribute('normal').array), Array.from(normals));
  assert.equal(body.getSize('r'), 1);
  assert.equal(body.getTargetSize('r'), 1);
  assert.equal(body.activePressCount, 0);
  assert.equal(f.mesh.morphTargetInfluences[0], 0.3);
  run(body, 1);
  assert.deepEqual(Array.from(positions(body)), Array.from(snap), 'no residual oscillation after reset');
  body.dispose();
});

test('size moves weighted vertices proportionally and never touches protected vertices', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  body.setSize('r', 1.4);
  run(body, 5);
  assert.ok(Math.abs(body.getSize('r') - 1.4) < 1e-3);

  const i = findVertex(snap, 0.3, 0.6); // mask weight 0.4
  const d = displacement(body, snap, i);
  const expected = 0.4 * (1.4 - 1) * (0.3 - body.regions[0].center[0]);
  assert.ok(Math.abs(d.x - expected) < 2e-3, `dx ${d.x} vs ${expected}`);
  assert.ok(Math.abs(d.z) < 1e-6);

  let moved = 0;
  const p = positions(body);
  for (let v = 0; v < snap.length / 3; v++) {
    const dist = Math.hypot(snap[v * 3], snap[v * 3 + 1] - 0.6);
    const changed = p[v * 3] !== snap[v * 3] || p[v * 3 + 1] !== snap[v * 3 + 1] || p[v * 3 + 2] !== snap[v * 3 + 2];
    if (dist > 0.5 + 1e-6) assert.equal(changed, false, `protected vertex ${v} moved`);
    if (changed) moved++;
  }
  assert.ok(moved > 10);
  assert.ok(body.regions[0].radius > 0.3 && body.regions[0].radius < 0.6);
  body.dispose();
});

test('overlapping region influence is normalised when it sums above one', () => {
  // Fully influenced mesh: every vertex has weight 1 in each region. Two
  // overlapping regions sum to 2 and must be normalised to 0.5 + 0.5, so the
  // result equals one region of weight 1 rather than doubling.
  const dxFor = (regions, sizeIds) => {
    const f = makeFixture();
    const body = new SoftBody(f.mesh, regions);
    const snap = snapshot(body);
    for (const id of sizeIds) body.setSize(id, 1.4);
    run(body, 5);
    const dx = displacement(body, snap, findVertex(snap, 0.3, 0.6)).x;
    const cx = body.regions[0].center[0];
    body.dispose();
    return { dx, cx };
  };
  const single = dxFor([{ id: 'r', attribute: '_SOFT_ONE' }], ['r']);
  const double = dxFor(
    [
      { id: 'one', attribute: '_SOFT_ONE' },
      { id: 'two', attribute: '_SOFT_ONE' },
    ],
    ['one', 'two'],
  );
  const expected = (1.4 - 1) * (0.3 - single.cx);
  assert.ok(Math.abs(single.dx - expected) < 2e-3, `single ${single.dx} vs ${expected}`);
  assert.ok(Math.abs(double.dx - expected) < 2e-3, `double ${double.dx} vs ${expected} (unnormalised would be ${2 * expected})`);
});

test('dynamic mesh is never frustum-culled by a stale pose bound; source culling is untouched', () => {
  const f = makeFixture();
  const sourceCulled = f.mesh.frustumCulled;
  const body = new SoftBody(f.mesh, REGION);
  const dyn = body.dynamicMesh;
  run(body, 0.5);
  const snap = snapshot(body);
  const vertex = findVertex(snap, 0, 0.9); // skin weight 1 on b1
  f.scene.updateMatrixWorld(true);
  dyn.computeBoundingSphere(); // renderer-style cache taken in the rest pose
  const staleSphere = dyn.boundingSphere.clone();

  f.b1.rotation.x = Math.PI;
  f.b1.position.y -= 10; // carries b1's vertices far from the cached bound
  f.scene.updateMatrixWorld(true);
  const posed = dyn.getVertexPosition(vertex, new THREE.Vector3()).applyMatrix4(dyn.matrixWorld);
  assert.ok(posed.y < -8, `vertex really followed the bone (${posed.y})`);
  const camera = new THREE.PerspectiveCamera(4, 1, 0.1, 50);
  camera.position.set(posed.x, posed.y, posed.z + 1);
  camera.lookAt(posed);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  const frustum = new THREE.Frustum().setFromProjectionMatrix(
    new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse),
  );
  assert.ok(frustum.containsPoint(posed), 'camera sees the posed vertex');
  assert.equal(frustum.intersectsSphere(staleSphere), false, 'precondition: the cached rest-pose bound misses the camera');

  // WebGLRenderer draws an object when frustumCulled is false or its bound intersects.
  const drawn = dyn.frustumCulled === false || frustum.intersectsObject(dyn);
  assert.equal(drawn, true, 'posed dynamic mesh must still be drawn');

  body.dispose();
  assert.equal(f.mesh.frustumCulled, sourceCulled);
});

test('setSize / setSoftness / impulse validate input', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  for (const bad of [0.59, 1.51, NaN, Infinity, '1', undefined]) {
    assert.throws(() => body.setSize('r', bad), RangeError);
  }
  assert.throws(() => body.setSize('missing', 1));
  for (const bad of [-0.01, 1.01, NaN, '0.5']) assert.throws(() => body.setSoftness(bad), RangeError);
  assert.throws(() => body.impulse('r', { x: 1, y: 1, z: 1 }), TypeError);
  assert.throws(() => body.impulse('r', new THREE.Vector3(NaN, 0, 0)), TypeError);
  assert.throws(() => body.impulse('nope', new THREE.Vector3(1, 0, 0)));
  body.setSize('r', 0.6);
  body.setSize('r', 1.5);
  body.setSoftness(0);
  body.setSoftness(1);
  assert.equal(body.softness, 1);
  body.dispose();
});

test('press maps a genuinely posed hit back to the rest surface, drags, then decays', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  const theta = -Math.PI / 3;
  f.b1.rotation.x = theta;
  f.scene.updateMatrixWorld(true);

  const posedPoint = (x, y) => new THREE.Vector3(x, y, 0).applyAxisAngle(X_AXIS, theta);
  const posedNormal = new THREE.Vector3(0, 0, 1).applyAxisAngle(X_AXIS, theta);
  const aim = (x, y) => castAlong(f.scene, body, posedPoint(x, y).addScaledVector(posedNormal, 2), posedNormal.clone().negate());

  const hit = aim(0, 0.6);
  assert.equal(hit.object, body.dynamicMesh);
  assert.ok(hit.point.distanceTo(posedPoint(0, 0.6)) < 1e-4, 'ray really hit the bent surface');
  // A naive worldToLocal would resolve to roughly (0, 0.3, -0.52): far from the rest anchor.
  assert.ok(Math.abs(hit.point.y - 0.6) > 0.25);

  const token = body.press(hit);
  assert.equal(body.activePressCount, 1);
  run(body, 1);
  const peak = maxDisplacement(body, snap);
  const peakRest = new THREE.Vector2(snap[peak.which * 3], snap[peak.which * 3 + 1]);
  assert.ok(peakRest.distanceTo(new THREE.Vector2(0, 0.6)) < 0.11, `peak at rest ${peakRest.toArray()}`);
  assert.ok(displacement(body, snap, peak.which).z < -0.01, 'indented along the rest normal');
  const naive = displacement(body, snap, findVertex(snap, 0, 0.3));
  assert.ok(naive.length() < peak.best * 0.3, 'vertex under the naive world-space mapping is barely affected');

  // Surrounding bulge: some vertex rises opposite to the indentation.
  const p = positions(body);
  let bulge = 0;
  for (let v = 0; v < snap.length / 3; v++) bulge = Math.max(bulge, p[v * 3 + 2] - snap[v * 3 + 2]);
  assert.ok(bulge > 1e-3, 'bulge around the dent');

  const center = findVertex(snap, 0, 0.6);
  const dxBefore = displacement(body, snap, center).x;
  body.move(token, aim(0.3, 0.6));
  run(body, 1);
  const dxAfter = displacement(body, snap, center).x;
  assert.ok(dxAfter - dxBefore > 0.05, `shear moved the pressed area (${dxBefore} -> ${dxAfter})`);

  assert.equal(body.release(token), true);
  run(body, 6);
  assert.equal(maxDisplacement(body, snap).best, 0, 'spring release restores the rest surface');
  assert.equal(body.activePressCount, 0);
  assert.equal(body.release(token), false);
  assert.throws(() => body.move(token, hit));
  body.dispose();
});

test('invalid or unrelated hits are rejected without corrupting state', () => {
  const f = makeFixture();
  const other = makePlain('Other');
  f.scene.add(other);
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  const good = castDown(f.scene, body, 0, 0.6);

  const stranger = new THREE.Raycaster(new THREE.Vector3(0, 0, 5), new THREE.Vector3(0, 0, -1)).intersectObject(other)[0];
  assert.throws(() => body.press(stranger));
  assert.throws(() => body.press(null));
  assert.throws(() => body.press({ ...good, point: new THREE.Vector3(NaN, 0, 0) }));
  assert.throws(() => body.press({ ...good, faceIndex: -1 }));
  assert.throws(() => body.press({ ...good, faceIndex: 1e9 }));
  assert.equal(body.activePressCount, 0);
  run(body, 0.5);
  assert.deepEqual(Array.from(positions(body)), Array.from(snap));

  const token = body.press(good);
  assert.throws(() => body.move(token, stranger));
  assert.throws(() => body.move(9999, good));
  run(body, 0.5);
  assert.ok(maxDisplacement(body, snap).best > 0.01, 'valid press survived rejected move');
  body.dispose();
});

test('concurrent presses are capped', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const hit = castDown(f.scene, body, 0, 0.6);
  const tokens = [];
  for (let i = 0; i < 4; i++) tokens.push(body.press(hit));
  assert.equal(new Set(tokens).size, 4);
  assert.throws(() => body.press(hit), RangeError);
  assert.equal(body.activePressCount, 4);
  for (const t of tokens) body.release(t);
  run(body, 6);
  assert.equal(body.activePressCount, 0);
  body.dispose();
});

test('softness scales the press response', () => {
  const peaks = [];
  for (const softness of [0, 1]) {
    const f = makeFixture();
    const body = new SoftBody(f.mesh, REGION);
    body.setSoftness(softness);
    const snap = snapshot(body);
    body.press(castDown(f.scene, body, 0, 0.6));
    run(body, 2);
    peaks.push(maxDisplacement(body, snap).best);
    body.dispose();
  }
  assert.ok(peaks[1] > peaks[0] * 1.5, `soft ${peaks[1]} vs stiff ${peaks[0]}`);
});

test('impulse jiggles the region and settles back to rest', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  body.impulse('r', new THREE.Vector3(0.4, 0, 0));
  run(body, 0.1);
  const i = findVertex(snap, 0, 0.6);
  assert.ok(Math.abs(displacement(body, snap, i).x) > 1e-3);
  run(body, 6);
  assert.equal(maxDisplacement(body, snap).best, 0);
  body.dispose();
});

test('long or hostile frames stay bounded and finite', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  body.setSize('r', 1.5);
  body.impulse('r', new THREE.Vector3(500, -500, 500));
  body.press(castDown(f.scene, body, 0, 0.6));
  body.update(1e6);
  body.update(30);
  body.update(0);
  for (const v of positions(body)) assert.ok(Number.isFinite(v));
  for (const v of body.dynamicMesh.geometry.getAttribute('normal').array) assert.ok(Number.isFinite(v));
  assert.ok(maxDisplacement(body, snap).best < 1.5);
  assert.ok(body.getSize('r') >= 0.4 && body.getSize('r') <= 1.8);
  assert.throws(() => body.update(NaN), RangeError);
  assert.throws(() => body.update(-1), RangeError);
  assert.throws(() => body.update(Infinity), RangeError);
  body.dispose();
});

test('hair follows growth and does not shrink through the body', () => {
  const f = makeFixture({ hair: true });
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  const hairVertex = findVertex(snap, 0, 0.9); // hair = 1, mask weight 0.4
  const bodyVertex = findVertex(snap, 0.3, 0.6);
  const center = body.regions[0].center;
  assert.ok(center[1] < 0.75, 'hair vertices excluded from the support centre');

  body.setSize('r', 1.4);
  run(body, 5);
  const grown = displacement(body, snap, hairVertex);
  const expected = 0.4 * 0.4 * (0.9 - center[1]);
  assert.ok(grown.y > 0.01, 'hair grows with the body');
  assert.ok(Math.abs(grown.y - expected) < 3e-3, `${grown.y} vs ${expected}`);

  body.reset();
  body.setSize('r', 0.7);
  run(body, 5);
  const shrunk = displacement(body, snap, hairVertex);
  assert.ok(shrunk.length() < 1e-7, 'hair keeps its rest position while the body shrinks');
  assert.ok(displacement(body, snap, bodyVertex).x < -0.02, 'non-hair vertices do shrink');
  body.dispose();
});

test('hair-only regions need explicit centre and radius', () => {
  const f = makeFixture({ hair: true });
  const original = f.mesh.geometry;
  const childCount = f.mesh.children.length;
  assert.throws(() => new SoftBody(f.mesh, [{ id: 'h', attribute: '_SOFT_HAIRONLY' }]), /hair/i);
  assert.equal(f.mesh.geometry, original);
  assert.equal(f.mesh.children.length, childCount);

  const body = new SoftBody(f.mesh, [
    { id: 'h', attribute: '_SOFT_HAIRONLY', center: [0, 0.9, 0], radius: 0.3 },
  ]);
  assert.deepEqual(body.regions[0].center, [0, 0.9, 0]);
  assert.equal(body.regions[0].radius, 0.3);
  const snap = snapshot(body);
  body.setSize('h', 1.5);
  run(body, 5);
  assert.ok(maxDisplacement(body, snap).best > 0.01);
  body.dispose();
});

test('explicit region centre and radius override derived values', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, [
    { id: 'r', attribute: '_SOFT_R', center: [0.2, 0.6, 0], radius: 0.25, group: 'g', bone: 'b1' },
  ]);
  assert.deepEqual(body.regions[0].center, [0.2, 0.6, 0]);
  assert.equal(body.regions[0].radius, 0.25);
  assert.equal(body.regions[0].group, 'g');
  assert.equal(body.regions[0].bone, 'b1');
  body.dispose();
});

test('constructor rejects bad input and leaves the source mesh untouched', () => {
  const f = makeFixture({ hair: true });
  const original = f.mesh.geometry;
  const childCount = f.mesh.children.length;
  const cases = [
    [[]],
    [[{ id: 'a', attribute: '_SOFT_MISSING' }]],
    [[{ id: 'a', attribute: '_SOFT_ZERO' }]],
    [[{ id: 'a', attribute: '_SOFT_BAD' }]],
    [[{ id: 'a', attribute: '_SOFT_R' }, { id: 'a', attribute: '_SOFT_R' }]],
    [[{ id: 'a', attribute: '_SOFT_R', bone: 'no-such-bone' }]],
    [[{ id: 'a', attribute: '_SOFT_R', radius: -1 }]],
    [[{ id: 'a', attribute: '_SOFT_R', center: [0, NaN, 0] }]],
    [[{ id: '', attribute: '_SOFT_R' }]],
    [[{ id: 'a', attribute: 'position' }]],
  ];
  for (const [regions] of cases) {
    assert.throws(() => new SoftBody(f.mesh, regions), Error, JSON.stringify(regions));
    assert.equal(f.mesh.geometry, original);
    assert.equal(f.mesh.children.length, childCount);
  }
  assert.throws(() => new SoftBody(new THREE.Points(new THREE.BufferGeometry()), REGION));
  assert.throws(() => new SoftBody(f.mesh, REGION, { substeps: 0 }));
  const instanced = new THREE.InstancedMesh(original, f.materials, 1);
  assert.throws(() => new SoftBody(instanced, REGION));
});

test('a source mesh can host only one active SoftBody until disposed', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  assert.throws(() => new SoftBody(f.mesh, REGION));
  body.dispose();
  const again = new SoftBody(f.mesh, REGION);
  again.dispose();
});

test('dispose restores the source, frees only owned geometry and is idempotent', () => {
  const f = makeFixture();
  const original = f.mesh.geometry;
  let materialDisposals = 0;
  let originalDisposals = 0;
  for (const m of f.materials) m.addEventListener('dispose', () => materialDisposals++);
  original.addEventListener('dispose', () => originalDisposals++);
  const body = new SoftBody(f.mesh, REGION);
  const dyn = body.dynamicMesh;
  let dynamicDisposals = 0;
  dyn.geometry.addEventListener('dispose', () => dynamicDisposals++);

  body.dispose();
  body.dispose();
  assert.equal(f.mesh.geometry, original);
  assert.equal(dyn.parent, null);
  assert.equal(f.mesh.children.includes(dyn), false);
  assert.equal(dynamicDisposals, 1);
  assert.equal(materialDisposals, 0);
  assert.equal(originalDisposals, 0);
  assert.equal(original.getAttribute('position').count, GRID * GRID);
  assert.equal(body.disposed, true);
  assert.throws(() => body.update(0.016));
  assert.throws(() => body.setSize('r', 1));
});

test('posed skinning and live morph influences survive on the dynamic mesh', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const dyn = body.dynamicMesh;
  const snap = snapshot(body);
  const v = findVertex(snap, 0, 0.9); // skin weight 1 on b1
  const out = new THREE.Vector3();

  const theta = 0.7;
  f.b1.rotation.x = theta;
  f.scene.updateMatrixWorld(true);
  dyn.getVertexPosition(v, out);
  const expected = new THREE.Vector3(0, 0.9, 0).applyAxisAngle(X_AXIS, theta);
  assert.ok(out.distanceTo(expected) < 1e-5, 'dynamic mesh follows the shared skeleton');

  f.b1.rotation.x = 0;
  f.scene.updateMatrixWorld(true);
  f.mesh.morphTargetInfluences[0] = 1;
  dyn.getVertexPosition(v, out);
  assert.ok(Math.abs(out.z - 0.2) < 1e-6, 'live morph influence reaches the dynamic mesh');
  body.setSize('r', 1.3);
  run(body, 3);
  f.mesh.morphTargetInfluences[0] = 0.25;
  dyn.getVertexPosition(v, out);
  const base = displacement(body, snap, v);
  assert.ok(Math.abs(out.z - (0.25 * 0.2 + base.z)) < 1e-5, 'morph is additive on top of the deformation');
  body.dispose();
});

test('normals stay unit length, change under press and keep the static seam normal', () => {
  const f = makeFixture();
  const body = new SoftBody(f.mesh, REGION);
  const snap = snapshot(body);
  body.press(castDown(f.scene, body, 0, 0.6));
  run(body, 1);
  const normals = body.dynamicMesh.geometry.getAttribute('normal').array;
  let tilted = 0;
  for (let v = 0; v < snap.length / 3; v++) {
    const n = Math.hypot(normals[v * 3], normals[v * 3 + 1], normals[v * 3 + 2]);
    assert.ok(Math.abs(n - 1) < 1e-4);
    const dist = Math.hypot(snap[v * 3], snap[v * 3 + 1] - 0.6);
    if (dist > 0.5 + 1e-6) {
      assert.ok(Math.abs(normals[v * 3 + 2] - 1) < 1e-6, 'seam vertex keeps the authored normal');
    } else if (normals[v * 3 + 2] < 0.97) tilted++;
  }
  assert.ok(tilted > 0, 'normals follow the dent');
  body.dispose();
});

test('non-skinned meshes work: press hits are mapped and release decays', () => {
  const scene = new THREE.Scene();
  const mesh = makePlain();
  scene.add(mesh);
  const body = new SoftBody(mesh, [{ id: 'p', attribute: '_SOFT_P' }]);
  assert.ok(!body.dynamicMesh.isSkinnedMesh);
  const snap = snapshot(body);
  scene.updateMatrixWorld(true);
  const token = body.press(castDown(scene, body, 0.2, 0));
  run(body, 1);
  const peak = maxDisplacement(body, snap);
  assert.ok(peak.best > 0.01);
  assert.ok(Math.hypot(snap[peak.which * 3] - 0.2, snap[peak.which * 3 + 1]) < 0.25);
  body.release(token);
  run(body, 6);
  assert.equal(maxDisplacement(body, snap).best, 0);
  body.dispose();
});

// ---------------------------------------------------------------------------

function sidecar(extra = {}) {
  return {
    version: 1,
    meshes: [
      { name: 'Body', regions: [{ id: 'r', group: 'g', attribute: '_SOFT_R', bone: 'b1' }] },
      { name: 'Plain', regions: [{ id: 'p', attribute: '_SOFT_P' }] },
    ],
    ...extra,
  };
}

test('attachSoftBodies returns controllers in sidecar order', () => {
  const f = makeFixture();
  const plain = makePlain();
  f.scene.add(plain);
  const controllers = attachSoftBodies(f.scene, sidecar());
  assert.equal(controllers.length, 2);
  assert.ok(controllers.every((c) => c instanceof SoftBody));
  assert.equal(controllers[0].sourceMesh, f.mesh);
  assert.equal(controllers[1].sourceMesh, plain);
  assert.equal(controllers[0].regions[0].id, 'r');
  assert.equal(controllers[1].regions[0].id, 'p');
  for (const c of controllers) c.dispose();
});

test('attachSoftBodies is transactional on construction failure', () => {
  const f = makeFixture();
  const plain = makePlain();
  f.scene.add(plain);
  const bodyGeometry = f.mesh.geometry;
  const plainGeometry = plain.geometry;
  const bodyChildren = f.mesh.children.length;
  const bad = sidecar({
    meshes: [
      { name: 'Body', regions: [{ id: 'r', attribute: '_SOFT_R' }] },
      { name: 'Plain', regions: [{ id: 'p', attribute: '_SOFT_NOPE' }] },
    ],
  });
  assert.throws(() => attachSoftBodies(f.scene, bad), /not found/);
  assert.equal(f.mesh.geometry, bodyGeometry);
  assert.equal(plain.geometry, plainGeometry);
  assert.equal(f.mesh.children.length, bodyChildren);

  const controllers = attachSoftBodies(f.scene, sidecar());
  assert.equal(controllers.length, 2, 'rolled-back meshes can be attached again');
  for (const c of controllers) c.dispose();
});

test('attachSoftBodies validates the sidecar and mesh references', () => {
  const f = makeFixture();
  const plain = makePlain();
  f.scene.add(plain);
  assert.throws(() => attachSoftBodies(f.scene, null));
  assert.throws(() => attachSoftBodies(f.scene, sidecar({ version: 2 })));
  assert.throws(() => attachSoftBodies(f.scene, { version: 1, meshes: [] }));
  assert.throws(() => attachSoftBodies(f.scene, { version: 1, meshes: [{ name: 'Ghost', regions: [{ id: 'a', attribute: '_SOFT_R' }] }] }), /not found/);
  assert.throws(() => attachSoftBodies(f.scene, { version: 1, meshes: [{ name: 'Body', regions: [] }] }));
  assert.throws(
    () => attachSoftBodies(f.scene, { version: 1, meshes: [{ name: 'Body', regions: [{ id: 'a', attribute: '_SOFT_R' }, { id: 'a', attribute: '_SOFT_R' }] }] }),
    /repeats/,
  );
  assert.throws(
    () => attachSoftBodies(f.scene, { version: 1, meshes: [{ name: 'Body', regions: [{ id: 'a', attribute: '_SOFT_R' }] }, { name: 'Body', regions: [{ id: 'b', attribute: '_SOFT_R' }] }] }),
    /more than once/,
  );
  const twin = makePlain('Plain');
  f.scene.add(twin);
  assert.throws(() => attachSoftBodies(f.scene, sidecar()), /ambiguous/);
  f.scene.remove(twin);

  const attached = attachSoftBodies(f.scene, sidecar());
  assert.throws(() => attachSoftBodies(f.scene, sidecar()), /already/);
  for (const c of attached) c.dispose();
});

test('a declared missing hair mask rejects admission without mutating the source', () => {
  const f = makeFixture();
  const geometry = f.mesh.geometry;
  const children = f.mesh.children.length;
  const entry = { name: 'Body', hairAttribute: '_MISSING_HAIR', regions: REGION };
  for (const attach of [
    () => new SoftBody(f.mesh, REGION, { hairAttribute: entry.hairAttribute }),
    () => attachSoftBodies(f.scene, { version: 1, meshes: [entry] }),
  ]) {
    assert.throws(attach, Error);
    assert.equal(f.mesh.geometry, geometry);
    assert.equal(f.mesh.children.length, children);
  }
  // No authored hair is still valid when the optional mask is not declared.
  const body = new SoftBody(f.mesh, REGION);
  body.dispose();
});

test('attachSoftBodies matches sanitized loader names through userData.name', () => {
  const f = makeFixture();
  f.mesh.name = 'Body_Mesh';
  f.mesh.userData.name = 'Body Mesh';
  f.b1.userData.name = 'Spine 2';
  const controllers = attachSoftBodies(f.scene, {
    version: 1,
    meshes: [{ name: 'Body Mesh', regions: [{ id: 'r', attribute: '_SOFT_R', bone: 'Spine 2' }] }],
  });
  assert.equal(controllers[0].sourceMesh, f.mesh);
  for (const c of controllers) c.dispose();
});

function assertSurfaceIntegrity(body, rest, restNormals = null) {
  const geometry = body.dynamicMesh.geometry;
  const p = geometry.getAttribute('position').array;
  const index = geometry.index.array;
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const u = new THREE.Vector3(), v = new THREE.Vector3(), n = new THREE.Vector3();
  for (let t = 0; t < index.length; t += 3) {
    a.fromArray(rest, index[t] * 3);
    b.fromArray(rest, index[t + 1] * 3).sub(a);
    c.fromArray(rest, index[t + 2] * 3).sub(a);
    n.crossVectors(b, c);
    a.fromArray(p, index[t] * 3);
    u.fromArray(p, index[t + 1] * 3).sub(a);
    v.fromArray(p, index[t + 2] * 3).sub(a);
    if (n.lengthSq() > 0) {
      const area = a.crossVectors(u, v).dot(n) / n.lengthSq();
      assert.ok(area >= 0.1499, `triangle ${t / 3} projected area ${area}`);
    }
    for (let k = 0; k < 3; k++) {
      const i = index[t + k] * 3, j = index[t + (k + 1) % 3] * 3;
      const before = a.fromArray(rest, i).distanceTo(b.fromArray(rest, j));
      if (before === 0) continue;
      const strain = a.fromArray(p, i).distanceTo(b.fromArray(p, j)) / before;
      assert.ok(strain >= 0.3999 && strain <= 1.8001, `edge length ratio ${strain}`);
    }
  }
  const coincident = new Map();
  const normal = geometry.getAttribute('normal');
  for (let i = 0; i < p.length; i += 3) {
    const key = `${rest[i]},${rest[i + 1]},${rest[i + 2]}`;
    const other = coincident.get(key);
    if (other !== undefined) {
      assert.ok(p[i] === p[other] && p[i + 1] === p[other + 1] && p[i + 2] === p[other + 2], 'UV splits stay coincident');
      if (restNormals && Math.hypot(restNormals[i] - restNormals[other], restNormals[i + 1] - restNormals[other + 1], restNormals[i + 2] - restNormals[other + 2]) < 1e-5) {
        assert.ok(Math.hypot(normal.array[i] - normal.array[other], normal.array[i + 1] - normal.array[other + 1], normal.array[i + 2] - normal.array[other + 2]) < 1e-5, 'smooth UV seams retain continuous normals');
      }
    } else coincident.set(key, i);
    const length = Math.hypot(normal.getX(i / 3), normal.getY(i / 3), normal.getZ(i / 3));
    assert.ok(Number.isFinite(length) && Math.abs(length - 1) < 1e-5);
  }
}

test('curved UV-split surface keeps triangle orientation and bounded strain through contact and release', () => {
  const geometry = new THREE.SphereGeometry(0.3, 16, 12).toNonIndexed();
  const pos = geometry.getAttribute('position');
  const mask = new Float32Array(pos.count);
  for (let i = 0; i < mask.length; i++) mask[i] = Math.max(0, Math.min(1, pos.getZ(i) / 0.15));
  geometry.setAttribute('_SOFT_P', new THREE.BufferAttribute(mask, 1));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  const scene = new THREE.Scene();
  scene.add(mesh);
  const body = new SoftBody(mesh, [{ id: 'p', attribute: '_SOFT_P', center: [0, 0, 0], radius: 0.4 }]);
  const rest = snapshot(body);
  const initialNormals = body.dynamicMesh.geometry.getAttribute('normal').array.slice();
  const hit = castDown(scene, body, 0, 0);
  const drag = castDown(scene, body, 0.2, 0);
  const advance = (frames) => {
    for (let i = 0; i < frames; i++) {
      body.update(1 / FPS);
      assertSurfaceIntegrity(body, rest, initialNormals);
      const p = positions(body);
      for (let j = 0; j < rest.length; j += 3) {
        if (rest[j + 2] <= 0) {
          assert.ok(p[j] === rest[j] && p[j + 1] === rest[j + 1] && p[j + 2] === rest[j + 2], 'protected boundary stays fixed');
        }
      }
    }
  };
  body.setSoftness(0.5);
  const token = body.press(hit);
  advance(30);
  assert.ok(maxDisplacement(body, rest).best > 0.005, 'ordinary indentation remains visible');
  body.move(token, drag);
  advance(30);
  assert.ok(positions(body).some((value, i) => i % 3 === 0 && value - rest[i] > 0.005), 'drag still shears');
  body.release(token);
  advance(180);
  assert.deepEqual(snapshot(body), rest);
  assert.deepEqual(body.dynamicMesh.geometry.getAttribute('normal').array, initialNormals);

  body.setSoftness(1);
  const tokens = Array.from({ length: 4 }, () => body.press(hit));
  for (const token of tokens) body.move(token, drag);
  body.setSize('p', 1.5);
  advance(90);
  assert.ok(maxDisplacement(body, rest).best > 0.005, 'stressed contact is bounded, not disabled');
  for (const token of tokens) body.release(token);
  body.setSize('p', 0.6);
  advance(90);
  body.setSize('p', 1);
  advance(300);
  assert.deepEqual(snapshot(body), rest);
  body.dispose();
});

test('projection stops at the first collapse even when the candidate endpoint recovers orientation', () => {
  const mesh = makePlain();
  const body = new SoftBody(mesh, [{ id: 'p', attribute: '_SOFT_P' }]);
  const rest = snapshot(body);
  const p = positions(body);
  // A 180-degree planar candidate has positive endpoint area, but its linear
  // path collapses all edges halfway. Endpoint-only checks miss the failure.
  for (let i = 0; i < p.length; i += 3) {
    p[i] = -rest[i];
    p[i + 1] = -rest[i + 1];
  }
  body._limitDeformation();
  assertSurfaceIntegrity(body, rest);
  for (let i = 0; i < p.length; i += 3) {
    assert.ok(p[i] * rest[i] >= 0 && p[i + 1] * rest[i + 1] >= 0, 'stays before first collapse');
  }
  body.dispose();
});

test('contact preserves authored hard-edge face normals while smoothing UV splits', () => {
  const geometry = new THREE.BoxGeometry(0.6, 0.6, 0.6, 4, 4, 4).toNonIndexed();
  geometry.setAttribute('_SOFT_P', new THREE.BufferAttribute(new Float32Array(geometry.attributes.position.count).fill(1), 1));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  const scene = new THREE.Scene();
  scene.add(mesh);
  const body = new SoftBody(mesh, [{ id: 'p', attribute: '_SOFT_P', center: [0, 0, 0], radius: 0.6 }]);
  const initial = body.dynamicMesh.geometry.attributes.normal.array.slice();
  const token = body.press(castDown(scene, body, 0.25, 0));
  for (let i = 0; i < 30; i++) body.update(1 / FPS);
  const normal = body.dynamicMesh.geometry.attributes.normal.array;
  let frontTilt = 0;
  for (let i = 0; i < initial.length; i += 3) {
    if (initial[i] > 0.99) {
      // Indentation only moves Z: the X-facing plane cannot tilt.
      assert.ok(Math.abs(normal[i] - 1) < 1e-6 && Math.abs(normal[i + 1]) < 1e-6 && Math.abs(normal[i + 2]) < 1e-6);
    }
    if (initial[i + 2] > 0.99) frontTilt = Math.max(frontTilt, Math.hypot(normal[i], normal[i + 1]));
  }
  assert.ok(frontTilt > 0.01, 'front surface genuinely bends beside the unchanged side plane');
  body.release(token);
  body.dispose();
});
