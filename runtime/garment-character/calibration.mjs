// SPDX-License-Identifier: Apache-2.0
// Per-input dimensions, semantic selections and artistic choices are not solver defaults.
export function requireFields(value, fields, label) {
  if (!value || typeof value !== 'object') throw new Error(`${label}: explicit configuration required`);
  for (const [key, rule] of Object.entries(fields)) {
    if (!rule(value[key])) throw new Error(`${label}.${key}: invalid or missing calibration`);
  }
  return value;
}
const finite = Number.isFinite;
const positive = v => finite(v) && v > 0;
const nonnegative = v => finite(v) && v >= 0;
const text = v => typeof v === 'string' && v.length > 0;
const vector = v => Array.isArray(v) && v.length === 3 && v.every(finite);
const pair = v => Array.isArray(v) && v.length === 2 && v.every(finite) && v[1] > v[0];
export function validateGarmentCalibration(c) {
  requireFields(c, { bodyMesh: text, garmentMesh: text, regions: v => v && text(v[1]) && text(v[-1]),
    outfits: v => Array.isArray(v) && v.length === 2 && v.every(text) && v[0] !== v[1], origin: vector, normalOrigin: vector }, 'garment');
  if (c.bodyMesh === c.garmentMesh || c.regions[1] === c.regions[-1]) throw new Error('garment: distinct meshes and side regions required');
  requireFields(c.strap, { yAttach: finite, yTop: finite, maxAbsX: positive, minZ: finite, maxPull: positive,
    grabMin: nonnegative, grabMax: positive, frequency: positive, dampingRatio: positive, holdFrequency: positive, tension: nonnegative }, 'garment.strap');
  if (!(c.strap.yTop > c.strap.yAttach && c.strap.grabMin < c.strap.grabMax && c.strap.grabMax <= 1)) throw new Error('garment.strap: invalid interval');
  requireFields(c.panel, { maxPull: positive, frequency: positive, dampingRatio: positive, normalLift: nonnegative }, 'garment.panel');
  requireFields(c.strapField, { reachFactor: positive, minReach: positive, fallbackReach: positive, pinRange: positive, liftFade: pair }, 'garment.strapField');
  requireFields(c.cupLift, { gap: nonnegative, lead: pair, extent: positive }, 'garment.cupLift');
  requireFields(c.contactSteady, { maxDisagreement: positive }, 'garment.contactSteady');
  requireFields(c.flap, { hinge: positive, bend: positive, reach: positive, lift: nonnegative, ribbonLift: nonnegative, cutSpan: positive, normalRadius: positive, hang: vector }, 'garment.flap');
  if (c.flap.cutSpan > 1 || Math.hypot(...c.flap.hang) === 0) throw new Error('garment.flap: invalid cut or hanging direction');
  validateContactCalibration(c.contact);
  requireFields(c.colorway, { saturation: pair, hueIn: v => Array.isArray(v) && v.length === 4 && v.every(finite) && v.every((x,i) => i === 0 || x > v[i-1]), hueOut: finite, saturationScale: positive, valueScale: positive }, 'garment.colorway');
  requireFields(c.visual, { sparkWidth: positive, noiseScale: positive, noiseAmplitude: nonnegative, waveWidth: positive, revealWidth: positive, glowColor: vector }, 'garment.visual');
  return c;
}
export function validateContactCalibration(c) {
  requireFields(c, { heightRange: pair, strapRadius: positive, panelRadius: positive, minGap: positive, maxGap: positive }, 'contact');
  if (c.maxGap < c.minGap) throw new Error('contact: maxGap must not be below minGap');
  return c;
}
export function validateSoftCalibration(c) {
  if (!c || typeof c !== 'object') throw new Error('SoftRig: explicit calibration required');
  for (const kind of ['chest', 'hips', 'abdomen', 'waist', 'cheek']) {
    const p = requireFields(c.profiles?.[kind], { frequency: positive, dampingRatio: v => positive(v) && v < 1, cap: positive, compression: nonnegative }, `SoftRig.profiles.${kind}`);
    if (p.pressDepth !== undefined && !finite(p.pressDepth)) throw new Error(`SoftRig.profiles.${kind}.pressDepth: invalid`);
    const pad = c.pads?.[kind];
    if (!Array.isArray(pad) || pad.length !== 2 || !positive(pad[0]) || !nonnegative(pad[1])) throw new Error(`SoftRig.pads.${kind}: invalid or missing calibration`);
  }
  return c;
}
export function validateRoundCalibration(c) {
  requireFields(c, { plateau: nonnegative, reach: positive, wallDepth: nonnegative, wallFade: positive, midline: finite, midlineFade: positive,
    regions: v => Array.isArray(v) && v.length > 0 && v.every(text), suffix: text }, 'roundChestMasks');
  if (!(c.reach > c.plateau)) throw new Error('roundChestMasks: reach must exceed plateau');
  return c;
}
export function validateViewerConfig(c) {
  requireFields(c, { label: text, synthetic: v => typeof v === 'boolean', clip: text, initialView: text,
    views: v => v && Object.keys(v).length > 0, regionViews: v => v && typeof v === 'object', outfitLabels: v => v && typeof v === 'object',
    background: v => Number.isInteger(v) && v >= 0 && v <= 0xffffff,
    lights: v => v && ['sky','ground','key','fill'].every(k=>Number.isInteger(v[k]) && v[k]>=0 && v[k]<=0xffffff),
    camera: v => v && positive(v.fov) && positive(v.near) && positive(v.far) && v.far > v.near && positive(v.minDistance) && v.maxDistance > v.minDistance,
    probes: v => v && finite(v.panelY) && positive(v.pullDistance) }, 'viewer');
  for (const [name, view] of Object.entries(c.views)) requireFields(view, { position: vector, target: vector }, `viewer.views.${name}`);
  if (!c.views[c.initialView]) throw new Error('viewer.initialView: unknown view');
  validateGarmentCalibration(c.garment); validateSoftCalibration(c.soft); validateRoundCalibration(c.round);
  for (const id of Object.values(c.garment.regions)) if (!c.round.regions.includes(id)) throw new Error(`viewer.round.regions: missing garment region ${id}`);
  for (const id of ['chest-left','chest-right','hips-left','hips-right','waist-left','waist-right','abdomen','cheek-left','cheek-right']) {
    if (!c.views[c.regionViews[id]]) throw new Error(`viewer.regionViews.${id}: unknown view`);
  }
  for (const id of c.garment.outfits) if (!text(c.outfitLabels[id])) throw new Error(`viewer.outfitLabels.${id}: missing`);
  if (!c.synthetic && (!text(c.glb) || !text(c.sidecar))) throw new Error('viewer: real inputs require glb and sidecar URLs');
  return c;
}
