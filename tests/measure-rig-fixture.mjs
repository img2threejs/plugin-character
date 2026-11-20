// Test-only CPU fixture controller. Not production viewer/render qualification.
import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {AnimationMixer, LoopOnce} from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {measureRig} from '../runtime/rig-measurements.mjs';

const bytes = await readFile(process.argv[2]);
const gltf = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
const mixer = new AnimationMixer(gltf.scene);
const clips = new Map(gltf.animations.map(clip => [clip.name, clip]));
const controller = {
  seek(name, time) {
    mixer.stopAllAction();
    const action = mixer.clipAction(clips.get(name));
    action.reset().setLoop(LoopOnce, 1);
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
  if (node === undefined || association?.primitives === undefined) throw new Error('missing GLTFLoader association');
  meshIds.set(mesh, `node:${node}/primitive:${association.primitives}`);
});
const result = measureRig({root: gltf.scene, clips: gltf.animations, controller, meshIds,
  glbSha256: createHash('sha256').update(bytes).digest('hex')});
await writeFile(process.argv[3], JSON.stringify(result));
