// Owned diagnostic and original-material consumer of the exact delivered GLB.
import * as THREE from 'three';
import {GLTFLoader} from './three/examples/jsm/loaders/GLTFLoader.js';
import {measureRig} from './rig-measurements.mjs';

async function sha(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    value => value.toString(16).padStart(2, '0')).join('');
}

function consumer(gltf) {
  const mixer = new THREE.AnimationMixer(gltf.scene);
  const clips = new Map(gltf.animations.map(clip => [clip.name, clip]));
  const controller = {
    seek(name, time) {
      const clip = clips.get(name);
      if (!clip) throw new Error(`missing clip ${name}`);
      mixer.stopAllAction();
      const action = mixer.clipAction(clip);
      action.reset().setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
      action.play();
      mixer.setTime(time);
    },
    stop() { mixer.stopAllAction(); },
  };
  const meshIds = new Map();
  gltf.scene.traverse(mesh => {
    if (!mesh.isMesh) return;
    const association = gltf.parser.associations.get(mesh);
    let node;
    for (let object = mesh; object && node === undefined; object = object.parent) {
      node = gltf.parser.associations.get(object)?.nodes;
    }
    if (node === undefined || association?.primitives === undefined) throw new Error('missing GLTFLoader primitive identity');
    meshIds.set(mesh, `node:${node}/primitive:${association.primitives}`);
  });
  return {root: gltf.scene, clips: gltf.animations, controller, meshIds};
}

const MATERIAL_PIXELS = Object.freeze({
  format: 'RGBA8', rawRowOrigin: 'bottom-left', pngRowOrigin: 'top-left',
  colorSpace: 'srgb', alphaMode: 'straight',
});
const SRGB_TO_LINEAR = Float64Array.from({length: 256}, (_, byte) => {
  const value = byte / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
});
const PNG_CRC = Uint32Array.from({length: 256}, (_, byte) => {
  let crc = byte;
  for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  return crc >>> 0;
});

function straightMaterialPixels(pixels) {
  // The sRGB render target stores linear-light blended (associated) color.
  // Unassociate in linear light, not by dividing the encoded sRGB channels.
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const alpha = pixels[offset + 3];
    if (alpha === 255) continue;
    for (let channel = 0; channel < 3; channel++) {
      const linear = alpha === 0 ? 0 : Math.min(1, SRGB_TO_LINEAR[pixels[offset + channel]] * 255 / alpha);
      const encoded = linear <= 0.0031308 ? linear * 12.92 : 1.055 * linear ** (1 / 2.4) - 0.055;
      pixels[offset + channel] = Math.round(encoded * 255);
    }
  }
}

function pngChunk(type, data) {
  const chunk = new Uint8Array(data.length + 12);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, data.length);
  for (let index = 0; index < 4; index++) chunk[4 + index] = type.charCodeAt(index);
  chunk.set(data, 8);
  let crc = 0xffffffff;
  for (let index = 4; index < chunk.length - 4; index++) crc = (crc >>> 8) ^ PNG_CRC[(crc ^ chunk[index]) & 255];
  view.setUint32(chunk.length - 4, (crc ^ 0xffffffff) >>> 0);
  return chunk;
}

async function materialPng(pixels, width, height) {
  // Canvas2D round-trips through premultiplied storage and loses low-alpha RGB.
  // Encode RGBA8 directly, retaining every byte and the prescribed vertical flip.
  const stride = width * 4;
  const rows = new Uint8Array((stride + 1) * height);
  for (let y = 0; y < height; y++) {
    rows.set(pixels.subarray((height - y - 1) * stride, (height - y) * stride), y * (stride + 1) + 1);
  }
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  header[8] = 8;
  header[9] = 6;
  const compressed = new Uint8Array(await new Response(
    new Blob([rows]).stream().pipeThrough(new CompressionStream('deflate'))).arrayBuffer());
  return new Blob([Uint8Array.of(137, 80, 78, 71, 13, 10, 26, 10),
    pngChunk('IHDR', header), pngChunk('sRGB', Uint8Array.of(0)),
    pngChunk('IDAT', compressed), pngChunk('IEND', new Uint8Array())], {type: 'image/png'});
}

async function post(name, bytes) {
  const response = await fetch(new URL(`capture/${name}`, import.meta.url), {method: 'POST', body: bytes});
  if (!response.ok) throw new Error(`capture storage failed: ${name}`);
}

