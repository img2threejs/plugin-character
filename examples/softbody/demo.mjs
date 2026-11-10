import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { attachSoftBodies } from '../../runtime/softbody.mjs';

const $ = (id) => document.getElementById(id);
const renderer = new THREE.WebGLRenderer({ canvas: $('canvas'), antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
const scene = new THREE.Scene();
scene.add(new THREE.HemisphereLight(0xdfefff, 0x253041, 2));
const key = new THREE.DirectionalLight(0xffffff, 3);
key.position.set(3, 4, 5);
scene.add(key);
const rim = new THREE.DirectionalLight(0x75cfff, 2);
rim.position.set(-3, 1, -2);
scene.add(rim);
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const impulse = new THREE.Vector3();
let root, config, controllers = [], diagnosticBone = null;
let activePress = null, lastTime = null, statusTime = 0, revision = 0;
let basePositions = [], pickScratch = new THREE.Vector3();

function fixture() {
  const geometry = new THREE.SphereGeometry(0.8, 64, 48);
  const position = geometry.getAttribute('position');
  const upper = new Float32Array(position.count), lower = new Float32Array(position.count);
  const hair = new Float32Array(position.count), colors = new Float32Array(position.count * 3);
  const skinIndex = new Uint16Array(position.count * 4), skinWeight = new Float32Array(position.count * 4);
  const morph = new Float32Array(position.count * 3);
  const color = new THREE.Color();
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i), y = position.getY(i) * 1.4, z = position.getZ(i);
    position.setY(i, y);
    const weight = (cy) => { const r = Math.hypot(x, y - cy, z - 0.64) / 0.83; return r < 1 ? (1 - r * r) ** 2 : 0; };
    upper[i] = weight(0.4); lower[i] = weight(-0.48);
    hair[i] = x > 0.24 && x < 0.40 && z > 0.25 ? 1 : 0;
    color.set(hair[i] ? '#e8c784' : upper[i] > lower[i] ? '#56bdb1' : '#887ac9');
    colors.set([color.r, color.g, color.b], i * 3);
    const w = THREE.MathUtils.clamp((y + 0.2) / 0.8, 0, 1);
    skinIndex[i * 4 + 1] = 1; skinWeight[i * 4] = 1 - w; skinWeight[i * 4 + 1] = w;
    morph[i * 3] = z * 0.18;
  }
  geometry.setAttribute('_SOFT_UPPER', new THREE.BufferAttribute(upper, 1));
  geometry.setAttribute('_SOFT_LOWER', new THREE.BufferAttribute(lower, 1));
  geometry.setAttribute('_HAIR', new THREE.BufferAttribute(hair, 1));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('skinIndex', new THREE.BufferAttribute(skinIndex, 4));
  geometry.setAttribute('skinWeight', new THREE.BufferAttribute(skinWeight, 4));
  geometry.morphTargetsRelative = true;
  geometry.morphAttributes.position = [new THREE.BufferAttribute(morph, 3)];
  geometry.computeVertexNormals();
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.38, metalness: 0, side: THREE.DoubleSide }));
  mesh.name = 'DiagnosticSurface';
  const base = new THREE.Bone(), tip = new THREE.Bone();
  base.name = 'DiagnosticRoot'; tip.name = 'DiagnosticUpper'; tip.position.y = 0.2;
  base.add(tip); mesh.add(base);
  mesh.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton([base, tip]));
  mesh.morphTargetDictionary = { OriginalShape: 0 };
  const group = new THREE.Group(); group.add(mesh);
  return { root: group, bone: tip, config: { version: 1, meshes: [{ name: mesh.name, hairAttribute: '_HAIR', regions: [
    { id: 'upper', group: 'Vùng trên', attribute: '_SOFT_UPPER', bone: tip.name },
    { id: 'lower', group: 'Vùng dưới', attribute: '_SOFT_LOWER', bone: base.name },
  ] }] } };
}

