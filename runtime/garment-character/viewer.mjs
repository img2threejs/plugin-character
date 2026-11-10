import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createSoftRig } from './softbody.mjs';
import { createPicker } from './picking.mjs';
import { createGarments } from './garment.mjs';
import { roundChestMasks } from './chest-field.mjs';

const $ = (id) => document.getElementById(id);
const names = Object.fromEntries([...$('region').options].map((o) => [o.value, o.textContent]));
window.namiStudio = { ready: false, error: null, build: 'guard-1' };

async function start() {
  const canvas = $('character');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.setClearColor(0xeeeae1, 0);
  // All admitted character materials are opaque. The floor is the sole
  // transparent item; sorting otherwise recomputes posed skin spheres per frame.
  renderer.sortObjects = false;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, .01, 30);
  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, .88, 0);
  controls.enableDamping = true;
  controls.dampingFactor = .1;
  controls.minDistance = .34; controls.maxDistance = 7;
  controls.maxPolarAngle = Math.PI * .92;
  scene.add(new THREE.HemisphereLight(0xffffff, 0xc5b9ad, Math.PI));
  const key = new THREE.DirectionalLight(0xffffff, .45*Math.PI); key.position.set(-3, 5, 4); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffeadb, .10*Math.PI); fill.position.set(3, 2, -2); scene.add(fill);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(.28, 64), new THREE.MeshBasicMaterial({ color: 0x80786a, transparent: true, opacity: .13, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.position.y = -.001; shadow.scale.set(1.25, .60, 1); scene.add(shadow);
  const [gltf, sidecar] = await Promise.all([
    new GLTFLoader().loadAsync('native/export/character.glb'),
    fetch('native/export/softbody.json').then((r) => { if (!r.ok) throw new Error(`Sidecar HTTP ${r.status}`); return r.json(); }),
  ]);
  const root = gltf.scene; scene.add(root); root.updateMatrixWorld(true);
  const modelMeshes = []; root.traverse((o) => { if (o.isMesh) modelMeshes.push(o); });
  if (modelMeshes.some(m => (Array.isArray(m.material)?m.material:[m.material]).some(v=>v.transparent || v.transmission>0))) throw new Error('Asset opacity changed; inspect render ordering before disabling sorting.');
  const body = modelMeshes.find(m=>m.name==='Body');
  if (!body) throw new Error('Không tìm thấy Body đã chuẩn bị.');
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
  // Round, direction-independent chest support; the authored masks still define which
  // bikini vertices belong to each cup.
  const round = roundChestMasks(root, sidecar);
  const rig = createSoftRig(root, round.sidecar);
  const picker = createPicker(modelMeshes, rig.meshes);
  const cupMasks = round.original.BikiniTop;
  const garments = createGarments({ bikini: modelMeshes.find((m) => m.name === 'BikiniTop'), rig,
    membership: { 1: cupMasks['chest-left'], [-1]: cupMasks['chest-right'] },
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches });
  const outfitNames = { green: 'Xanh', orange: 'Cam–trắng' };
  const mixer = new THREE.AnimationMixer(root);
  const clip = gltf.animations.find((a) => a.name.includes('MotionProbe'));
  if (!clip) throw new Error('Export thiếu clip MotionProbe thực; không tạo chuyển động giả thay thế.');
  const action = mixer.clipAction(clip);
  let mode = 'squeeze', motion = false, paused = false, destroyed = false, lastTime, lastUI = 0, frameNumber = 0;
  let currentView = 'quarter', frameHandle = 0;
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
  const views = {
    front: { position: [0, .90, 3.8], target: [0, .88, 0] },
    quarter: { position: [2.25, 1.03, 3.2], target: [0, .88, 0] },
    profile: { position: [3.8, .90, 0], target: [0, .88, 0] },
    rear: { position: [0, .90, -3.8], target: [0, .88, 0] },
    torso: { position: [0, 1.25, 1.24], target: [0, 1.25, 0] },
    hips: { position: [0, .94, -1.24], target: [0, .94, 0] },
    face: { position: [0, 1.61, .73], target: [0, 1.605, 0] },
  };
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
    $('tissue-label').textContent = id.startsWith('cheek') ? 'Căng mượt · giãn nhẹ' : id.startsWith('waist') ? 'Chắc · tắt nhanh' : id === 'abdomen' ? 'Mềm vừa · giảm chấn' : 'Mềm · quán tính';
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
  function reset() { setMotion(false); rig.reset(); garments.reset(); refreshOutfit(); $('status').textContent = 'Trạng thái nghỉ · 9 vùng'; render(); }
  function cast(clientX, clientY) {
    const r = canvas.getBoundingClientRect(); pointer.set((clientX-r.left)/r.width*2-1, -(clientY-r.top)/r.height*2+1);
    raycaster.setFromCamera(pointer, camera); return picker.cast(raycaster);
  }
  // The strap ribbon is ~5 mm wide; search a small ring when the finger lands beside it,
  // but never steal a press that already hits a soft region.
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
  function focusRegion(id) { setView(id.startsWith('hips') ? 'hips' : id.startsWith('cheek') ? 'face' : 'torso'); revealStage(); }
  $('region').addEventListener('change',()=>{refreshProfile();focusRegion($('region').value);});
  $('impulse').addEventListener('click',()=>{const id=$('region').value,p=rig.regions.get(id).profile;focusRegion(id);rig.impulse(id,sharedImpulse.set(0,0,p.cap*2*Math.PI*p.frequency*.65));$('status').textContent='Thử nẩy · '+names[id];});
  $('motion').addEventListener('click',()=>setMotion(!motion)); $('reset').addEventListener('click',reset);
  let outfitPending = false;
  function refreshOutfit() {
    for (const value of ['green','orange']) { const button=$(`outfit-${value}`); button.setAttribute('aria-pressed',String(garments.outfit===value)); button.disabled=garments.transitioning; }
  }
  function setOutfit(value) {
    if (!garments.transformTo(value)) return false;
    releaseAll();
    outfitPending = true; refreshOutfit();
    if (['face','rear','hips'].includes(currentView)) setView('torso');
    revealStage(); $('status').textContent = `Đang biến hình · ${outfitNames[value]}`;
    return true;
  }
  for (const value of ['green','orange']) $(`outfit-${value}`).addEventListener('click',()=>setOutfit(value));
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
    shadow.geometry.dispose();shadow.material.dispose();renderer.dispose();
  }
  setView('quarter');resize();refreshProfile();refreshOutfit();$('loading').hidden=true;$('status').textContent='Sẵn sàng · 9 vùng mô mềm';
  // Variant texture + slip targets are prepared off the interaction path.
  (window.requestIdleCallback ?? ((callback)=>setTimeout(callback,200)))(()=>{ if(!destroyed) garments.prepare(); });
  Object.assign(window.namiStudio,{ready:true,root,rig,garments,camera,renderer,scene,controls,mixer,clip,modelMeshes,pointerEvents,frameTimes,
    setView,locate,setMotion,reset,releaseAll,setSurface,setOutfit,step,render,dispose,getSurface:()=>surface,getMode:()=>mode,getView:()=>currentView,setPaused:(value)=>{paused=Boolean(value);lastTime=undefined;},diagnostics:()=>rig.getDiagnostics()});
  frameHandle=requestAnimationFrame(frame);
}
start().catch((error)=>{window.namiStudio.error=String(error.stack??error);$('loading').hidden=false;$('loading').textContent='Không tải được model: '+error.message;$('status').textContent='Lỗi tải · xem chi tiết';console.error(error);});
