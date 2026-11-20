// Offline linking only: no browser, renderer, external fetch or executed Three.js code.
// Run with node --experimental-vm-modules --test tests/rig-capture-modules.test.mjs.
import test from 'node:test';
import assert from 'node:assert/strict';
import {SourceTextModule} from 'node:vm';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {captureSources, browserEnvironment} from '../tools/capture_routed_rig.mjs';

async function sources() {
  // Resolver fallback is TEST-ONLY. Production requires an independently approved root/pin.
  const root = process.env.IMG2_CHARACTER_THREE_ROOT
    ?? resolve(dirname(fileURLToPath(import.meta.resolve('three'))), '..');
  return captureSources(root);
}

async function link(files) {
  const origin = new URL('http://127.0.0.1/owned-capture/');
  const modules = new Map(Object.entries(files).map(([name, bytes]) => [
    new URL(name, origin).href, new SourceTextModule(bytes.toString('utf8'), {identifier: new URL(name, origin).href}),
  ]));
  await modules.get(new URL('runner.mjs', origin).href).link((specifier, referencing) => {
    const target = specifier === 'three'
      ? new URL('three/build/three.module.js', origin).href
      : new URL(specifier, referencing.identifier).href;
    const module = modules.get(target);
    if (!module) throw new Error(`unserved static dependency: ${target}`);
    return module;
  });
}

test('fixed served/hashed source inventory closes actual static ESM imports', async () => {
  await link(await sources());
});

test('missing SkeletonUtils is detected before browser dynamic import', async () => {
  const files = await sources();
  delete files['three/examples/jsm/utils/SkeletonUtils.js'];
  await assert.rejects(link(files), /unserved static dependency: .*SkeletonUtils\.js/);
});

test('Chromium environment excludes preload hooks and API credentials', () => {
  const forbidden = ['NODE_OPTIONS', 'NODE_PATH', 'LD_PRELOAD', 'DYLD_INSERT_LIBRARIES',
    'PYTHONPATH', 'BASH_ENV', 'TYPESAFE_API_KEY', 'AWS_SECRET_ACCESS_KEY', 'HTTPS_PROXY'];
  const previous = new Map(forbidden.map(name => [name, process.env[name]]));
  try {
    for (const name of forbidden) process.env[name] = 'test-only-do-not-inherit';
    const environment = browserEnvironment();
    for (const name of forbidden) assert.equal(Object.hasOwn(environment, name), false, name);
  } finally {
    for (const [name, value] of previous) {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    }
  }
});
