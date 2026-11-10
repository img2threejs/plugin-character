// Soft-body interaction layer for skinned/morphed GLB meshes.
//
// A SoftBody splits a source mesh into a static complement (kept on the source
// mesh) and a dynamic child mesh holding every triangle touched by a region
// mask. The dynamic mesh shares the source materials, skeleton and live morph
// influences, so skinning and morphs keep working while its rest-space base
// positions are deformed on the CPU (size springs, jiggle, press/shear).
//
// Coordinates: every deformation is expressed in the loaded mesh's local,
// pre-skin ("rest") space. Raycast hits are posed (skin + morph) world
// positions; they are mapped back through the barycentric coordinates of the
// hit triangle, never through a naive worldToLocal of the rest mesh.

import {
  BufferAttribute,
  BufferGeometry,
  DynamicDrawUsage,
  Matrix4,
  Mesh,
  SkinnedMesh,
  Triangle,
  Vector3,
} from 'three';

export const SIZE_MIN = 0.6;
export const SIZE_MAX = 1.5;
const MAX_DT = 0.05;
const MAX_PRESSES = 4;
const MAX_SUBSTEPS = 16;
const MASK_EPS = 1e-6;
const SETTLE_POS = 1e-4;
const SETTLE_VEL = 1e-3;
const SIZE_CLAMP_LO = 0.4;
const SIZE_CLAMP_HI = 1.8;
const SEAM_RAMP = 0.35;

/** Source meshes that currently own a SoftBody. */
const registry = new WeakMap();

function fail(message) {
  return new Error(`SoftBody: ${message}`);
}

function resolveAttribute(geometry, name) {
  if (typeof name !== 'string' || name.length === 0) return null;
  return geometry.getAttribute(name) ?? geometry.getAttribute(name.toLowerCase()) ?? null;
}

function rawView(attribute) {
  if (attribute.isInterleavedBufferAttribute) {
    return { array: attribute.data.array, stride: attribute.data.stride, offset: attribute.offset };
  }
  return { array: attribute.array, stride: attribute.itemSize, offset: 0 };
}

/** Copy the vertices listed in `map` into a new tightly packed BufferAttribute. */
function compactAttribute(attribute, map, toFloat) {
  if (attribute.isGLBufferAttribute) throw fail('GLBufferAttribute is not supported');
  const size = attribute.itemSize;
  const count = map.length;
  let result;
  if (toFloat) {
    const out = new Float32Array(count * size);
    for (let i = 0; i < count; i++) {
      const s = map[i];
      for (let k = 0; k < size; k++) out[i * size + k] = attribute.getComponent(s, k);
    }
    result = new BufferAttribute(out, size, false);
  } else {
    const { array, stride, offset } = rawView(attribute);
    const out = new array.constructor(count * size);
    for (let i = 0; i < count; i++) {
      const base = map[i] * stride + offset;
      for (let k = 0; k < size; k++) out[i * size + k] = array[base + k];
    }
    result = new BufferAttribute(out, size, attribute.normalized);
  }
  if (attribute.gpuType !== undefined) result.gpuType = attribute.gpuType;
  result.name = attribute.name;
  return result;
}

function readMask(geometry, name, vertexCount, label) {
  const attribute = resolveAttribute(geometry, name);
  if (!attribute) return null;
  if (attribute.isGLBufferAttribute) throw fail(`${label} attribute "${name}" is not a CPU attribute`);
  if (attribute.itemSize !== 1) throw fail(`${label} attribute "${name}" must be scalar (itemSize 1)`);
  if (attribute.count !== vertexCount) {
    throw fail(`${label} attribute "${name}" has ${attribute.count} values for ${vertexCount} vertices`);
  }
  const out = new Float32Array(vertexCount);
  for (let i = 0; i < vertexCount; i++) {
    const v = attribute.getX(i);
    if (!Number.isFinite(v) || v < -MASK_EPS || v > 1 + MASK_EPS) {
      throw fail(`${label} attribute "${name}" value ${v} at vertex ${i} is outside [0,1]`);
    }
    out[i] = v < 0 ? 0 : v > 1 ? 1 : v;
  }
  return out;
}

function toTriple(value, label) {
  let x;
  let y;
  let z;
  if (Array.isArray(value) && value.length === 3) [x, y, z] = value;
  else if (value && value.isVector3) ({ x, y, z } = value);
  else throw fail(`${label} must be [x,y,z]`);
  if (![x, y, z].every((n) => typeof n === 'number' && Number.isFinite(n))) {
    throw fail(`${label} must contain finite numbers`);
  }
  return [x, y, z];
}

function smoothstep01(t) {
  const c = t < 0 ? 0 : t > 1 ? 1 : t;
  return c * c * (3 - 2 * c);
}

// First boundary on the entire rest-to-candidate path, not just its endpoint.
// c is positive at rest. Stable roots also catch collapse followed by recovery.
function firstBoundary(a, b, c) {
  if (a === 0) return b < 0 ? -c / b : Infinity;
  const discriminant = b * b - 4 * a * c;
  if (discriminant < 0) return Infinity;
  const q = -0.5 * (b + (b < 0 ? -1 : 1) * Math.sqrt(discriminant));
  const r1 = q / a;
  const r2 = q === 0 ? Infinity : c / q;
  return Math.min(r1 > 0 ? r1 : Infinity, r2 > 0 ? r2 : Infinity);
}

function edgeBoundary(x, y, z, dx, dy, dz, length2) {
  if (length2 === 0) return Infinity; // An authored zero edge cannot be repaired here.
  const a = dx * dx + dy * dy + dz * dz;
  const b = 2 * (x * dx + y * dy + z * dz);
  // Keep lengths within 40%..180% of rest, independently of triangle rotation.
  return Math.min(
    firstBoundary(a, b, 0.84 * length2),
    firstBoundary(-a, -b, 2.24 * length2),
  );
}

// UV/export splits must not split a smooth normal field. Authored hard edges,
// different skin/morph data and different deformation masks remain separate.
function normalWeld(geometry, rest, normals, masks, hair, compact) {
  const attributes = ['skinIndex', 'skinWeight'].map((name) => geometry.getAttribute(name)).filter(Boolean);
  for (const list of Object.values(geometry.morphAttributes)) attributes.push(...list);
  const groups = new Map();
  const weld = new Uint32Array(compact.length);
  for (let i = 0; i < compact.length; i++) {
    const k = i * 3, source = compact[i];
    let key = `${rest[k]},${rest[k + 1]},${rest[k + 2]}|${normals[k]},${normals[k + 1]},${normals[k + 2]}`;
    for (const mask of masks) key += `|${mask[source]}`;
    key += `|${hair ? hair[source] : 0}`;
    for (const attribute of attributes) {
      for (let c = 0; c < attribute.itemSize; c++) key += `|${attribute.getComponent(i, c)}`;
    }
    const existing = groups.get(key);
    weld[i] = existing === undefined ? i : existing;
    if (existing === undefined) groups.set(key, i);
  }
  return weld;
}