export async function capture() {
  const plan = await (await fetch(new URL('plan.json', import.meta.url))).json();
  const load = async (name, expected) => {
    const bytes = await (await fetch(new URL(name, import.meta.url))).arrayBuffer();
    if (await sha(bytes) !== expected) throw new Error('browser loaded foreign GLB bytes');
    return new GLTFLoader().parseAsync(bytes, '');
  };
  const candidate = consumer(await load('candidate.glb', plan.glbSha256));
  const baseline = consumer(await load('baseline.glb', plan.baselineGlbSha256));
  const runtime = measureRig({...candidate, glbSha256: plan.glbSha256});
  await post('runtime.json', new TextEncoder().encode(JSON.stringify(runtime)));
  const renderer = new THREE.WebGLRenderer({alpha: true, antialias: false});
  renderer.setPixelRatio(1);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  const debug = renderer.getContext().getExtension('WEBGL_debug_renderer_info');
  const rendererName = debug ? renderer.getContext().getParameter(debug.UNMASKED_RENDERER_WEBGL) : renderer.getContext().getParameter(renderer.getContext().RENDERER);
  const scenes = [];
  const materials = [];
  const materialBindings = [];
  for (const input of [candidate, baseline]) {
    const scene = new THREE.Scene();
    scene.add(input.root);
    const bindings = [];
    input.root.traverse(object => { if (object.isLight) object.visible = false; });
    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 3);
    keyLight.position.set(3, 5, 4);
    scene.add(keyLight);
    input.root.traverse(mesh => {
      if (!mesh.isMesh) return;
      const originals = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const replacement = originals.map(material => {
        const diagnostic = new THREE.MeshNormalMaterial({side: material.side});
        materials.push(diagnostic);
        return diagnostic;
      });
      const diagnostic = Array.isArray(mesh.material) ? replacement : replacement[0];
      bindings.push({mesh, original: mesh.material, diagnostic});
      mesh.material = diagnostic;
    });
    scenes.push(scene);
    materialBindings.push(bindings);
  }
  try {
    for (let i = 0; i < plan.frames.length; i++) {
      const frame = plan.frames[i];
      const camera = frame.camera.projectionMatrix[15] === 1
        ? new THREE.OrthographicCamera() : new THREE.PerspectiveCamera();
      camera.matrixAutoUpdate = false;
      camera.matrix.fromArray(frame.camera.matrixWorld);
      camera.projectionMatrix.fromArray(frame.camera.projectionMatrix);
      camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
      camera.updateMatrixWorld(true);
      const target = new THREE.WebGLRenderTarget(frame.width, frame.height, {type: THREE.UnsignedByteType, format: THREE.RGBAFormat});
      target.texture.colorSpace = THREE.SRGBColorSpace;
      target.texture.internalFormat = 'SRGB8_ALPHA8';
      const pixels = new Uint8Array(frame.width * frame.height * 4);
      try {
        for (const [j, input] of [candidate, baseline].entries()) {
          const clip = input.clips.find(clip => clip.name === frame.clip);
          if (!clip) throw new Error('sweep references foreign clip');
          input.controller.seek(frame.clip, clip.duration * frame.time);
          input.root.updateMatrixWorld(true);
          input.root.traverse(mesh => { if (mesh.isSkinnedMesh) mesh.skeleton.update(); });
          renderer.setRenderTarget(target);
          renderer.clear();
          renderer.render(scenes[j], camera);
          renderer.readRenderTargetPixels(target, 0, 0, frame.width, frame.height, pixels);
          if (renderer.getContext().isContextLost()) throw new Error('WebGL context lost');
          // RGBA and ROI rows are both WebGL bottom-up. No screenshot/canvas orientation guess.
          await post(`${i}-${j === 0 ? 'candidate' : 'baseline'}.rgba`, pixels);
          if (j === 0) {
            for (const binding of materialBindings[j]) binding.mesh.material = binding.original;
            try {
              renderer.clear();
              renderer.render(scenes[j], camera);
              renderer.readRenderTargetPixels(target, 0, 0, frame.width, frame.height, pixels);
              if (renderer.getContext().isContextLost()) throw new Error('WebGL material context lost');
              straightMaterialPixels(pixels);
              await post(`${i}-material.rgba`, pixels);
              await post(`${i}-material.png`, await materialPng(pixels, frame.width, frame.height));
            } finally {
              for (const binding of materialBindings[j]) binding.mesh.material = binding.diagnostic;
            }
          }
          input.controller.stop();
        }
      } finally { target.dispose(); }
    }
  } finally {
    candidate.controller.stop();
    baseline.controller.stop();
    for (const material of materials) material.dispose();
    renderer.dispose();
  }
  return {threeRevision: THREE.REVISION, renderer: String(rendererName), diagnostic: 'opaque-source-sided-normal-v1',
    materialCapture: 'original-material-fixed-lighting-v1', materialPixels: MATERIAL_PIXELS,
    frameCount: plan.frames.length};
}
