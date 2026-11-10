#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Prints the exported NON-function constants of the garment-character runtime as JSON.
//
//   node tools/extract_garment_parameters.mjs            # JSON on stdout
//   node tools/extract_garment_parameters.mjs --out f    # also writes the same JSON to f
//
// reference/garment-parameters.json stores this output under `constants`, next to a
// hand-built `subjectLiterals` list. tests/test_garment_character_provenance.py fails when
// the stored constants drift from the runtime copies, so a parameter cannot be edited in
// the runtime without the reference being regenerated.
import { writeFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const runtime = join(dirname(fileURLToPath(import.meta.url)), '..', 'runtime', 'garment-character');
const MODULES = ['garment', 'chest-field', 'softbody'];
// Constants the route doc and gates rely on; their absence means the runtime was changed incompatibly.
const REQUIRED = {
  garment: ['STRAP', 'PANEL', 'PULL_PATCH', 'STRAP_FIELD', 'CUP_LIFT', 'CONTACT_STEADY', 'SKIN_GUARD', 'FLAP', 'TRANSITION', 'REDUCED_TRANSITION', 'OUTFITS'],
  'chest-field': ['ROUND_CHEST'],
  softbody: ['PROFILES', 'REGION_IDS'],
};

/** Deep plain-JSON copy (frozen objects/arrays included); rejects values JSON cannot round-trip. */
function plain(value, path) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error(`${path}: non-finite number`);
    return value;
  }
  if (typeof value === 'string' || typeof value === 'boolean' || value === null) return value;
  if (Array.isArray(value)) return value.map((item, i) => plain(item, `${path}[${i}]`));
  if (typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, plain(v, `${path}.${k}`)]));
  throw new Error(`${path}: unsupported ${typeof value}`);
}

const constants = {};
for (const name of MODULES) {
  const mod = await import(pathToFileURL(join(runtime, `${name}.mjs`)).href);
  for (const required of REQUIRED[name]) {
    if (!(required in mod)) throw new Error(`${name}.mjs no longer exports ${required}`);
  }
  constants[name] = {};
  for (const key of Object.keys(mod).sort()) {
    if (typeof mod[key] === 'function') continue;
    constants[name][key] = plain(mod[key], `${name}.${key}`);
  }
}

const text = JSON.stringify({ generatedFrom: 'runtime/garment-character/*.mjs', constants }, null, 2) + '\n';
const out = process.argv.indexOf('--out');
if (out !== -1) {
  if (!process.argv[out + 1]) throw new Error('--out needs a file path');
  writeFileSync(process.argv[out + 1], text);
}
process.stdout.write(text);