export class SoftBody {
  /**
   * @param {Mesh} sourceMesh Mesh or SkinnedMesh (unique owner of its geometry swap).
   * @param {Array} regions {id, group?, attribute, bone?, center?, radius?}
   * @param {{hairAttribute?: string, substeps?: number}} options
   */
  constructor(sourceMesh, regions, options = {}) {
    const { hairAttribute = '_HAIR', substeps = 4 } = options;
    if (!sourceMesh || !sourceMesh.isMesh || sourceMesh.isInstancedMesh || sourceMesh.isBatchedMesh) {
      throw fail('sourceMesh must be a Mesh or SkinnedMesh (instanced/batched meshes are unsupported)');
    }
    if (registry.has(sourceMesh)) throw fail('sourceMesh already has an active SoftBody');
    if (!Number.isInteger(substeps) || substeps < 1 || substeps > MAX_SUBSTEPS) {
      throw fail(`substeps must be an integer in [1,${MAX_SUBSTEPS}]`);
    }
    if (!Array.isArray(regions) || regions.length === 0) throw fail('regions must be a non-empty array');

    const geometry = sourceMesh.geometry;
    if (!geometry || !geometry.isBufferGeometry) throw fail('sourceMesh has no BufferGeometry');
    const positionAttribute = geometry.getAttribute('position');
    if (!positionAttribute || positionAttribute.isGLBufferAttribute || positionAttribute.itemSize !== 3) {
      throw fail('geometry needs a CPU position attribute with itemSize 3');
    }
    const vertexCount = positionAttribute.count;
    const skinned = Boolean(sourceMesh.isSkinnedMesh);
    if (skinned) {
      if (!sourceMesh.skeleton) throw fail('SkinnedMesh has no skeleton bound');
      if (!geometry.getAttribute('skinIndex') || !geometry.getAttribute('skinWeight')) {
        throw fail('SkinnedMesh geometry lacks skinIndex/skinWeight');
      }
    }

    // ---- topology -------------------------------------------------------
    const indexAttribute = geometry.index;
    const corners = indexAttribute ? indexAttribute.count : vertexCount;
    if (corners % 3 !== 0) throw fail('triangle list length is not a multiple of 3');
    const drawRange = geometry.drawRange;
    if (drawRange.start !== 0 || (Number.isFinite(drawRange.count) && drawRange.count < corners)) {
      throw fail('geometry.drawRange restricting the draw is unsupported');
    }
    const triCount = corners / 3;
    const cornerIndex = new Uint32Array(corners);
    for (let i = 0; i < corners; i++) {
      const v = indexAttribute ? indexAttribute.getX(i) : i;
      if (!(v >= 0 && v < vertexCount)) throw fail(`index ${v} out of range`);
      cornerIndex[i] = v;
    }
    const triGroup = new Int32Array(triCount).fill(-1);
    const grouped = geometry.groups.length > 0;
    const groupList = [];
    if (grouped) {
      for (let g = 0; g < geometry.groups.length; g++) {
        const group = geometry.groups[g];
        const start = group.start;
        const count = Math.min(group.count, corners - start);
        if (!Number.isInteger(start) || start < 0 || start % 3 !== 0 || !Number.isInteger(count) || count < 0 || count % 3 !== 0) {
          throw fail(`geometry group ${g} is not triangle aligned`);
        }
        for (let t = start / 3; t < (start + count) / 3; t++) {
          if (triGroup[t] !== -1) throw fail(`geometry group ${g} overlaps another group`);
          triGroup[t] = g;
        }
        groupList.push({ start, count, materialIndex: group.materialIndex });
      }
    } else {
      triGroup.fill(0);
      groupList.push({ start: 0, count: corners, materialIndex: undefined });
    }

    // ---- masks ----------------------------------------------------------
    const seenIds = new Set();
    const masks = [];
    const total = new Float32Array(vertexCount);
    for (let r = 0; r < regions.length; r++) {
      const region = regions[r];
      if (!region || typeof region !== 'object') throw fail(`region ${r} must be an object`);
      if (typeof region.id !== 'string' || region.id.length === 0) throw fail(`region ${r} needs a non-empty string id`);
      if (seenIds.has(region.id)) throw fail(`duplicate region id "${region.id}"`);
      seenIds.add(region.id);
      if (region.group !== undefined && typeof region.group !== 'string') throw fail(`region "${region.id}" group must be a string`);
      if (region.bone !== undefined) {
        if (typeof region.bone !== 'string' || region.bone.length === 0) throw fail(`region "${region.id}" bone must be a string`);
        if (!skinned || !sourceMesh.skeleton.bones.some((bone) => bone.name === region.bone || bone.userData?.name === region.bone)) {
          throw fail(`region "${region.id}" bone "${region.bone}" is not a joint of the mesh skeleton`);
        }
      }
      const mask = readMask(geometry, region.attribute, vertexCount, `region "${region.id}"`);
      if (!mask) throw fail(`region "${region.id}" attribute "${region.attribute}" not found on geometry`);
      let any = false;
      for (let i = 0; i < vertexCount; i++) {
        if (mask[i] > 0) {
          any = true;
          total[i] += mask[i];
        }
      }
      if (!any) throw fail(`region "${region.id}" has zero influence`);
      masks.push(mask);
    }
    const hair = hairAttribute ? readMask(geometry, hairAttribute, vertexCount, 'hair') : null;
    if (options.hairAttribute !== undefined && !hair) {
      throw fail(`declared hair attribute "${hairAttribute}" not found on geometry`);
    }

    // ---- partition ------------------------------------------------------
    const triDynamic = new Uint8Array(triCount);
    let dynTris = 0;
    let staticTris = 0;
    for (let t = 0; t < triCount; t++) {
      if (triGroup[t] < 0) continue;
      const o = t * 3;
      if (total[cornerIndex[o]] > 0 || total[cornerIndex[o + 1]] > 0 || total[cornerIndex[o + 2]] > 0) {
        triDynamic[t] = 1;
        dynTris++;
      } else staticTris++;
    }
    if (dynTris === 0) throw fail('no rendered triangle is influenced by any region');

    const dynCorners = new Uint32Array(dynTris * 3);
    const staticCorners = new Uint32Array(staticTris * 3);
    const dynGroups = [];
    const staticGroups = [];
    const remap = new Int32Array(vertexCount).fill(-1);
    const compactSource = new Uint32Array(Math.min(vertexCount, dynTris * 3));
    let dn = 0;
    let sn = 0;
    let compactCount = 0;
    for (const group of groupList) {
      const dStart = dn;
      const sStart = sn;
      for (let t = group.start / 3; t < (group.start + group.count) / 3; t++) {
        const o = t * 3;
        if (triDynamic[t]) {
          for (let k = 0; k < 3; k++) {
            const v = cornerIndex[o + k];
            if (remap[v] < 0) {
              remap[v] = compactCount;
              compactSource[compactCount++] = v;
            }
            dynCorners[dn++] = remap[v];
          }
        } else if (triGroup[t] >= 0) {
          for (let k = 0; k < 3; k++) staticCorners[sn++] = cornerIndex[o + k];
        }
      }
      if (dn > dStart) dynGroups.push({ start: dStart, count: dn - dStart, materialIndex: group.materialIndex });
      if (sn > sStart) staticGroups.push({ start: sStart, count: sn - sStart, materialIndex: group.materialIndex });
    }
    const compact = compactSource.slice(0, compactCount);
    const m = compactCount;

    // ---- geometries -----------------------------------------------------
    const dynamicGeometry = new BufferGeometry();
    dynamicGeometry.name = `${geometry.name || 'geometry'}:softbody`;
    for (const name of Object.keys(geometry.attributes)) {
      const toFloat = name === 'position' || name === 'normal';
      const attribute = compactAttribute(geometry.attributes[name], compact, toFloat);
      if (toFloat) attribute.setUsage(DynamicDrawUsage);
      dynamicGeometry.setAttribute(name, attribute);
    }
    for (const key of Object.keys(geometry.morphAttributes)) {
      const toFloat = key === 'position' || key === 'normal';
      dynamicGeometry.morphAttributes[key] = geometry.morphAttributes[key].map((a) => {
        const out = compactAttribute(a, compact, toFloat);
        return out;
      });
    }
    dynamicGeometry.morphTargetsRelative = geometry.morphTargetsRelative;
    dynamicGeometry.setIndex(new BufferAttribute(m > 65535 ? dynCorners : Uint16Array.from(dynCorners), 1));
    for (const g of dynGroups) dynamicGeometry.addGroup(g.start, g.count, g.materialIndex);

    const staticGeometry = new BufferGeometry();
    staticGeometry.name = `${geometry.name || 'geometry'}:static`;
    for (const name of Object.keys(geometry.attributes)) staticGeometry.setAttribute(name, geometry.attributes[name]);
    for (const key of Object.keys(geometry.morphAttributes)) staticGeometry.morphAttributes[key] = geometry.morphAttributes[key].slice();
    staticGeometry.morphTargetsRelative = geometry.morphTargetsRelative;
    staticGeometry.setIndex(
      new BufferAttribute(vertexCount > 65535 ? staticCorners : Uint16Array.from(staticCorners), 1),
    );
    for (const g of staticGroups) staticGeometry.addGroup(g.start, g.count, g.materialIndex);

    // ---- runtime buffers ------------------------------------------------
    const positionOut = dynamicGeometry.getAttribute('position');
    const normalOut = dynamicGeometry.getAttribute('normal') ?? null;
    const rest = Float32Array.from(positionOut.array);
    for (let i = 0; i < rest.length; i++) {
      if (!Number.isFinite(rest[i])) throw fail('non-finite rest position');
    }
    const restNormal = normalOut ? Float32Array.from(normalOut.array) : null;
    const accumulator = normalOut ? new Float32Array(m * 3) : null;
    const restFaceNormal = normalOut ? new Float32Array(m * 3) : null;
    const weld = restNormal ? normalWeld(dynamicGeometry, rest, restNormal, masks, hair, compact) : null;
    // Cache rest topology once; the per-frame projection allocates nothing.
    const topology = new Float64Array(dynTris * 13);
    for (let t = 0; t < dynTris; t++) {
      const a = dynCorners[t * 3] * 3;
      const b = dynCorners[t * 3 + 1] * 3;
      const c = dynCorners[t * 3 + 2] * 3;
      const o = t * 13;
      const x = rest[b] - rest[a], y = rest[b + 1] - rest[a + 1], z = rest[b + 2] - rest[a + 2];
      const u = rest[c] - rest[a], v = rest[c + 1] - rest[a + 1], w = rest[c + 2] - rest[a + 2];
      const nx = y * w - z * v, ny = z * u - x * w, nz = x * v - y * u;
      topology.set([x, y, z, u, v, w, nx, ny, nz,
        nx * nx + ny * ny + nz * nz,
        x * x + y * y + z * z, u * u + v * v + w * w,
        (u - x) ** 2 + (v - y) ** 2 + (w - z) ** 2], o);
    }
    const seam = new Float32Array(m);
    for (let i = 0; i < m; i++) seam[i] = smoothstep01(Math.min(1, total[compact[i]]) / SEAM_RAMP);

    // ---- regions --------------------------------------------------------
    const regionStates = [];
    const regionById = new Map();
    for (let r = 0; r < regions.length; r++) {
      const input = regions[r];
      const mask = masks[r];
      let n = 0;
      for (let i = 0; i < m; i++) if (mask[compact[i]] > 0) n++;
      if (n === 0) throw fail(`region "${input.id}" influences no rendered vertex`);
      const idx = new Uint32Array(n);
      const weight = new Float32Array(n);
      const hairWeight = new Float32Array(n);
      let j = 0;
      for (let i = 0; i < m; i++) {
        const s = compact[i];
        const w = mask[s];
        if (w <= 0) continue;
        idx[j] = i;
        weight[j] = total[s] > 1 ? w / total[s] : w;
        hairWeight[j] = hair ? hair[s] : 0;
        j++;
      }
      let center = input.center === undefined ? null : toTriple(input.center, `region "${input.id}" center`);
      let radius = input.radius === undefined ? null : input.radius;
      if (radius !== null && !(typeof radius === 'number' && Number.isFinite(radius) && radius > 0)) {
        throw fail(`region "${input.id}" radius must be a positive finite number`);
      }
      if (center === null || radius === null) {
        let sw = 0;
        let cx = 0;
        let cy = 0;
        let cz = 0;
        for (let q = 0; q < n; q++) {
          const cw = mask[compact[idx[q]]] * (1 - hairWeight[q]);
          if (cw <= 0) continue;
          const i3 = idx[q] * 3;
          sw += cw;
          cx += cw * rest[i3];
          cy += cw * rest[i3 + 1];
          cz += cw * rest[i3 + 2];
        }
        if (sw <= 0) {
          throw fail(`region "${input.id}" covers only hair; explicit center and radius are required`);
        }
        const derived = [cx / sw, cy / sw, cz / sw];
        if (center === null) center = derived;
        if (radius === null) {
          let r2 = 0;
          for (let q = 0; q < n; q++) {
            if (mask[compact[idx[q]]] * (1 - hairWeight[q]) <= 0) continue;
            const i3 = idx[q] * 3;
            const dx = rest[i3] - center[0];
            const dy = rest[i3 + 1] - center[1];
            const dz = rest[i3 + 2] - center[2];
            const d2 = dx * dx + dy * dy + dz * dz;
            if (d2 > r2) r2 = d2;
          }
          radius = Math.sqrt(r2);
          if (!(radius > 0)) throw fail(`region "${input.id}" has degenerate support (zero radius)`);
        }
      }
      const state = {
        id: input.id,
        group: input.group,
        bone: input.bone,
        attribute: input.attribute,
        cx: center[0],
        cy: center[1],
        cz: center[2],
        radius,
        idx,
        w: weight,
        hair: hairWeight,
        size: 1,
        sizeVel: 0,
        sizeTarget: 1,
        ox: 0,
        oy: 0,
        oz: 0,
        ovx: 0,
        ovy: 0,
        ovz: 0,
      };
      regionStates.push(state);
      regionById.set(state.id, state);
    }

    // ---- commit (nothing below can throw) ---------------------------------
    this.sourceMesh = sourceMesh;
    this._originalGeometry = geometry;
    this._staticGeometry = staticGeometry;
    this._dynamicGeometry = dynamicGeometry;
    this._substeps = substeps;
    this._m = m;
    this._triCount = dynTris;
    this._dynIndex = dynamicGeometry.index.array;
    this._rest = rest;
    this._topology = topology;
    this._restNormal = restNormal;
    this._normalWeld = weld;
    this._pos = positionOut.array;
    this._posAttr = positionOut;
    this._nrm = normalOut ? normalOut.array : null;
    this._nrmAttr = normalOut;
    this._acc = accumulator;
    this._restFace = restFaceNormal;
    this._seam = seam;
    this._regions = regionStates;
    this._regionById = regionById;
    this._presses = [];
    for (let i = 0; i < MAX_PRESSES; i++) {
      this._presses.push({
        active: false, held: false, token: 0, region: 0,
        ax: 0, ay: 0, az: 0, nx: 0, ny: 0, nz: 1,
        radius: 1, shearMax: 0,
        a: 0, va: 0, sx: 0, sy: 0, sz: 0, vsx: 0, vsy: 0, vsz: 0, tx: 0, ty: 0, tz: 0,
      });
    }
    this._tokenSeq = 0;
    this._softness = 0.5;
    this._k = 0;
    this._c = 0;
    this._gain = 1;
    this._dirty = false;
    this._disposed = false;
    this._hit = { region: 0, ax: 0, ay: 0, az: 0, nx: 0, ny: 0, nz: 1 };
    this._va = new Vector3();
    this._vb = new Vector3();
    this._vc = new Vector3();
    this._lp = new Vector3();
    this._bary = new Vector3();
    this._inv = new Matrix4();
    this.setSoftness(0.5);

    if (restNormal) {
      this._accumulate(rest, restFaceNormal);
      this._normalizeInPlace(restFaceNormal);
    }

    const dynamicMesh = skinned
      ? new SkinnedMesh(dynamicGeometry, sourceMesh.material)
      : new Mesh(dynamicGeometry, sourceMesh.material);
    dynamicMesh.name = `${sourceMesh.name || 'mesh'}:softbody`;
    dynamicMesh.matrixAutoUpdate = false;
    // SkinnedMesh caches its bounding sphere and three only refreshes it when
    // asked; recomputing it from the pose every frame is O(vertices). A stale
    // rest-pose bound would cull the region once bones move, so the (small)
    // dynamic mesh is always submitted. The source mesh keeps its own setting.
    dynamicMesh.frustumCulled = false;
    dynamicMesh.castShadow = sourceMesh.castShadow;
    dynamicMesh.receiveShadow = sourceMesh.receiveShadow;
    dynamicMesh.renderOrder = sourceMesh.renderOrder;
    dynamicMesh.layers.mask = sourceMesh.layers.mask;
    dynamicMesh.customDepthMaterial = sourceMesh.customDepthMaterial;
    dynamicMesh.customDistanceMaterial = sourceMesh.customDistanceMaterial;
    if (sourceMesh.morphTargetInfluences) {
      dynamicMesh.morphTargetInfluences = sourceMesh.morphTargetInfluences;
      dynamicMesh.morphTargetDictionary = sourceMesh.morphTargetDictionary;
    }
    if (skinned) {
      dynamicMesh.bindMode = sourceMesh.bindMode;
      dynamicMesh.bind(sourceMesh.skeleton, sourceMesh.bindMatrix);
      const skinnedRaycast = SkinnedMesh.prototype.raycast;
      // Bounds are cached by SkinnedMesh; they must follow pose and deformation.
      dynamicMesh.raycast = function raycastPosed(raycaster, intersects) {
        this.boundingSphere = null;
        this.boundingBox = null;
        this.computeBoundingSphere();
        this.computeBoundingBox();
        skinnedRaycast.call(this, raycaster, intersects);
      };
    }
    this.dynamicMesh = dynamicMesh;

    sourceMesh.geometry = staticGeometry;
    if (skinned) {
      sourceMesh.boundingSphere = null;
      sourceMesh.boundingBox = null;
    }
    sourceMesh.add(dynamicMesh);
    registry.set(sourceMesh, this);
  }

