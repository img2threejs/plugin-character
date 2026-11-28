// SPDX-License-Identifier: Apache-2.0
// Circular surface-support fields. Dimensions and region selection belong to the input.
import { BufferAttribute, Matrix4, Vector3 } from 'three';

import { validateRoundCalibration } from './calibration.mjs';

const smooth = (t) => { const c = Math.max(0, Math.min(1, t)); return c * c * (3 - 2 * c); };

/** Weight for a vertex at straight distance `distance` (m) from the apex. */
export function roundChestWeight(distance, plateau, reach) {
  if (!(Number.isFinite(distance) && Number.isFinite(plateau) && Number.isFinite(reach) && reach > plateau && plateau >= 0)) throw new Error('roundChestWeight: explicit finite interval required');
  return 1 - smooth((distance - plateau) / (reach - plateau));
}

function attributeByName(geometry, name) {
  return geometry.getAttribute(name) ?? geometry.getAttribute(name.toLowerCase());
}

/**
 * Adds `<attribute>_ROUND` scalar attributes to the sidecar meshes' geometries and returns
 * { sidecar, original, apex }: a patched copy of the sidecar that points the chest
 * regions at the round masks, the original per-mesh mask arrays, and the apex per region.
 * The asset's forward axis (+Z in the shared first-mesh frame) locates the apex as the
 * front-most vertex among those the author painted at weight >= 0.3.
 */
export function roundChestMasks(root, sidecar, options) {
  const { plateau, reach, wallDepth, wallFade, midline, midlineFade, regions, suffix } = validateRoundCalibration(options);
  root.updateWorldMatrix(true, false); root.updateMatrixWorld(true);
  const patched = JSON.parse(JSON.stringify(sidecar));
  const specs = patched.meshes.map((spec) => {
    const found = [];
    root.traverse((object) => { if (object.name === spec.name) found.push(object); });
    if (found.length !== 1 || !found[0].isMesh) throw new Error(`roundChestMasks: mesh ${spec.name} must resolve to exactly one Mesh`);
    return { spec, mesh: found[0] };
  });
  const referenceInverse = specs[0].mesh.matrixWorld.clone().invert();
  const toShared = (mesh) => new Matrix4().multiplyMatrices(referenceInverse, mesh.matrixWorld);
  const original = {}, apexes = {}, weights = new Map(), p = new Vector3();

  for (const id of regions) {
    const owners = specs.filter(({ spec }) => spec.regions.some((r) => r.id === id));
    if (!owners.length) continue;
    // Apex from the first owner (the skin) so the garment layered on top does not shift it.
    const { spec: firstSpec, mesh: firstMesh } = owners[0];
    const firstItem = firstSpec.regions.find((r) => r.id === id);
    const painted = attributeByName(firstMesh.geometry, firstItem.attribute);
    if (!painted) throw new Error(`roundChestMasks: ${firstSpec.name} has no ${firstItem.attribute}`);
    const firstPosition = firstMesh.geometry.getAttribute('position'), firstMatrix = toShared(firstMesh);
    let apex = null;
    for (let i = 0; i < painted.count; i++) {
      if (painted.getX(i) < 0.3) continue;
      p.fromBufferAttribute(firstPosition, i).applyMatrix4(firstMatrix);
      if (!apex || p.z > apex.z) apex = p.clone();
    }
    if (!apex) throw new Error(`roundChestMasks: no painted vertex for ${id}`);
    apexes[id] = apex;
    for (const { spec, mesh } of owners) {
      const item = spec.regions.find((r) => r.id === id);
      const source = attributeByName(mesh.geometry, item.attribute);
      if (!source) throw new Error(`roundChestMasks: ${spec.name} has no ${item.attribute}`);
      const position = mesh.geometry.getAttribute('position'), matrix = toShared(mesh);
      const values = new Float32Array(position.count), copy = new Float32Array(source.count);
      for (let i = 0; i < position.count; i++) {
        copy[i] = source.getX(i);
        p.fromBufferAttribute(position, i).applyMatrix4(matrix);
        const behind = apex.z - p.z;
        const medial = smooth((Math.abs(p.x) - midline) / midlineFade);
        values[i] = roundChestWeight(Math.hypot(p.x - apex.x, p.y - apex.y), plateau, reach) * (1 - smooth((behind - wallDepth) / wallFade)) * medial;
      }
      (original[spec.name] ??= {})[id] = copy;
      weights.set(`${spec.name}|${id}`, { mesh, item, values });
    }
  }
  // Where both breasts' supports overlap at the cleavage, share the weight instead of
  // letting two regions each move the same vertex at full strength.
  const byMesh = new Map();
  for (const [key, entry] of weights) {
    const name = key.split('|')[0];
    (byMesh.get(name) ?? byMesh.set(name, []).get(name)).push(entry);
  }
  for (const list of byMesh.values()) {
    if (list.length < 2) continue;
    const n = list[0].values.length;
    for (let i = 0; i < n; i++) {
      let sum = 0; for (const e of list) sum += e.values[i];
      if (sum > 1) for (const e of list) e.values[i] /= sum;
    }
  }
  for (const { mesh, item, values } of weights.values()) {
    const name = item.attribute + suffix;
    mesh.geometry.setAttribute(name, new BufferAttribute(values, 1));
    item.attribute = name;
  }
  return { sidecar: patched, original, apex: apexes };
}
