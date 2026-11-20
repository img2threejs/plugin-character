#!/usr/bin/env node
// Local-only owned Chromium/CDP measurement. Never installs a browser or contacts a provider.
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {readFile, writeFile, mkdir, mkdtemp, rm, access, realpath} from 'node:fs/promises';
import {constants, createReadStream} from 'node:fs';
import {createHash, randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname, join, resolve, isAbsolute, delimiter} from 'node:path';
import {tmpdir} from 'node:os';

const hash = data => createHash('sha256').update(data).digest('hex');
const plugin = resolve(dirname(fileURLToPath(import.meta.url)), '..');

async function fileHash(path) {
  const result = createHash('sha256');
  for await (const chunk of createReadStream(path)) result.update(chunk);
  return result.digest('hex');
}

async function chromium() {
  const override = process.env.IMG2_CHARACTER_BROWSER;
  if (override !== undefined && (!override || !isAbsolute(override))) {
    throw new Error('producer-dependency-invalid: IMG2_CHARACTER_BROWSER must be absolute');
  }
  const candidates = override !== undefined ? [override]
    : (process.env.PATH ?? '').split(delimiter).map(directory => join(directory || '.', 'chromium'));
  for (const path of candidates) {
    try { await access(path, constants.X_OK); return await realpath(path); } catch { /* Match PATH lookup, never download. */ }
  }
  throw new Error('capture-unavailable: PATH chromium or absolute IMG2_CHARACTER_BROWSER required');
}

