// Measure the delivered controller, not a second animation implementation.
import {PropertyBinding, Vector3} from 'three';

const fail = message => { throw new Error(`Rig measurements: ${message}`); };
const finite = values => values.every(Number.isFinite);
const finiteVector = value => Number.isFinite(value.x) && Number.isFinite(value.y) && Number.isFinite(value.z);

function transforms(node) {
  return [...node.position.toArray(), ...node.quaternion.toArray(), ...node.scale.toArray()];
}

function update(root, meshes) {
  root.updateMatrixWorld(true);
  for (const mesh of meshes) mesh.skeleton.update();
}

function buffers(mesh, name) {
  const attributes = {};
  for (const key of ['position', 'normal', 'uv', 'skinIndex', 'skinWeight']) {
    const attribute = mesh.geometry.getAttribute(key);
    if (!attribute) continue;
    const values = [];
    for (let i = 0; i < attribute.count; i++) {
      for (let j = 0; j < attribute.itemSize; j++) values.push(attribute.getComponent(i, j));
    }
    if (!finite(values)) fail(`non-finite ${key} on ${mesh.name}`);
    attributes[key] = values;
  }
  const index = mesh.geometry.index;
  return {name, attributes, index: index ? Array.from(index.array) : null};
}

/**
 * glbSha256 must be computed from the exact bytes passed to GLTFLoader. The caller
 * persists this result as evidence; this function does not assert artifact acceptance.
 * controller.seek(clipName,time) / stop() are the ACTUAL delivered runtime methods.
 * Run on a disposable loaded copy, with external tickers paused. No rig/weight edits.
 */