  // ---- inspection --------------------------------------------------------

  get disposed() {
    return this._disposed;
  }

  get softness() {
    return this._softness;
  }

  get activePressCount() {
    let n = 0;
    for (const p of this._presses) if (p.active) n++;
    return n;
  }

  /** Plain, immutable description of each region (rest/mesh-local space). */
  get regions() {
    return this._regions.map((r) =>
      Object.freeze({
        id: r.id,
        group: r.group,
        bone: r.bone,
        center: [r.cx, r.cy, r.cz],
        radius: r.radius,
      }),
    );
  }

  getSize(id) {
    return this._region(id).size;
  }

  getTargetSize(id) {
    return this._region(id).sizeTarget;
  }

  // ---- controls ----------------------------------------------------------

  setSize(id, value) {
    this._assertLive();
    const region = this._region(id);
    if (typeof value !== 'number' || !Number.isFinite(value) || value < SIZE_MIN || value > SIZE_MAX) {
      throw new RangeError(`SoftBody: size must be a finite number in [${SIZE_MIN},${SIZE_MAX}]`);
    }
    region.sizeTarget = value;
  }

  setSoftness(value) {
    this._assertLive?.();
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1) {
      throw new RangeError('SoftBody: softness must be a finite number in [0,1]');
    }
    this._softness = value;
    this._k = 320 + (90 - 320) * value;
    const zeta = 0.85 + (0.3 - 0.85) * value;
    this._c = 2 * zeta * Math.sqrt(this._k);
    this._gain = 0.5 + 1.1 * value;
    this._dirty = true;
  }

  impulse(id, vector) {
    this._assertLive();
    const region = this._region(id);
    if (!vector || !vector.isVector3 || !Number.isFinite(vector.x + vector.y + vector.z)) {
      throw new TypeError('SoftBody: impulse needs a finite THREE.Vector3');
    }
    region.ovx += vector.x;
    region.ovy += vector.y;
    region.ovz += vector.z;
    this._dirty = true;
  }

  reset() {
    this._assertLive();
    for (const r of this._regions) {
      r.size = 1;
      r.sizeVel = 0;
      r.sizeTarget = 1;
      r.ox = r.oy = r.oz = 0;
      r.ovx = r.ovy = r.ovz = 0;
    }
    for (const p of this._presses) {
      p.active = false;
      p.held = false;
    }
    this._dirty = false;
    this._writeNeutral();
  }

  // ---- press / drag / release -------------------------------------------

  press(intersection) {
    this._assertLive();
    let slot = null;
    for (const p of this._presses) {
      if (!p.active) {
        slot = p;
        break;
      }
    }
    if (!slot) throw new RangeError(`SoftBody: at most ${MAX_PRESSES} concurrent presses`);
    const hit = this._mapHit(intersection);
    const region = this._regions[hit.region];
    slot.active = true;
    slot.held = true;
    slot.token = ++this._tokenSeq;
    slot.region = hit.region;
    slot.ax = hit.ax;
    slot.ay = hit.ay;
    slot.az = hit.az;
    slot.nx = hit.nx;
    slot.ny = hit.ny;
    slot.nz = hit.nz;
    slot.radius = 0.5 * region.radius;
    slot.shearMax = 0.8 * slot.radius;
    slot.a = slot.va = 0;
    slot.sx = slot.sy = slot.sz = 0;
    slot.vsx = slot.vsy = slot.vsz = 0;
    slot.tx = slot.ty = slot.tz = 0;
    this._dirty = true;
    return slot.token;
  }

  move(token, intersection) {
    this._assertLive();
    const slot = this._findPress(token);
    if (!slot || !slot.held) throw new Error('SoftBody: move() needs a held press token');
    const hit = this._mapHit(intersection);
    let dx = hit.ax - slot.ax;
    let dy = hit.ay - slot.ay;
    let dz = hit.az - slot.az;
    const along = dx * slot.nx + dy * slot.ny + dz * slot.nz;
    dx -= along * slot.nx;
    dy -= along * slot.ny;
    dz -= along * slot.nz;
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (len > slot.shearMax) {
      const s = slot.shearMax / len;
      dx *= s;
      dy *= s;
      dz *= s;
    }
    slot.tx = dx;
    slot.ty = dy;
    slot.tz = dz;
    this._dirty = true;
  }

  release(token) {
    this._assertLive();
    const slot = this._findPress(token);
    if (!slot) return false;
    slot.held = false;
    slot.tx = slot.ty = slot.tz = 0;
    this._dirty = true;
    return true;
  }

  // ---- simulation --------------------------------------------------------

  update(dt) {
    this._assertLive();
    if (typeof dt !== 'number' || !Number.isFinite(dt) || dt < 0) {
      throw new RangeError('SoftBody: dt must be a finite, non-negative number');
    }
    const step = dt < MAX_DT ? dt : MAX_DT;
    if (step > 0) {
      const h = step / this._substeps;
      for (let s = 0; s < this._substeps; s++) this._integrate(h);
    }
    if (this._energetic()) {
      this._dirty = true;
      this._apply();
    } else if (this._dirty) {
      this._snap();
      this._apply();
      this._dirty = false;
    }
  }

  dispose() {
    if (this._disposed) return;
    this._disposed = true;
    for (const p of this._presses) {
      p.active = false;
      p.held = false;
    }
    const source = this.sourceMesh;
    this.dynamicMesh.removeFromParent();
    if (source.geometry === this._staticGeometry) source.geometry = this._originalGeometry;
    if (source.isSkinnedMesh) {
      source.boundingSphere = null;
      source.boundingBox = null;
    }
    // Static geometry borrows the original attributes: detach them so
    // dispose() releases only the buffers this controller owns.
    this._staticGeometry.attributes = {};
    this._staticGeometry.morphAttributes = {};
    this._staticGeometry.dispose();
    this._dynamicGeometry.dispose();
    if (registry.get(source) === this) registry.delete(source);
  }

  // ---- internals ---------------------------------------------------------

  _assertLive() {
    if (this._disposed) throw fail('controller is disposed');
  }

  _region(id) {
    const region = this._regionById.get(id);
    if (!region) throw new Error(`SoftBody: unknown region "${String(id)}"`);
    return region;
  }

  _findPress(token) {
    for (const p of this._presses) if (p.active && p.token === token) return p;
    return null;
  }

  _integrate(h) {
    const k = this._k;
    const c = this._c;
    for (let i = 0; i < this._regions.length; i++) {
      const r = this._regions[i];
      r.sizeVel += (-k * (r.size - r.sizeTarget) - c * r.sizeVel) * h;
      r.size += r.sizeVel * h;
      if (r.size < SIZE_CLAMP_LO) {
        r.size = SIZE_CLAMP_LO;
        r.sizeVel = 0;
      } else if (r.size > SIZE_CLAMP_HI) {
        r.size = SIZE_CLAMP_HI;
        r.sizeVel = 0;
      }
      r.ovx += (-k * r.ox - c * r.ovx) * h;
      r.ovy += (-k * r.oy - c * r.ovy) * h;
      r.ovz += (-k * r.oz - c * r.ovz) * h;
      r.ox += r.ovx * h;
      r.oy += r.ovy * h;
      r.oz += r.ovz * h;
      const maxOff = 0.5 * r.radius;
      const len2 = r.ox * r.ox + r.oy * r.oy + r.oz * r.oz;
      if (len2 > maxOff * maxOff) {
        const s = maxOff / Math.sqrt(len2);
        r.ox *= s;
        r.oy *= s;
        r.oz *= s;
      }
    }
    for (let i = 0; i < MAX_PRESSES; i++) {
      const p = this._presses[i];
      if (!p.active) continue;
      const target = p.held ? 1 : 0;
      p.va += (-k * (p.a - target) - c * p.va) * h;
      p.a += p.va * h;
      if (p.a < -1) {
        p.a = -1;
        p.va = 0;
      } else if (p.a > 1.5) {
        p.a = 1.5;
        p.va = 0;
      }
      p.vsx += (-k * (p.sx - p.tx) - c * p.vsx) * h;
      p.vsy += (-k * (p.sy - p.ty) - c * p.vsy) * h;
      p.vsz += (-k * (p.sz - p.tz) - c * p.vsz) * h;
      p.sx += p.vsx * h;
      p.sy += p.vsy * h;
      p.sz += p.vsz * h;
    }
  }

  _energetic() {
    for (let i = 0; i < this._regions.length; i++) {
      const r = this._regions[i];
      if (Math.abs(r.size - r.sizeTarget) > SETTLE_POS || Math.abs(r.sizeVel) > SETTLE_VEL) return true;
      if (Math.abs(r.ox) + Math.abs(r.oy) + Math.abs(r.oz) > SETTLE_POS * r.radius) return true;
      if (Math.abs(r.ovx) + Math.abs(r.ovy) + Math.abs(r.ovz) > SETTLE_VEL * r.radius) return true;
    }
    for (let i = 0; i < MAX_PRESSES; i++) {
      const p = this._presses[i];
      if (!p.active) continue;
      const target = p.held ? 1 : 0;
      const sr = p.radius * SETTLE_POS;
      if (
        Math.abs(p.a - target) > SETTLE_POS || Math.abs(p.va) > SETTLE_VEL ||
        Math.abs(p.sx - p.tx) + Math.abs(p.sy - p.ty) + Math.abs(p.sz - p.tz) > sr ||
        Math.abs(p.vsx) + Math.abs(p.vsy) + Math.abs(p.vsz) > SETTLE_VEL * p.radius
      ) {
        return true;
      }
      if (!p.held) {
        // Released and within tolerance, so it is spent and only a snap remains.
        continue;
      }
    }
    return false;
  }

  _snap() {
    for (let i = 0; i < this._regions.length; i++) {
      const r = this._regions[i];
      r.size = r.sizeTarget;
      r.sizeVel = 0;
      r.ox = r.oy = r.oz = 0;
      r.ovx = r.ovy = r.ovz = 0;
    }
    for (let i = 0; i < MAX_PRESSES; i++) {
      const p = this._presses[i];
      if (!p.active) continue;
      p.va = 0;
      p.vsx = p.vsy = p.vsz = 0;
      p.sx = p.tx;
      p.sy = p.ty;
      p.sz = p.tz;
      if (p.held) p.a = 1;
      else {
        p.a = 0;
        p.active = false;
      }
    }
  }

  _writeNeutral() {
    this._pos.set(this._rest);
    if (this._nrm) this._nrm.set(this._restNormal);
    this._touch();
  }

  _touch() {
    this._posAttr.needsUpdate = true;
    if (this._nrmAttr) this._nrmAttr.needsUpdate = true;
    this._dynamicGeometry.boundingSphere = null;
    this._dynamicGeometry.boundingBox = null;
    if (this.dynamicMesh.isSkinnedMesh) {
      this.dynamicMesh.boundingSphere = null;
      this.dynamicMesh.boundingBox = null;
    }
  }

  _apply() {
    const pos = this._pos;
    const rest = this._rest;
    pos.set(rest);
    let deformed = false;
    for (let ri = 0; ri < this._regions.length; ri++) {
      const r = this._regions[ri];
      const s = r.size;
      const grow = s > 1 ? s : 1;
      const hasSize = s !== 1;
      const hasOff = r.ox !== 0 || r.oy !== 0 || r.oz !== 0;
      if (!hasSize && !hasOff) continue;
      deformed = true;
      const idx = r.idx;
      const wt = r.w;
      const hr = r.hair;
      const cx = r.cx;
      const cy = r.cy;
      const cz = r.cz;
      const ox = r.ox;
      const oy = r.oy;
      const oz = r.oz;
      for (let j = 0; j < idx.length; j++) {
        const i3 = idx[j] * 3;
        const w = wt[j];
        // Hair keeps growing with the body but never shrinks into it.
        const ds = (s + hr[j] * (grow - s) - 1) * w;
        pos[i3] += ds * (rest[i3] - cx) + w * ox;
        pos[i3 + 1] += ds * (rest[i3 + 1] - cy) + w * oy;
        pos[i3 + 2] += ds * (rest[i3 + 2] - cz) + w * oz;
      }
    }
    const gain = this._gain;
    for (let pi = 0; pi < MAX_PRESSES; pi++) {
      const p = this._presses[pi];
      if (!p.active) continue;
      deformed = true;
      const r = this._regions[p.region];
      const idx = r.idx;
      const wt = r.w;
      const R = p.radius;
      const invR = 1 / R;
      const outer2 = 4 * R * R;
      const indent = 0.3 * r.radius * gain * p.a;
      const bulge = 0.25 * indent;
      const nx = p.nx;
      const ny = p.ny;
      const nz = p.nz;
      for (let j = 0; j < idx.length; j++) {
        const i3 = idx[j] * 3;
        const dx = rest[i3] - p.ax;
        const dy = rest[i3 + 1] - p.ay;
        const dz = rest[i3 + 2] - p.az;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 >= outer2) continue;
        const q = Math.sqrt(d2) * invR;
        let along;
        if (q < 1) {
          const t = 1 - q * q;
          along = -indent * t * t;
        } else {
          const sn = Math.sin(Math.PI * (q - 1));
          along = bulge * sn * sn;
        }
        const g = 1 - 0.25 * q * q;
        const shear = g * g * gain;
        const w = wt[j];
        pos[i3] += w * (along * nx + shear * p.sx);
        pos[i3 + 1] += w * (along * ny + shear * p.sy);
        pos[i3 + 2] += w * (along * nz + shear * p.sz);
      }
    }
    if (deformed) this._limitDeformation();
    if (this._nrm) {
      if (deformed) this._updateNormals();
      else this._nrm.set(this._restNormal);
    }
    this._touch();
  }

  /**
   * Project the combined size/contact/jiggle field along one global line.
   * Positive projected area (15% of rest) prevents foldover; edge bounds
   * prevent extreme stretch and collapse. A global scale retains coincident
   * UV vertices and zero-displacement boundaries without welding attributes.
   * This protects rest-space deformation, not arbitrary downstream bone poses.
   */
  _limitDeformation() {
    const p = this._pos, rest = this._rest, idx = this._dynIndex, data = this._topology;
    let limit = 1;
    for (let t = 0; t < idx.length; t += 3) {
      const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
      const o = (t / 3) * 13;
      const x = data[o], y = data[o + 1], z = data[o + 2];
      const u = data[o + 3], v = data[o + 4], w = data[o + 5];
      const dx = p[b] - p[a] - x, dy = p[b + 1] - p[a + 1] - y, dz = p[b + 2] - p[a + 2] - z;
      const du = p[c] - p[a] - u, dv = p[c + 1] - p[a + 1] - v, dw = p[c + 2] - p[a + 2] - w;
      const nx = data[o + 6], ny = data[o + 7], nz = data[o + 8];
      const area2 = data[o + 9];
      if (area2 > 0) {
        const linear = (dy * w - dz * v + y * dw - z * dv) * nx
          + (dz * u - dx * w + z * du - x * dw) * ny
          + (dx * v - dy * u + x * dv - y * du) * nz;
        const quadratic = (dy * dw - dz * dv) * nx
          + (dz * du - dx * dw) * ny + (dx * dv - dy * du) * nz;
        limit = Math.min(limit, firstBoundary(quadratic, linear, 0.85 * area2));
      }
      limit = Math.min(limit,
        edgeBoundary(x, y, z, dx, dy, dz, data[o + 10]),
        edgeBoundary(u, v, w, du, dv, dw, data[o + 11]),
        edgeBoundary(u - x, v - y, w - z, du - dx, dv - dy, dw - dz, data[o + 12]));
    }
    if (limit < 1) {
      // Stay inside the boundary after Float32 storage, not exactly on it.
      limit *= 0.999;
      for (let i = 0; i < p.length; i++) p[i] = rest[i] + limit * (p[i] - rest[i]);
    }
  }

  _accumulate(positions, out) {
    out.fill(0);
    const idx = this._dynIndex;
    for (let t = 0; t < idx.length; t += 3) {
      const a = idx[t] * 3;
      const b = idx[t + 1] * 3;
      const c = idx[t + 2] * 3;
      const e1x = positions[b] - positions[a];
      const e1y = positions[b + 1] - positions[a + 1];
      const e1z = positions[b + 2] - positions[a + 2];
      const e2x = positions[c] - positions[a];
      const e2y = positions[c + 1] - positions[a + 1];
      const e2z = positions[c + 2] - positions[a + 2];
      const nx = e1y * e2z - e1z * e2y;
      const ny = e1z * e2x - e1x * e2z;
      const nz = e1x * e2y - e1y * e2x;
      const wa = this._normalWeld[idx[t]] * 3;
      const wb = this._normalWeld[idx[t + 1]] * 3;
      const wc = this._normalWeld[idx[t + 2]] * 3;
      out[wa] += nx;
      out[wa + 1] += ny;
      out[wa + 2] += nz;
      out[wb] += nx;
      out[wb + 1] += ny;
      out[wb + 2] += nz;
      out[wc] += nx;
      out[wc + 1] += ny;
      out[wc + 2] += nz;
    }
    for (let i = 0; i < this._normalWeld.length; i++) {
      const source = this._normalWeld[i] * 3, target = i * 3;
      if (source === target) continue;
      out[target] = out[source];
      out[target + 1] = out[source + 1];
      out[target + 2] = out[source + 2];
    }
  }

  _normalizeInPlace(array) {
    for (let i = 0; i < array.length; i += 3) {
      const len = Math.sqrt(array[i] * array[i] + array[i + 1] * array[i + 1] + array[i + 2] * array[i + 2]);
      if (len > 1e-20) {
        array[i] /= len;
        array[i + 1] /= len;
        array[i + 2] /= len;
      }
    }
  }

  /**
   * Rest normals are authoritative (hard edges, seams, authored smoothing). The
   * deformation only contributes the *change* in the face-averaged normal,
   * faded in by the region influence so the static boundary keeps its normal.
   */
  _updateNormals() {
    const acc = this._acc;
    this._accumulate(this._pos, acc);
    this._normalizeInPlace(acc);
    const out = this._nrm;
    const rn = this._restNormal;
    const rf = this._restFace;
    for (let v = 0; v < this._m; v++) {
      const i = v * 3;
      const k = this._seam[v];
      const nx = rn[i] + k * (acc[i] - rf[i]);
      const ny = rn[i + 1] + k * (acc[i + 1] - rf[i + 1]);
      const nz = rn[i + 2] + k * (acc[i + 2] - rf[i + 2]);
      const len = Math.sqrt(nx * nx + ny * ny + nz * nz);
      if (len > 1e-12) {
        out[i] = nx / len;
        out[i + 1] = ny / len;
        out[i + 2] = nz / len;
      } else {
        out[i] = rn[i];
        out[i + 1] = rn[i + 1];
        out[i + 2] = rn[i + 2];
      }
    }
  }

  _weightAt(region, vertex) {
    const idx = region.idx;
    let lo = 0;
    let hi = idx.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      const v = idx[mid];
      if (v === vertex) return region.w[mid];
      if (v < vertex) lo = mid + 1;
      else hi = mid - 1;
    }
    return 0;
  }

  /** Map a posed Raycaster hit on the dynamic mesh to a rest-space anchor. */
  _mapHit(hit) {
    const dyn = this.dynamicMesh;
    if (!hit || hit.object !== dyn) throw new Error('SoftBody: intersection does not belong to dynamicMesh');
    const tri = hit.faceIndex;
    if (!Number.isInteger(tri) || tri < 0 || tri >= this._triCount) throw new Error('SoftBody: invalid faceIndex');
    const point = hit.point;
    if (!point || !Number.isFinite(point.x + point.y + point.z)) throw new Error('SoftBody: invalid hit point');
    const idx = this._dynIndex;
    const ia = idx[tri * 3];
    const ib = idx[tri * 3 + 1];
    const ic = idx[tri * 3 + 2];
    if (hit.face && (hit.face.a !== ia || hit.face.b !== ib || hit.face.c !== ic)) {
      throw new Error('SoftBody: intersection face does not match faceIndex');
    }
    // Posed (skinned + morphed) triangle in the mesh's current local frame.
    dyn.getVertexPosition(ia, this._va);
    dyn.getVertexPosition(ib, this._vb);
    dyn.getVertexPosition(ic, this._vc);
    this._inv.copy(dyn.matrixWorld).invert();
    this._lp.copy(point).applyMatrix4(this._inv);
    const bary = Triangle.getBarycoord(this._lp, this._va, this._vb, this._vc, this._bary);
    if (!bary || !Number.isFinite(bary.x + bary.y + bary.z)) throw new Error('SoftBody: degenerate hit triangle');
    let u = bary.x < 0 ? 0 : bary.x;
    let v = bary.y < 0 ? 0 : bary.y;
    let w = bary.z < 0 ? 0 : bary.z;
    const sum = u + v + w;
    if (!(sum > 0)) throw new Error('SoftBody: degenerate barycentric coordinates');
    u /= sum;
    v /= sum;
    w /= sum;

    let best = -1;
    let bestWeight = 1e-6;
    for (let r = 0; r < this._regions.length; r++) {
      const region = this._regions[r];
      const weight =
        u * this._weightAt(region, ia) + v * this._weightAt(region, ib) + w * this._weightAt(region, ic);
      if (weight > bestWeight) {
        bestWeight = weight;
        best = r;
      }
    }
    if (best < 0) throw new Error('SoftBody: hit is outside every region');

    const rest = this._rest;
    const a3 = ia * 3;
    const b3 = ib * 3;
    const c3 = ic * 3;
    const out = this._hit;
    out.region = best;
    out.ax = u * rest[a3] + v * rest[b3] + w * rest[c3];
    out.ay = u * rest[a3 + 1] + v * rest[b3 + 1] + w * rest[c3 + 1];
    out.az = u * rest[a3 + 2] + v * rest[b3 + 2] + w * rest[c3 + 2];
    let nx;
    let ny;
    let nz;
    const rn = this._restNormal;
    if (rn) {
      nx = u * rn[a3] + v * rn[b3] + w * rn[c3];
      ny = u * rn[a3 + 1] + v * rn[b3 + 1] + w * rn[c3 + 1];
      nz = u * rn[a3 + 2] + v * rn[b3 + 2] + w * rn[c3 + 2];
    } else {
      const e1x = rest[b3] - rest[a3];
      const e1y = rest[b3 + 1] - rest[a3 + 1];
      const e1z = rest[b3 + 2] - rest[a3 + 2];
      const e2x = rest[c3] - rest[a3];
      const e2y = rest[c3 + 1] - rest[a3 + 1];
      const e2z = rest[c3 + 2] - rest[a3 + 2];
      nx = e1y * e2z - e1z * e2y;
      ny = e1z * e2x - e1x * e2z;
      nz = e1x * e2y - e1y * e2x;
    }
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (!(len > 1e-12)) throw new Error('SoftBody: hit has no usable surface normal');
    out.nx = nx / len;
    out.ny = ny / len;
    out.nz = nz / len;
    return out;
  }
}