class CDP {
  constructor(socket) {
    this.socket = socket;
    this.next = 0;
    this.pending = new Map();
    this.events = new Map();
    socket.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.id) {
        const entry = this.pending.get(message.id);
        if (!entry) return;
        this.pending.delete(message.id);
        clearTimeout(entry.timer);
        if (message.error) entry.reject(new Error(JSON.stringify(message.error)));
        else entry.resolve(message.result);
      } else {
        const key = `${message.sessionId ?? ''}:${message.method}`;
        const entry = this.events.get(key);
        if (entry) { this.events.delete(key); clearTimeout(entry.timer); entry.resolve(message.params); }
      }
    });
    socket.addEventListener('close', () => {
      for (const entry of [...this.pending.values(), ...this.events.values()]) { clearTimeout(entry.timer); entry.reject(new Error('capture browser disconnected')); }
      this.pending.clear();
      this.events.clear();
    });
  }
  call(method, params = {}, sessionId) {
    if (this.socket.readyState !== WebSocket.OPEN) return Promise.reject(new Error('capture browser is not connected'));
    const id = ++this.next;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error(`capture timed out: ${method}`)); }, method === 'Browser.close' ? 3000 : 180000);
      this.pending.set(id, {resolve, reject, timer});
      this.socket.send(JSON.stringify({id, method, params, ...(sessionId ? {sessionId} : {})}));
    });
  }
  event(method, sessionId) {
    const key = `${sessionId}:${method}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.events.delete(key); reject(new Error(`capture missing event: ${method}`)); }, 30000);
      this.events.set(key, {resolve, reject, timer});
    });
  }
}

// One fixed whitelist feeds serving, receipt hashes and the offline module-closure regression.
export async function captureSources(threeRoot) {
  return {
    'rig-measurements.mjs': await readFile(join(plugin, 'runtime/rig-measurements.mjs')),
    'runner.mjs': await readFile(join(plugin, 'runtime/rig-terminal-capture.mjs')),
    'three/build/three.module.js': await readFile(join(threeRoot, 'build/three.module.js')),
    'three/build/three.core.js': await readFile(join(threeRoot, 'build/three.core.js')),
    'three/examples/jsm/loaders/GLTFLoader.js': await readFile(join(threeRoot, 'examples/jsm/loaders/GLTFLoader.js')),
    'three/examples/jsm/utils/BufferGeometryUtils.js': await readFile(join(threeRoot, 'examples/jsm/utils/BufferGeometryUtils.js')),
    'three/examples/jsm/utils/SkeletonUtils.js': await readFile(join(threeRoot, 'examples/jsm/utils/SkeletonUtils.js')),
  };
}


const OS_ENVIRONMENT = ['HOME', 'TMPDIR', 'TMP', 'TEMP', 'LANG', 'LC_ALL', 'LC_CTYPE', 'SYSTEMROOT', 'WINDIR'];

export function browserEnvironment() {
  const environment = Object.fromEntries(OS_ENVIRONMENT.filter(key => process.env[key] !== undefined).map(key => [key, process.env[key]]));
  environment.PATH = process.platform === 'win32' ? join(process.env.SYSTEMROOT ?? 'C:\\Windows', 'System32') : '/bin:/usr/bin';
  return environment;
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

async function approvedThree(root, sources) {
  const approved = process.env.IMG2_CHARACTER_THREE_SHA256;
  if (!/^[a-f0-9]{64}$/.test(approved ?? '')) throw new Error('host Three approval digest is missing');
  const packageBytes = await readFile(join(root, 'package.json'));
  if (JSON.parse(packageBytes).version !== '0.186.1') throw new Error('producer-dependency-mismatch: Three.js 0.186.1 required');
  const names = [...Object.keys(sources).filter(name => name.startsWith('three/')).map(name => name.slice(6)), 'package.json'].sort();
  const files = names.map(path => ({path, sha256: hash(path === 'package.json' ? packageBytes : sources[`three/${path}`])}));
  const inventory = {kind: 'img2.character-three-package', version: 1, files};
  const actual = hash(Buffer.from(canonical(inventory), 'utf8'));
  if (actual !== approved) throw new Error('host-approved Three package digest mismatch');
  return {root, version: '0.186.1', sha256: actual, files, approval: 'host-approved'};
}


export async function runCapture(jobPath, output) {
  if (Number(process.versions.node.split('.')[0]) < 22) {
    throw new Error(`producer-dependency-missing: character-node>=22.0; actual ${process.version} at ${process.execPath}`);
  }
  if (typeof WebSocket !== 'function') throw new Error('producer-dependency-missing: Node.js with built-in WebSocket required (22+)');
  const browser = await chromium();
  const nodeIdentity = {executable: await realpath(process.execPath), version: process.version, sha256: await fileHash(process.execPath)};
  const browserIdentity = {path: browser, sha256: await fileHash(browser)};
  const driverSha = hash(await readFile(fileURLToPath(import.meta.url)));
  const configuredRoot = process.env.IMG2_CHARACTER_THREE_ROOT;
  if (!configuredRoot || !isAbsolute(configuredRoot)) throw new Error('absolute host-approved IMG2_CHARACTER_THREE_ROOT is required');
  const threeRoot = await realpath(configuredRoot);
  const job = JSON.parse(await readFile(jobPath, 'utf8'));
  const candidate = await readFile(job.candidatePath), baseline = await readFile(job.baselinePath);
  if (hash(candidate) !== job.glbSha256 || hash(baseline) !== job.baselineGlbSha256) throw new Error('capture source hash mismatch');
  const sources = await captureSources(threeRoot);
  const threeIdentity = await approvedThree(threeRoot, sources);
  const token = randomBytes(24).toString('hex');
  const stored = new Map();
  const expected = new Set(['runtime.json', ...job.frames.flatMap((_, i) => [`${i}-candidate.rgba`, `${i}-baseline.rgba`])]);
  await mkdir(output); // Refuse an existing output directory, never overwrite source evidence.
  let origin;
  const server = createServer(async (request, response) => {
    try {
      const prefix = `/${token}/`;
      if (!request.url.startsWith(prefix)) { response.writeHead(404).end(); return; }
      const name = request.url.slice(prefix.length);
      if (request.method === 'POST' && name.startsWith('capture/')) {
        const file = name.slice('capture/'.length);
        if (!expected.has(file) || stored.has(file)) throw new Error('unexpected/repeated capture');
        const chunks = [];
        let count = 0;
        const index = Number(file.split('-')[0]);
        const limit = file === 'runtime.json' ? 128 * 1024 * 1024 : job.frames[index].width * job.frames[index].height * 4;
        for await (const chunk of request) {
          count += chunk.length;
          if (count > limit) throw new Error('capture exceeds expected byte size');
          chunks.push(chunk);
        }
        const data = Buffer.concat(chunks);
        if (file !== 'runtime.json' && data.length !== limit) throw new Error('incomplete RGBA capture');
        await writeFile(join(output, file), data, {flag: 'wx'});
        stored.set(file, {path: file, sha256: hash(data)});
        response.writeHead(204).end();
        return;
      }
      if (request.method !== 'GET') { response.writeHead(405).end(); return; }
      if (name === '') {
        response.setHeader('Content-Type', 'text/html');
        response.end(`<script type="importmap">{"imports":{"three":"${origin}/three/build/three.module.js"}}</script>`);
      } else if (name === 'plan.json') {
        response.setHeader('Content-Type', 'application/json'); response.end(JSON.stringify(job));
      } else if (name === 'candidate.glb' || name === 'baseline.glb') {
        response.setHeader('Content-Type', 'model/gltf-binary'); response.end(name === 'candidate.glb' ? candidate : baseline);
      } else if (sources[name]) {
        response.setHeader('Content-Type', 'text/javascript'); response.end(sources[name]);
      } else response.writeHead(404).end();
    } catch (error) { response.writeHead(400).end(String(error)); }
  });
  let child, cdp, profile;
  const deadline = setTimeout(() => {
    if (child && child.exitCode === null) child.kill('SIGTERM');
    if (cdp) cdp.socket.close();
    server.closeAllConnections();
  }, 180000);
  try {
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    origin = `http://127.0.0.1:${server.address().port}/${token}`;
    profile = await mkdtemp(join(tmpdir(), 'img2-character-browser-'));
    const endpoint = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('capture browser did not expose CDP')), 30000);
      child = spawn(browser, ['--headless=new', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
        `--user-data-dir=${profile}`, '--no-first-run', '--no-default-browser-check', '--disable-extensions',
        '--disable-background-networking', '--disable-sync', '--disable-component-update',
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1', 'about:blank'], {stdio: ['ignore', 'ignore', 'pipe'], env: browserEnvironment()});
      let diagnostic = '';
      child.stderr.on('data', chunk => {
        diagnostic = (diagnostic + chunk.toString()).slice(-16384);
        const match = diagnostic.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/[^\s]+)/);
        if (match) { clearTimeout(timer); resolve(match[1]); }
      });
      child.once('error', error => { clearTimeout(timer); reject(error); });
      child.once('exit', code => { clearTimeout(timer); reject(new Error(`capture browser exited ${code}: ${diagnostic}`)); });
    });
    const socket = new WebSocket(endpoint);
    await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, {once: true}); socket.addEventListener('error', reject, {once: true}); });
    cdp = new CDP(socket);
    const browserVersion = await cdp.call('Browser.getVersion');
    const {targetId} = await cdp.call('Target.createTarget', {url: 'about:blank'});
    const {sessionId} = await cdp.call('Target.attachToTarget', {targetId, flatten: true});
    await cdp.call('Page.enable', {}, sessionId);
    // All script/asset fetches stay on the owned loopback origin; no remote APIs or assets.
    await cdp.call('Network.enable', {}, sessionId);
    await cdp.call('Network.setBlockedURLs', {urls: ['https://*', 'http://localhost:*', 'http://[::1]:*']}, sessionId);
    const loaded = cdp.event('Page.loadEventFired', sessionId);
    await cdp.call('Page.navigate', {url: `${origin}/`}, sessionId);
    await loaded;
    const result = await cdp.call('Runtime.evaluate', {expression: `import(${JSON.stringify(`${origin}/runner.mjs`)}).then(module=>module.capture())`, awaitPromise: true, returnByValue: true}, sessionId);
    if (result.exceptionDetails || !result.result?.value) throw new Error(`live capture failed: ${JSON.stringify(result.exceptionDetails ?? result)}`);
    if (stored.size !== expected.size) throw new Error('live capture did not produce every required file');
    const after = await approvedThree(threeRoot, await captureSources(threeRoot));
    if (canonical(after) !== canonical(threeIdentity)) throw new Error('host-approved Three changed during capture');
    const receipt = {kind: 'img2.character-live-capture', version: 1, glbSha256: job.glbSha256,
      baselineGlbSha256: job.baselineGlbSha256, browser: browserVersion, measurement: result.result.value,
      node: nodeIdentity, browserExecutable: browserIdentity,
      three: threeIdentity,
      producerFiles: {...Object.fromEntries(Object.entries(sources).map(([name, bytes]) => [name, hash(bytes)])),
        'tools/capture_routed_rig.mjs': driverSha},
      files: [...stored.values()]};
    await writeFile(join(output, 'capture.json'), JSON.stringify(receipt), {flag: 'wx'});
    return receipt;
  } finally {
    clearTimeout(deadline);
    if (cdp) { try { await cdp.call('Browser.close'); } catch { /* Owned process cleanup below. */ } cdp.socket.close(); }
    if (child && child.exitCode === null) {
      child.kill('SIGTERM');
      await new Promise(resolve => { const timer = setTimeout(() => { child.kill('SIGKILL'); resolve(); }, 3000); child.once('exit', () => { clearTimeout(timer); resolve(); }); });
    }
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    if (profile) await rm(profile, {recursive: true, force: true});
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 4 || args[0] !== '--input' || args[2] !== '--out') throw new Error('usage: capture_routed_rig.mjs --input JOB.json --out NEW_DIRECTORY');
  try { await runCapture(args[1], args[3]); }
  catch (error) { console.error(String(error)); process.exitCode = 2; }
}