export function measureRig({root, clips, controller, glbSha256, meshIds, sampleCount = 5}) {
  if (!/^[a-f0-9]{64}$/.test(glbSha256)) fail('exact source GLB hash required');
  if (!root?.isObject3D || !Array.isArray(clips) || clips.length === 0) fail('animated rig required');
  if (!controller || typeof controller.seek !== 'function' || typeof controller.stop !== 'function') {
    fail('delivered controller seek/stop producer missing');
  }
  if (!Number.isInteger(sampleCount) || sampleCount < 5) fail('at least five samples required');
  const nodes = [], visible = [], skinned = [];
  root.traverse(node => {
    nodes.push(node);
    if (!node.isMesh) return;
    let shown = true;
    for (let current = node; current; current = current.parent) shown &&= current.visible;
    if (shown) visible.push(node);
    if (node.isSkinnedMesh && shown) skinned.push(node);
  });
  if (!skinned.length) fail('no visible skinned mesh');
  if (!(meshIds instanceof Map)) fail('GLTFLoader node/primitive association map required');
  const names = visible.map(mesh => meshIds.get(mesh));
  if (names.some(name => !/^node:\d+\/primitive:\d+$/.test(name ?? ''))
      || new Set(names).size !== names.length) fail('unique GLB primitive identities required');
  if (clips.some(clip => !clip.name) || new Set(clips.map(clip => clip.name)).size !== clips.length) {
    fail('unique clip names required');
  }
  const rest = nodes.map(transforms);
  if (rest.some(value => !finite(value))) fail('non-finite initial transform');
  controller.stop();
  update(root, skinned);
  const meshBuffers = {meshes: visible.map(mesh => buffers(mesh, meshIds.get(mesh)))
    .sort((a, b) => a.name.localeCompare(b.name, 'en', {numeric: true}))};
  const sampled = {}, deformation = {};
  for (const mesh of skinned) deformation[meshIds.get(mesh)] = {frames: 0, verticesPerFrame: []};
  let maxDelta = 0, restoreDelta = 0, nonFiniteCount = 0;
  const vertex = new Vector3();
  let restoreVertexDelta = 0;
  const restVertices = new Map();
  for (const mesh of skinned) {
    const position = mesh.geometry.getAttribute('position');
    const values = new Float64Array(position.count * 3);
    for (let i = 0; i < position.count; i++) {
      vertex.fromBufferAttribute(position, i);
      mesh.applyBoneTransform(i, vertex);
      if (!finiteVector(vertex)) fail('non-finite initial bind deformation');
      values[i * 3] = vertex.x;
      values[i * 3 + 1] = vertex.y;
      values[i * 3 + 2] = vertex.z;
    }
    restVertices.set(mesh, values);
  }
  try {
    for (const clip of clips) {
      if (!(clip.duration > 0) || !Number.isFinite(clip.duration) || !clip.tracks.length) fail('empty clip');
      const tracks = clip.tracks.map(track => {
        const size = track.getValueSize();
        const binding = PropertyBinding.create(root, track.name);
        binding.bind();
        return {binding, interpolant: track.createInterpolant(), actual: new Array(size), size};
      });
      const times = [];
      let clipDelta = 0;
      try {
        for (let i = 0; i < sampleCount; i++) {
          const time = clip.duration * i / (sampleCount - 1);
          times.push(time);
          controller.seek(clip.name, time);
          update(root, skinned);
          for (const track of tracks) {
            track.actual.fill(NaN);
            track.binding.getValue(track.actual, 0);
            const expected = track.interpolant.evaluate(time);
            if (!finite(track.actual) || !finite(Array.from(expected))) fail('unresolved/non-finite track binding');
            for (let j = 0; j < track.size; j++) clipDelta = Math.max(clipDelta, Math.abs(track.actual[j] - expected[j]));
          }
          for (const mesh of skinned) {
            const position = mesh.geometry.getAttribute('position');
            const count = position.count; // All DISTINCT vertices, never duplicate a tiny mesh to reach 64.
            for (let j = 0; j < count; j++) {
              vertex.fromBufferAttribute(position, j);
              mesh.applyBoneTransform(j, vertex);
              if (!finiteVector(vertex)) nonFiniteCount++;
            }
            deformation[meshIds.get(mesh)].frames++;
            deformation[meshIds.get(mesh)].verticesPerFrame.push(count);
          }
        }
        controller.stop();
        update(root, skinned);
        for (let i = 0; i < nodes.length; i++) {
          const actual = transforms(nodes[i]);
          if (!finite(actual)) fail('non-finite restored transform');
          for (let j = 0; j < actual.length; j++) restoreDelta = Math.max(restoreDelta, Math.abs(actual[j] - rest[i][j]));
        }
        for (const mesh of skinned) {
          const position = mesh.geometry.getAttribute('position'), expected = restVertices.get(mesh);
          for (let i = 0; i < position.count; i++) {
            vertex.fromBufferAttribute(position, i);
            mesh.applyBoneTransform(i, vertex);
            if (!finiteVector(vertex)) fail('non-finite restored bind deformation');
            restoreVertexDelta = Math.max(restoreVertexDelta, Math.abs(vertex.x - expected[i * 3]),
              Math.abs(vertex.y - expected[i * 3 + 1]), Math.abs(vertex.z - expected[i * 3 + 2]));
          }
        }
      } finally {
        for (const track of tracks) track.binding.unbind();
      }
      maxDelta = Math.max(maxDelta, clipDelta);
      sampled[clip.name] = {sampleCount: times.length, sampleTimes: times, maxSampledBindingDelta: clipDelta};
    }
  } finally {
    controller.stop();
    update(root, skinned);
  }
  return {
    kind: 'img2.character-runtime-measurements', version: 1, glbSha256,
    producer: 'character/runtime/rig-measurements.mjs', meshBuffers,
    measurements: {
      bindingSamples: {maxSampledBindingDelta: maxDelta, clips: sampled},
      deformation: {nonFiniteCount, allFinite: nonFiniteCount === 0, meshes: deformation},
      bindRestore: {maxBindRestoreDelta: restoreDelta, maxBindRestoreVertexDelta: restoreVertexDelta,
        meshes: Object.fromEntries(skinned.map(mesh => [meshIds.get(mesh), {vertexCount: mesh.geometry.getAttribute('position').count}]))},
      meshVisibility: {
        visibleMeshCount: visible.length, visibleSkinnedMeshCount: skinned.length,
        unboundMeshes: visible.filter(mesh => !mesh.isSkinnedMesh).map(mesh => meshIds.get(mesh)),
      },
    },
  };
}
