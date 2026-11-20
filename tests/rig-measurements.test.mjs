import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {measureRig} from '../runtime/rig-measurements.mjs';

function fixture({brokenBinding = false, brokenStop = false, vertices = 66} = {}) {
  const root = new THREE.Group();
  const bone = new THREE.Bone();
  bone.name = 'Joint';
  root.add(bone);
  const geometry = new THREE.BufferGeometry();
  const positions = [], indices = [], weights = [];
  for (let i = 0; i < vertices; i++) {
    positions.push(i / vertices, 0, 0);
    indices.push(0, 0, 0, 0);
    weights.push(1, 0, 0, 0);
  }
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(indices, 4));
  geometry.setAttribute('skinWeight', new THREE.Float32BufferAttribute(weights, 4));
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshBasicMaterial());
  mesh.name = 'Body';
  root.add(mesh);
  root.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton([bone]));
  const clip = new THREE.AnimationClip('move', 1, [
    new THREE.VectorKeyframeTrack('Joint.position', [0, 1], [0, 0, 0, 1, 0, 0]),
  ]);
  const mixer = new THREE.AnimationMixer(root);
  const controller = {
    seek(name, time) {
      if (brokenBinding) return;
      mixer.stopAllAction();
      const action = mixer.clipAction(clip);
      action.reset().setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
      action.play();
      mixer.setTime(time);
    },
    stop() { if (!brokenStop) mixer.stopAllAction(); },
  };
  return {root, clips: [clip], controller, meshIds: new Map([[mesh, 'node:1/primitive:0']]), glbSha256: 'a'.repeat(64)};
}

test('real mixer binding, distinct deformed vertices and stop restoration are measured', () => {
  const input = fixture();
  const result = measureRig(input);
  assert.ok(result.measurements.bindingSamples.maxSampledBindingDelta <= 2 ** -23);
  assert.equal(result.measurements.bindingSamples.clips.move.sampleCount, 5);
  assert.equal(result.measurements.deformation.nonFiniteCount, 0);
  assert.deepEqual(result.measurements.deformation.meshes['node:1/primitive:0'].verticesPerFrame, [66, 66, 66, 66, 66]);
  assert.equal(result.measurements.bindRestore.maxBindRestoreDelta, 0);
  assert.equal(result.measurements.bindRestore.maxBindRestoreVertexDelta, 0);
  assert.deepEqual(result.measurements.bindRestore.meshes, {'node:1/primitive:0': {vertexCount: 66}});
  assert.equal(input.root.getObjectByName('Joint').position.x, 0);
});

test('silently nonbinding delivered controller produces a failing G1 number', () => {
  const result = measureRig(fixture({brokenBinding: true}));
  assert.equal(result.measurements.bindingSamples.maxSampledBindingDelta, 1);
});

test('broken stop is measured rather than fixed by the probe', () => {
  const result = measureRig(fixture({brokenStop: true}));
  assert.equal(result.measurements.bindRestore.maxBindRestoreDelta, 1);
  assert.equal(result.measurements.bindRestore.maxBindRestoreVertexDelta, 1);
});

test('tiny meshes are never padded with duplicate vertex samples', () => {
  const result = measureRig(fixture({vertices: 3}));
  assert.deepEqual(result.measurements.deformation.meshes['node:1/primitive:0'].verticesPerFrame, [3, 3, 3, 3, 3]);
});

test('missing controller and source mesh associations fail closed', () => {
  assert.throws(() => measureRig({...fixture(), controller: null}), /producer missing/);
  assert.throws(() => measureRig({...fixture(), meshIds: new Map()}), /primitive identities/);
});

test('missing target cannot become a zero-delta binding pass', () => {
  const input = fixture();
  input.clips[0].tracks[0].name = 'Absent.position';
  assert.throws(() => measureRig(input), /unresolved/);
});

test('non-finite skin weights do not produce successful evidence', () => {
  const input = fixture();
  input.root.getObjectByName('Body').geometry.attributes.skinWeight.setX(0, NaN);
  assert.throws(() => measureRig(input), /non-finite skinWeight/);
});
