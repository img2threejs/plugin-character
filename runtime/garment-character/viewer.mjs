import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createSoftRig } from './softbody.mjs';
import { createPicker } from './picking.mjs';
import { createGarments } from './garment.mjs';
import { roundChestMasks } from './chest-field.mjs';
import { SYNTHETIC } from './synthetic-config.mjs';
import { createSyntheticScene } from './synthetic-scene.mjs';
import { validateViewerConfig } from './calibration.mjs';

const $ = (id) => document.getElementById(id);
let names;
window.garmentStudio = { ready: false, error: null, build: 'synthetic-1' };

async function start() {
  const configURL = new URLSearchParams(location.search).get('config');
  const config = validateViewerConfig(configURL ? await fetch(configURL).then(r => {
    if (!r.ok) throw new Error(`Configuration HTTP ${r.status}`); return r.json();
  }) : structuredClone(SYNTHETIC));
  if (configURL && config.synthetic) throw new Error('Caller configurations must select real inputs; the synthetic demo is the default page only.');
  document.querySelector('.subtitle').textContent = config.label;
  document.title = config.synthetic ? 'Garment — Synthetic Mechanics Studio' : 'Garment — Caller Input';
  document.querySelector('.edition').textContent = config.synthetic ? 'SYNTHETIC DEMO / 01' : 'CALLER INPUT';
  for (const [i, option] of [...$('region').options].entries()) if (config.synthetic) option.textContent = `Vùng hình học ${i+1}`;
  names = Object.fromEntries([...$('region').options].map(o => [o.value,o.textContent]));
  for (const [i,id] of config.garment.outfits.entries()) $(`outfit-${i}`).textContent = config.outfitLabels[id];
  const canvas = $('character');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.setClearColor(config.background, 0);
  // Sorting is disabled only for the opaque input contract checked below.
  renderer.sortObjects = false;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(config.camera.fov, 1, config.camera.near, config.camera.far);
  const controls = new OrbitControls(camera, canvas);
  controls.target.fromArray(config.views[config.initialView].target);
  controls.enableDamping = true;
  controls.dampingFactor = .1;
  controls.minDistance = config.camera.minDistance; controls.maxDistance = config.camera.maxDistance;
  controls.maxPolarAngle = Math.PI * .92;
  scene.add(new THREE.HemisphereLight(config.lights.sky, config.lights.ground, Math.PI));
  const key = new THREE.DirectionalLight(config.lights.key, .45*Math.PI); key.position.set(-3, 5, 4); scene.add(key);
  const fill = new THREE.DirectionalLight(config.lights.fill, .10*Math.PI); fill.position.set(3, 2, -2); scene.add(fill);
  const generated = config.synthetic ? createSyntheticScene() : null;
  const [gltf, sidecar] = generated ? [generated, generated.sidecar] : await Promise.all([
    new GLTFLoader().loadAsync(config.glb),
    fetch(config.sidecar).then((r) => { if (!r.ok) throw new Error(`Sidecar HTTP ${r.status}`); return r.json(); }),
  ]);
  const root = gltf.scene; scene.add(root); root.updateMatrixWorld(true);
  const modelMeshes = []; root.traverse((o) => { if (o.isMesh) modelMeshes.push(o); });
  if (modelMeshes.some(m => (Array.isArray(m.material)?m.material:[m.material]).some(v=>v.transparent || v.transmission>0))) throw new Error('Asset opacity changed; inspect render ordering before disabling sorting.');
  const body = modelMeshes.find(m=>m.name===config.garment.bodyMesh);
  if (!body) throw new Error('Không tìm thấy mesh hỗ trợ đã cấu hình.');
  const nativeSkinMaterial = body.material;
  const sourceSkinMaterial = new THREE.MeshBasicMaterial({ map:nativeSkinMaterial.map, color:nativeSkinMaterial.color, side:nativeSkinMaterial.side });
  sourceSkinMaterial.name = 'Artist unlit color comparison';
  let surface = 'skin';
  function setSurface(value) {
    if (value !== 'skin' && value !== 'artist') throw new Error('Unknown surface mode');
    surface=value; body.material=value==='artist'?sourceSkinMaterial:nativeSkinMaterial;
    $('surface').value=value; render();
  }
  $('surface').addEventListener('change',()=>setSurface($('surface').value));
  const round = roundChestMasks(root, sidecar, config.round);
  const rig = createSoftRig(root, round.sidecar, config.soft);
  const picker = createPicker(modelMeshes, rig.meshes);
  const cupMasks = round.original[config.garment.garmentMesh];
  if (!cupMasks) throw new Error('Configured garment has no calibrated round-region masks');
  const garments = createGarments({ garment: modelMeshes.find((m) => m.name === config.garment.garmentMesh), rig,
    calibration: config.garment,
    membership: { 1: cupMasks[config.garment.regions[1]], [-1]: cupMasks[config.garment.regions[-1]] },
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches });
  const outfitNames = config.outfitLabels;
  const mixer = new THREE.AnimationMixer(root);
  const clip = gltf.animations.find((a) => a.name === config.clip);
  if (!clip) throw new Error(`Thiếu clip đã cấu hình: ${config.clip}`);
  const action = mixer.clipAction(clip);
  let mode = 'squeeze', motion = false, paused = false, destroyed = false, lastTime, lastUI = 0, frameNumber = 0;
  let currentView = config.initialView, frameHandle = 0;
  const frameTimes = new Float32Array(240), pointerEvents = [], contacts = new Map();
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2(), planePoint = new THREE.Vector3(), planeNormal = new THREE.Vector3();
  const sharedImpulse = new THREE.Vector3();
  function eventLog(event, type, id = null) {
    pointerEvents.push({ type, id, pointerId: event.pointerId, pointerType: event.pointerType, trusted: event.isTrusted, time: performance.now() });
    if (pointerEvents.length > 256) pointerEvents.shift();
  }
  function render() { garments.apply(); renderer.render(scene, camera); }
  function resize() {
    const rect = canvas.getBoundingClientRect(); renderer.setSize(rect.width, rect.height, false);
    camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix(); render();
  }
  const observer = new ResizeObserver(resize); observer.observe(canvas);
  const views = config.views;
  for (const button of document.querySelectorAll('[data-view]')) button.hidden = !views[button.dataset.view];
  function setView(name) {
    const view = views[name]; if (!view) throw new Error('Unknown view ' + name);
    releaseAll(); currentView = name;
    document.querySelector('.stage').classList.toggle('face-view', name === 'face');
    controls.enableDamping = false; controls.target.fromArray(view.target); camera.position.fromArray(view.position); controls.update(); controls.enableDamping = true;
    for (const button of document.querySelectorAll('[data-view]')) button.setAttribute('aria-pressed', String(button.dataset.view === name));
    render();
  }
  function refreshProfile() {
    const id = $('region').value, p = rig.regions.get(id).profile;
    $('frequency').textContent = p.frequency.toFixed(1) + ' Hz'; $('damping').textContent = p.dampingRatio.toFixed(2);
    $('tissue-label').textContent = config.synthetic ? 'Chế độ cơ học · không phải mô sinh học' : 'Thông số từ cấu hình đầu vào';
  }
  function releaseAll() {
    rig.releaseAll(); garments.releaseAll();
    for (const id of contacts.keys()) if (canvas.hasPointerCapture(id)) canvas.releasePointerCapture(id);
    contacts.clear(); controls.enabled = true; canvas.style.cursor = '';
  }
  function setMotion(enabled) {
    releaseAll(); motion = enabled;
    if (enabled) action.reset().play(); else { action.stop(); mixer.update(0); }
    root.updateMatrixWorld(true); rig.reset();
    $('motion').setAttribute('aria-pressed', String(enabled));
    $('motion').innerHTML = `<span class="play-icon" aria-hidden="true">${enabled ? 'Ⅱ' : '▷'}</span> ${enabled ? 'Dừng chuyển động' : 'Chuyển động thử'}`;
  }
  function reset() { setMotion(false); rig.reset(); garments.reset(); refreshOutfit(); $('status').textContent = config.label; render(); }
  function cast(clientX, clientY) {
    const r = canvas.getBoundingClientRect(); pointer.set((clientX-r.left)/r.width*2-1, -(clientY-r.top)/r.height*2+1);
    raycaster.setFromCamera(pointer, camera); return picker.cast(raycaster);
  }
  // Search a small screen-space ring for narrow cloth, without stealing tissue hits.
  function strapNear(event, hit) {
    const side = garments.strapSide(hit);
    if (side) return { hit, side };
    if (hit && rig.pick(hit)) return null;
    const radii = event.pointerType === 'touch' ? [5, 10, 15] : [4, 8];
    for (const radius of radii) for (let k = 0; k < 8; k++) {
      const angle = k * Math.PI / 4, near = cast(event.clientX + Math.cos(angle) * radius, event.clientY + Math.sin(angle) * radius);
      const nearSide = garments.strapSide(near);
      if (nearSide) return { hit: near, side: nearSide };
    }
    return null;
  }
  function down(event) {
    if (event.button !== 0 && event.pointerType !== 'touch') return;
    if (garments.transitioning) return;
    const hit = cast(event.clientX, event.clientY), strapHit = strapNear(event, hit), strap = strapHit?.side;
    if (strap) {
      camera.getWorldDirection(planeNormal);
      const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, strapHit.hit.point);
      // Anchor at the actual pointer on the drag plane so a ring-picked strap does not jump.
      const r = canvas.getBoundingClientRect(); pointer.set((event.clientX-r.left)/r.width*2-1, -(event.clientY-r.top)/r.height*2+1); raycaster.setFromCamera(pointer, camera);
      if (!garments.grabStrap(strapHit.hit, strap, raycaster.ray.intersectPlane(plane, planePoint) ?? strapHit.hit.point)) return;
      event.preventDefault(); event.stopImmediatePropagation();
      contacts.set(event.pointerId, { strap, id: 'strap', plane });
      controls.enabled = false; canvas.setPointerCapture(event.pointerId); canvas.style.cursor = 'grabbing';
      $('status').textContent = 'Đang kéo dây áo'; eventLog(event, 'grab', 'strap');
      return;
    }
    if (mode === 'fabric') {
      const panel = garments.panelSide(hit);
      if (!panel) return;
      camera.getWorldDirection(planeNormal);
      const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, hit.point);
      if (!garments.grabPanel(hit, panel)) return;
      event.preventDefault(); event.stopImmediatePropagation();
      contacts.set(event.pointerId, { panel, id: 'fabric', plane });
      controls.enabled = false; canvas.setPointerCapture(event.pointerId); canvas.style.cursor = 'grabbing';
      $('status').textContent = 'Đang kéo mảnh vải áo'; eventLog(event, 'grab', 'fabric');
      return;
    }
    const id = hit && rig.pick(hit);
    if (!id) return;
    const token = rig.grab(hit, event.pointerId, { mode }); if (!token) return;
    event.preventDefault(); event.stopImmediatePropagation();
    camera.getWorldDirection(planeNormal);
    contacts.set(event.pointerId, { token, id, plane: new THREE.Plane().setFromNormalAndCoplanarPoint(planeNormal, hit.point) });
    controls.enabled = false; canvas.setPointerCapture(event.pointerId); canvas.style.cursor = 'grabbing';
    $('region').value = id; refreshProfile(); $('status').textContent = `${mode === 'squeeze' ? 'Đang bóp' : 'Đang kéo'} · ${names[id]}`;
    eventLog(event, 'grab', id);
  }
  function move(event) {
    const contact = contacts.get(event.pointerId);
    if (contact) {
      event.preventDefault(); event.stopImmediatePropagation();
      const r=canvas.getBoundingClientRect(); pointer.set((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1); raycaster.setFromCamera(pointer,camera);
      if (raycaster.ray.intersectPlane(contact.plane, planePoint)) {
        if (contact.strap) garments.dragStrap(contact.strap, planePoint);
        else if (contact.panel) garments.dragPanel(contact.panel, planePoint);
        else rig.drag(contact.token, planePoint);
      }
    }
  }
  function up(event) {
    const contact=contacts.get(event.pointerId); if(!contact)return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (contact.strap) garments.releaseStrap(contact.strap);
    else if (contact.panel) garments.releasePanel(contact.panel);
    else rig.release(contact.token);
    contacts.delete(event.pointerId);
    eventLog(event,event.type==='pointercancel'?'cancel':event.type==='lostpointercapture'?'lost-capture':'release',contact.id);
    if(canvas.hasPointerCapture(event.pointerId))canvas.releasePointerCapture(event.pointerId);
    controls.enabled=contacts.size===0; if(!contacts.size)canvas.style.cursor='';
    $('status').textContent=contact.strap?'Đã thả dây áo · ngực đàn hồi':contact.panel?'Đã thả mảnh vải · áo hồi phục':'Đã thả · quan sát hồi phục';
  }
  canvas.addEventListener('pointerdown',down,{capture:true}); canvas.addEventListener('pointermove',move,{capture:true});
  for(const type of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(type,up,{capture:true});
  window.addEventListener('blur',releaseAll);
  document.addEventListener('visibilitychange',()=>{if(document.hidden){releaseAll();lastTime=undefined;}});
  for(const button of document.querySelectorAll('[data-view]'))button.addEventListener('click',()=>setView(button.dataset.view));
  function revealStage() { if (innerWidth<=850) document.querySelector('.stage').scrollIntoView({block:'start',behavior:'auto'}); }
  for(const value of ['squeeze','grab','fabric'])$(value).addEventListener('click',()=>{releaseAll();mode=value;for(const v of ['squeeze','grab','fabric'])$(v).setAttribute('aria-pressed',String(v===mode));revealStage();});
  function focusRegion(id) { setView(config.regionViews[id]); revealStage(); }
  $('region').addEventListener('change',()=>{refreshProfile();focusRegion($('region').value);});
  $('impulse').addEventListener('click',()=>{const id=$('region').value,p=rig.regions.get(id).profile;focusRegion(id);rig.impulse(id,sharedImpulse.set(0,0,p.cap*2*Math.PI*p.frequency*.65));$('status').textContent='Thử nẩy · '+names[id];});
  $('motion').addEventListener('click',()=>setMotion(!motion)); $('reset').addEventListener('click',reset);
  let outfitPending = false;
  function refreshOutfit() {
    for (const [i,value] of config.garment.outfits.entries()) { const button=$(`outfit-${i}`); button.setAttribute('aria-pressed',String(garments.outfit===value)); button.disabled=garments.transitioning; }
  }
  function setOutfit(value) {
    if (!garments.transformTo(value)) return false;
    releaseAll();
    outfitPending = true; refreshOutfit();
    setView(config.initialView);
    revealStage(); $('status').textContent = `Đang biến hình · ${outfitNames[value]}`;
    return true;
  }
  for (const [i,value] of config.garment.outfits.entries()) $(`outfit-${i}`).addEventListener('click',()=>setOutfit(value));
  function step(dt) {
    if(motion)mixer.update(dt); root.updateMatrixWorld(true); garments.update(dt); rig.update(dt);
    if (outfitPending && !garments.transitioning) { outfitPending=false; refreshOutfit(); $('status').textContent=`Trang phục · ${outfitNames[garments.outfit]}`; }
    render();
  }
  function frame(time) {
    if(destroyed)return;
    // The solver owns its substep cap. Keep wall-clock animation and FPS honest.
    const dt=lastTime===undefined?1/60:Math.max(.001,(time-lastTime)/1000);lastTime=time;
    if(!paused){if(controls.enabled)controls.update();step(dt);}
    else render();
    frameTimes[frameNumber++%frameTimes.length]=dt*1000;
    if(time-lastUI>400){const active=rig.getDiagnostics().contactCount;$('performance').textContent=Math.round(1/dt)+' FPS';if(!active&&motion)$('status').textContent='Rig chuyển động · mô phản hồi quán tính';lastUI=time;}
    frameHandle=requestAnimationFrame(frame);
  }
  function locate(id) {
    // Actual posed exported triangles and first visible ray hit, not guessed UI coordinates.
    const candidates=[],p=new THREE.Vector3(),a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
    root.updateMatrixWorld(true);camera.updateMatrixWorld(true);
    for(const entry of rig.meshes.values()){
      const mask=entry.masks.get(id);if(!mask)continue;
      for(let i=0;i<entry.indices.length;i+=3){const ia=entry.indices[i],ib=entry.indices[i+1],ic=entry.indices[i+2];const weight=(mask[ia]+mask[ib]+mask[ic])/3;if(weight<.04)continue;
        entry.mesh.getVertexPosition(ia,a);entry.mesh.getVertexPosition(ib,b);entry.mesh.getVertexPosition(ic,c);p.copy(a).add(b).add(c).multiplyScalar(1/3).applyMatrix4(entry.mesh.matrixWorld).project(camera);
        if(Math.abs(p.x)>.96||Math.abs(p.y)>.96||p.z< -1||p.z>1)continue;
        candidates.push({x:p.x,y:p.y,weight,mesh:entry.mesh.name});}
    }
    candidates.sort((a,b)=>b.weight-a.weight);
    const rect=canvas.getBoundingClientRect();
    for(const candidate of candidates.slice(0,500)){
      const x=rect.left+(candidate.x+1)*.5*rect.width,y=rect.top+(1-candidate.y)*.5*rect.height;
      const hit=cast(x,y);if(hit&&rig.pick(hit)===id)return {x,y,mesh:hit.object.name,weight:candidate.weight,id};
    }
    return null;
  }
  function dispose() {
    if(destroyed)return;destroyed=true;cancelAnimationFrame(frameHandle);releaseAll();garments.dispose();rig.dispose();controls.dispose();observer.disconnect();
    canvas.removeEventListener('pointerdown',down,true);canvas.removeEventListener('pointermove',move,true);for(const type of ['pointerup','pointercancel','lostpointercapture'])canvas.removeEventListener(type,up,true);window.removeEventListener('blur',releaseAll);
    const materials=new Set(modelMeshes.flatMap(m=>Array.isArray(m.material)?m.material:[m.material]));
    materials.add(nativeSkinMaterial); materials.add(sourceSkinMaterial);
    const textures=new Set(); for(const material of materials)for(const value of Object.values(material))if(value?.isTexture)textures.add(value);
    for(const value of textures)value.dispose(); for(const material of materials)material.dispose();
    for(const geometry of new Set(modelMeshes.map(m=>m.geometry)))geometry.dispose();
    for(const skeleton of new Set(modelMeshes.filter(m=>m.isSkinnedMesh).map(m=>m.skeleton)))skeleton.dispose();
    renderer.dispose();
  }
  setView(config.initialView);resize();refreshProfile();refreshOutfit();
  // Preparation failures must be reported before ready, never hidden in an idle callback.
  garments.prepare();
  $('loading').hidden=true;$('status').textContent=config.label;
  Object.assign(window.garmentStudio,{ready:true,config,root,rig,garments,camera,renderer,scene,controls,mixer,clip,modelMeshes,pointerEvents,frameTimes,
    setView,locate,setMotion,reset,releaseAll,setSurface,setOutfit,step,render,dispose,getSurface:()=>surface,getMode:()=>mode,getView:()=>currentView,setPaused:(value)=>{paused=Boolean(value);lastTime=undefined;},diagnostics:()=>rig.getDiagnostics()});
  frameHandle=requestAnimationFrame(frame);
}
start().catch((error)=>{window.garmentStudio.ready=false;window.garmentStudio.error=String(error.stack??error);$('loading').hidden=false;$('loading').textContent='Không thể khởi tạo: '+error.message+' · Kiểm tra cấu hình đầu vào.';$('status').textContent='Cấu hình hoặc dữ liệu không hợp lệ';console.error(error);});
