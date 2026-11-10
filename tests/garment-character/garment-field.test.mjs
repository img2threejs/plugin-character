// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildGraph, distanceField, falloff, falloffSlope, geodesic } from '../../runtime/garment-character/garment-field.mjs';

// A ring of quads (a neck-loop-like band) built from `n` columns x 2 rows; the seam column is
// duplicated (as a UV seam would be): vertices n*2.. repeat column 0 at the same position.
function ring(n, radius = 0.05) {
  const rest = [], weld = [], indices = [];
  for (let c = 0; c < n; c++) for (let r = 0; r < 2; r++) {
    const a = (2 * Math.PI * c) / n;
    rest.push(radius * Math.cos(a), r * 0.01, radius * Math.sin(a)); weld.push(c * 2 + r);
  }
  rest.push(...rest.slice(0, 6)); weld.push(0, 1);
  const at = (c, r) => (c === n ? 2 * n + r : c * 2 + r);
  for (let c = 0; c < n; c++) {
    const a = at(c, 0), b = at(c + 1, 0), cc = at(c, 1), d = at(c + 1, 1);
    indices.push(a, b, cc, b, d, cc);
  }
  return { rest: Float32Array.from(rest), weldIds: Uint32Array.from(weld), indices: Uint32Array.from(indices), weldCount: 2 * n };
}

test('distance runs along the surface, around the loop the short way, and seam duplicates share one distance', () => {
  const n = 40, { rest, weldIds, indices, weldCount } = ring(n);
  const graph = buildGraph(weldIds, weldCount, rest, indices);
  const geo = geodesic(graph, [{ weld: 0, distance: 0 }]);
  const step = 2 * 0.05 * Math.sin(Math.PI / n);
  assert.ok(Math.abs(geo[2 * 10] - 10 * step) < step * 1.2, 'ten columns along the ring');
  assert.ok(Math.abs(geo[2 * 30] - 10 * step) < step * 1.2, 'thirty columns = ten the other way round');
  const far = geo[2 * 20];
  assert.ok(far > 18 * step && far < 21 * step, 'the far side is half the ring away');
  const field = distanceField(graph, rest, [0], { x: rest[0], y: rest[1], z: rest[2] }, new Float32Array(weldIds.length));
  assert.equal(field[weldIds.length - 2], field[0], 'the duplicated seam vertex has the same distance as its twin');
});

test('a part the surface cannot reach falls back to its straight distance instead of staying behind', () => {
  const { rest, weldIds, indices, weldCount } = ring(12);
  const lone = Float32Array.from([...rest, 0.3, 0, 0, 0.31, 0, 0, 0.3, 0.01, 0]), ids = Uint32Array.from([...weldIds, weldCount, weldCount + 1, weldCount + 2]);
  const idx = Uint32Array.from([...indices, rest.length / 3, rest.length / 3 + 1, rest.length / 3 + 2]);
  const graph = buildGraph(ids, weldCount + 3, lone, idx);
  const field = distanceField(graph, lone, [0], { x: lone[0], y: lone[1], z: lone[2] }, new Float32Array(ids.length));
  const k = rest.length / 3;
  assert.ok(Number.isFinite(field[k]) && Math.abs(field[k] - Math.hypot(0.3 - lone[0], lone[1], lone[2])) < 1e-6, 'straight distance for the loose piece');
});

test('the kernel is 1 at the grab, 0 at the reach, never rises, and neighbours differ by at most slope x edge', () => {
  const plateau = 0.02, reach = 0.2;
  assert.equal(falloff(0, plateau, reach), 1); assert.equal(falloff(reach, plateau, reach), 0); assert.equal(falloff(reach * 3, plateau, reach), 0);
  let previous = 1; const edge = 0.004, bound = falloffSlope(plateau, reach) * edge + 1e-9;
  for (let d = 0; d <= reach + 0.05; d += edge) {
    const w = falloff(d, plateau, reach);
    assert.ok(w <= previous + 1e-12, `monotonic at ${d}`);
    assert.ok(Math.abs(previous - w) <= bound, `neighbour weights differ by at most the slope bound at ${d}`);
    previous = w;
  }
});
