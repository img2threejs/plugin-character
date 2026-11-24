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
              await post(`${i}-material.rgba`, pixels);
              // PNG consumers use top-down rows; the G10 buffers above remain bottom-up.
              const upright = new Uint8ClampedArray(pixels.length);
              const stride = frame.width * 4;
              for (let y = 0; y < frame.height; y++) {
                upright.set(pixels.subarray((frame.height - y - 1) * stride, (frame.height - y) * stride), y * stride);
              }
              const canvas = document.createElement('canvas');
              canvas.width = frame.width;
              canvas.height = frame.height;
              canvas.getContext('2d').putImageData(new ImageData(upright, frame.width, frame.height), 0, 0);
              const image = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
              if (!image) throw new Error('material PNG encoding failed');
              await post(`${i}-material.png`, new Uint8Array(await image.arrayBuffer()));
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
    materialCapture: 'original-material-fixed-lighting-v1', frameCount: plan.frames.length};
}