function resolveUnique(root, name) {
  let found = null;
  let count = 0;
  root.traverse((object) => {
    if (object.isMesh && (object.name === name || object.userData?.name === name)) {
      count++;
      found = object;
    }
  });
  if (count === 0) throw fail(`sidecar mesh "${name}" not found under root`);
  if (count > 1) throw fail(`sidecar mesh name "${name}" is ambiguous (${count} meshes)`);
  return found;
}

/**
 * Validate a v1 sidecar against a loaded root and create one SoftBody per
 * sidecar mesh entry, in sidecar order. Transactional: on any failure every
 * controller already created is disposed before the error is rethrown.
 */
export function attachSoftBodies(root, sidecar) {
  if (!root || typeof root.traverse !== 'function') throw fail('root must be an Object3D');
  if (!sidecar || typeof sidecar !== 'object' || sidecar.version !== 1) throw fail('sidecar.version must be 1');
  if (!Array.isArray(sidecar.meshes) || sidecar.meshes.length === 0) throw fail('sidecar.meshes must be a non-empty array');

  const plan = [];
  const seenMeshes = new Set();
  for (let i = 0; i < sidecar.meshes.length; i++) {
    const entry = sidecar.meshes[i];
    if (!entry || typeof entry !== 'object') throw fail(`sidecar.meshes[${i}] must be an object`);
    if (typeof entry.name !== 'string' || entry.name.length === 0) throw fail(`sidecar.meshes[${i}].name must be a string`);
    if (entry.hairAttribute !== undefined && (typeof entry.hairAttribute !== 'string' || entry.hairAttribute.length === 0)) {
      throw fail(`sidecar.meshes[${i}].hairAttribute must be a non-empty string`);
    }
    if (!Array.isArray(entry.regions) || entry.regions.length === 0) throw fail(`sidecar mesh "${entry.name}" needs regions`);
    const mesh = resolveUnique(root, entry.name);
    if (seenMeshes.has(mesh)) throw fail(`sidecar lists mesh "${entry.name}" more than once`);
    seenMeshes.add(mesh);
    const ids = new Set();
    for (const region of entry.regions) {
      if (!region || typeof region.id !== 'string' || region.id.length === 0) {
        throw fail(`sidecar mesh "${entry.name}" has a region without an id`);
      }
      if (ids.has(region.id)) throw fail(`sidecar mesh "${entry.name}" repeats region id "${region.id}"`);
      ids.add(region.id);
      if (typeof region.attribute !== 'string' || region.attribute.length === 0) {
        throw fail(`region "${region.id}" needs an attribute name`);
      }
    }
    plan.push({ mesh, entry });
  }

  const controllers = [];
  try {
    for (const { mesh, entry } of plan) {
      const options = {};
      if (entry.hairAttribute !== undefined) options.hairAttribute = entry.hairAttribute;
      const regions = entry.regions.map((region) => {
        const out = { id: region.id, attribute: region.attribute };
        if (region.group !== undefined) out.group = region.group;
        if (region.bone !== undefined) out.bone = region.bone;
        if (region.center !== undefined) out.center = region.center;
        if (region.radius !== undefined) out.radius = region.radius;
        return out;
      });
      controllers.push(new SoftBody(mesh, regions, options));
    }
  } catch (error) {
    for (const controller of controllers) controller.dispose();
    throw error;
  }
  return controllers;
}