function cancelPress() {
  if (activePress) activePress.controller.release(activePress.token);
  activePress = null; controls.enabled = true;
}
function disposeRoot(value) {
  if (!value) return;
  const geometries = new Set(), materials = new Set(), textures = new Set();
  value.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    for (const material of object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : []) {
      materials.add(material);
      for (const item of Object.values(material)) if (item?.isTexture) textures.add(item);
    }
  });
  for (const item of [...geometries, ...materials, ...textures]) item.dispose();
}
function install(value, sidecar, bone = null) {
  const next = attachSoftBodies(value, sidecar); // Validation is transactional; keep old view on failure.
  cancelPress();
  controllers.forEach((controller) => controller.dispose());
  scene.remove(root); disposeRoot(root);
  root = value; config = sidecar; controllers = next; diagnosticBone = bone;
  scene.add(root); root.updateMatrixWorld(true);
  basePositions = controllers.map((controller) => controller.dynamicMesh.geometry.getAttribute('position').array.slice());
  const bounds = new THREE.Box3().setFromObject(root), center = bounds.getCenter(new THREE.Vector3());
  const radius = Math.max(bounds.getSize(new THREE.Vector3()).length() * 0.5, 0.1);
  camera.near = radius / 100; camera.far = radius * 100; camera.updateProjectionMatrix();
  camera.position.copy(center).add(new THREE.Vector3(0, 0.05 * radius, radius * 3.8));
  controls.target.copy(center); controls.update();
  $('sizes').replaceChildren();
  for (let i = 0; i < sidecar.meshes.length; i++) for (const region of sidecar.meshes[i].regions) {
    const label = document.createElement('label'), output = document.createElement('output'), input = document.createElement('input');
    label.append(document.createTextNode(`${sidecar.meshes[i].name} / ${region.group || region.id}`));
    output.value = '1.00'; input.type = 'range'; input.min = '0.6'; input.max = '1.5'; input.step = '0.01'; input.value = '1';
    input.id = `region-size-${i}-${$('sizes').childElementCount}`; label.htmlFor = input.id;
    input.dataset.region = region.id;
    input.addEventListener('input', () => { controllers[i].setSize(region.id, Number(input.value)); output.value = Number(input.value).toFixed(2); });
    label.append(output, input); $('sizes').append(label);
  }
  $('pose').disabled = !bone; $('pose').value = '0';
  $('morph').value = '0'; $('morph-value').value = '0.00';
  $('softness').value = '0.6'; $('soft-value').value = '0.60';
  controllers.forEach((controller) => controller.setSoftness(0.6));
  revision++;
  $('status').textContent = 'Đã nạp vùng tác động. Chưa phải xác nhận likeness, collision hay hiệu năng điện thoại.';
}
function showFixture() {
  const value = fixture(); install(value.root, value.config, value.bone);
  $('asset-label').textContent = 'Hình học chẩn đoán có skin và morph, không phải nhân vật thật hay kết quả CC5.';
}
function intersect(event, controller = null) {
  const box = renderer.domElement.getBoundingClientRect();
  pointer.set((event.clientX - box.left) / box.width * 2 - 1, -(event.clientY - box.top) / box.height * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObject(root, true)[0];
  if (!hit || !controllers.some((item) => item.dynamicMesh === hit.object)) return null;
  return !controller || hit.object === controller.dynamicMesh ? hit : null;
}
renderer.domElement.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || activePress) return;
  const hit = intersect(event); if (!hit) return;
  const controller = controllers.find((item) => item.dynamicMesh === hit.object);
  let token;
  try { token = controller.press(hit); }
  catch (error) { $('status').textContent = `Không thể nhấn tại điểm này: ${error.message}`; return; }
  if (!token) return;
  activePress = { id: event.pointerId, controller, token }; controls.enabled = false;
  renderer.domElement.setPointerCapture(event.pointerId);
}, { capture: true });
renderer.domElement.addEventListener('pointermove', (event) => {
  if (!activePress || activePress.id !== event.pointerId) return;
  const hit = intersect(event, activePress.controller);
  if (hit) {
    try { activePress.controller.move(activePress.token, hit); }
    catch (error) { cancelPress(); $('status').textContent = `Đã thả điểm kéo: ${error.message}`; }
  }
});
for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) renderer.domElement.addEventListener(name, (event) => {
  if (activePress?.id === event.pointerId) cancelPress();
});
$('softness').addEventListener('input', (event) => {
  const value = Number(event.target.value); controllers.forEach((controller) => controller.setSoftness(value)); $('soft-value').value = value.toFixed(2);
});
$('morph').addEventListener('input', (event) => {
  const value = Number(event.target.value);
  root.traverse((object) => { if (object.morphTargetInfluences?.length) object.morphTargetInfluences[0] = value; });
  $('morph-value').value = value.toFixed(2);
});
$('pose').addEventListener('input', (event) => { if (diagnosticBone) diagnosticBone.rotation.z = Number(event.target.value); });
$('impulse').addEventListener('click', () => {
  impulse.set(0.3, 0.4, 0.5);
  config.meshes.forEach((mesh, i) => mesh.regions.forEach((region) => controllers[i].impulse(region.id, impulse)));
});
$('reset').addEventListener('click', () => {
  cancelPress(); controllers.forEach((controller) => controller.reset());
  $('sizes').querySelectorAll('input').forEach((input) => { input.value = '1'; input.previousElementSibling.value = '1.00'; });
});
$('diagnostic').addEventListener('click', showFixture);
$('load').addEventListener('click', async () => {
  const glb = $('glb').files[0], sidecar = $('config').files[0];
  if (!glb || !sidecar) { $('status').textContent = 'Cần chọn cả GLB và softbody.json.'; return; }
  try {
    const settings = JSON.parse(await sidecar.text());
    const manager = new THREE.LoadingManager();
    manager.setURLModifier((url) => {
      if (!url.startsWith('blob:') && !url.startsWith('data:')) throw new Error('GLB phải nhúng mọi tài nguyên; không tải URL ngoài.');
      return url;
    });
    const asset = await new GLTFLoader(manager).parseAsync(await glb.arrayBuffer(), '');
    try { install(asset.scene, settings); } catch (error) { disposeRoot(asset.scene); throw error; }
    $('asset-label').textContent = `${glb.name}: asset người dùng, chưa kiểm chứng likeness hoặc motion clips. ${asset.animations.length} clip được đọc, chưa phát.`;
  } catch (error) { $('status').textContent = `Không mở asset: ${error.message}`; }
});
new ResizeObserver(() => {
  const box = $('view').getBoundingClientRect(); renderer.setSize(box.width, box.height, false);
  camera.aspect = box.width / box.height; camera.updateProjectionMatrix();
}).observe($('view'));

// Local diagnostic hooks expose measured geometry, not fabricated pass flags.
window.softbodyDemo = {
  get controllers() { return controllers; }, get root() { return root; }, get camera() { return camera; },
  frameView(target, height) {
    cancelPress();
    controls.target.fromArray(target);
    const distance = height * Math.max(1, 0.75 / camera.aspect) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
    camera.position.copy(controls.target); camera.position.z += distance;
    controls.update();
    renderer.render(scene, camera);
  },
  snapshot() {
    return { revision, activePress: Boolean(activePress), meshes: controllers.map((controller, k) => {
      const geometry = controller.dynamicMesh.geometry, position = geometry.getAttribute('position');
      const hair = geometry.getAttribute('_HAIR') || geometry.getAttribute('_hair');
      let delta = 0, hairDelta = 0, finite = true;
      for (let i = 0; i < position.count; i++) {
        let d = 0;
        for (let j = 0; j < 3; j++) { const value = position.array[i * 3 + j]; finite &&= Number.isFinite(value); d += (value - basePositions[k][i * 3 + j]) ** 2; }
        delta = Math.max(delta, Math.sqrt(d)); if (hair?.getX(i) > 0.5) hairDelta = Math.max(hairDelta, Math.sqrt(d));
      }
      return { delta, hairDelta, finite, triangles: geometry.index ? geometry.index.count / 3 : position.count / 3, joints: controller.dynamicMesh.skeleton?.bones.length || 0, morph: controller.dynamicMesh.morphTargetInfluences?.[0] ?? null };
    }) };
  },
  pickPoint(attribute = '_SOFT_UPPER') {
    const mesh = controllers[0].dynamicMesh, geometry = mesh.geometry;
    const weights = geometry.getAttribute(attribute) || geometry.getAttribute(attribute.toLowerCase());
    if (!weights) return null;
    let best = -1, index = -1;
    for (let i = 0; i < weights.count; i++) if (weights.getX(i) > best) { best = weights.getX(i); index = i; }
    root.updateMatrixWorld(true); mesh.getVertexPosition(index, pickScratch).applyMatrix4(mesh.matrixWorld).project(camera);
    const box = renderer.domElement.getBoundingClientRect();
    return { x: box.left + (pickScratch.x + 1) * box.width / 2, y: box.top + (1 - pickScratch.y) * box.height / 2 };
  },
};
showFixture();
renderer.setAnimationLoop((now) => {
  const dt = lastTime === null ? 0 : Math.max(0, Math.min((now - lastTime) / 1000, 0.05)); lastTime = now;
  controllers.forEach((controller) => controller.update(dt));
  root?.updateMatrixWorld(true); controls.update(); renderer.render(scene, camera);
  if (now - statusTime > 700) {
    statusTime = now;
    if (!$('status').textContent.startsWith('Không') && !$('status').textContent.startsWith('Cần')) {
      const snapshot = window.softbodyDemo.snapshot();
      $('status').textContent = `${controllers.length} mesh có vùng động · độ lệch vertex lớn nhất ${Math.max(...snapshot.meshes.map((m) => m.delta)).toFixed(4)} đơn vị local.\n${diagnosticBone ? 'Fixture chẩn đoán, không phải nhân vật.' : 'Asset thật: vẫn cần kiểm tra đa góc, pose và clip.'}`;
    }
  }
});
