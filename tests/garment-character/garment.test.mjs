// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { Triangle, Vector3 } from 'three';
import { createGarments, limitPull, strapCoordinate, recolorPixels, transitionPhase, fallProfile, TRANSITION } from '../../runtime/garment-character/garment.mjs';
import { createSoftRig } from '../../runtime/garment-character/softbody.mjs';
import { createSyntheticScene } from '../../runtime/garment-character/synthetic-scene.mjs';
import { SYNTHETIC } from '../../runtime/garment-character/synthetic-config.mjs';
import { validateViewerConfig } from '../../runtime/garment-character/calibration.mjs';

function fixture({height}={}) {
  const input=createSyntheticScene({texture:false,height}),config=structuredClone(SYNTHETIC);
  const rig=createSoftRig(input.scene,input.sidecar,config.soft);
  const mesh=input.scene.getObjectByName(config.garment.garmentMesh);
  const garments=createGarments({garment:mesh,rig,calibration:config.garment});
  const entry=rig.meshes.get(mesh.name),body=rig.meshes.get(config.garment.bodyMesh);
  return {input,config,rig,mesh,garments,entry,body,
    step(n){for(let i=0;i<n;i++)garments.update(1/120);garments.apply();},
    dispose(){garments.dispose();rig.dispose();for(const m of [mesh,body.mesh]){m.geometry.dispose();m.material.dispose();}mesh.skeleton.dispose();}};
}
function hit(f,kind,side) {
  const p=f.mesh.geometry.attributes.position,ix=f.mesh.geometry.index.array;
  const tag=f.mesh.geometry.attributes[kind==='strap'?'aStrap':'aPanel'];
  let best=null,distance=Infinity;
  for(let t=0;t<ix.length;t+=3){
    const ids=Array.from(ix.slice(t,t+3));if(!ids.every(i=>tag.getX(i)===side))continue;
    const y=ids.reduce((s,i)=>s+p.getY(i),0)/3;
    const d=Math.abs(y-(kind==='strap'?0.7:0));if(d>=distance)continue;
    const point=new Vector3();for(const i of ids)point.add(new Vector3().fromBufferAttribute(p,i));point.divideScalar(3);
    best={object:f.mesh,faceIndex:t/3,face:{a:ids[0],b:ids[1],c:ids[2]},point};distance=d;
  }
  assert.ok(best,`${kind} side ${side} has real triangles`);return best;
}
// Independent exhaustive nearest-triangle measurement, including triangle centres.
function clearance(f) {
  const positions=f.mesh.geometry.attributes.position,ix=f.mesh.geometry.index.array;
  const skin=f.body.positions,bi=f.body.indices,triangles=[];
  for(let t=0;t<bi.length;t+=3){const tri=new Triangle(...[0,1,2].map(k=>new Vector3().fromArray(skin,bi[t+k]*3)));triangles.push([tri,tri.getNormal(new Vector3())]);}
  const samples=[];
  for(let i=0;i<positions.count;i++)samples.push(new Vector3().fromBufferAttribute(positions,i));
  for(let t=0;t<ix.length;t+=3)samples.push(new Vector3().fromBufferAttribute(positions,ix[t]).add(new Vector3().fromBufferAttribute(positions,ix[t+1])).add(new Vector3().fromBufferAttribute(positions,ix[t+2])).divideScalar(3));
  let lowest=Infinity;const q=new Vector3(),delta=new Vector3();
  for(const p of samples){let distance=Infinity,height=Infinity;for(const [tri,n] of triangles){tri.closestPointToPoint(p,q);const d=p.distanceToSquared(q);if(d<distance){distance=d;height=delta.subVectors(p,q).dot(n);}}lowest=Math.min(lowest,height);}
  return lowest;
}

test('calibration is explicit and invalid inputs are refused before geometry mutation',()=>{
  assert.equal(validateViewerConfig(structuredClone(SYNTHETIC)).synthetic,true);
  assert.throws(()=>createGarments({}),/configuration required/);
  assert.throws(()=>createSoftRig(null,null),/explicit calibration/);
  assert.throws(()=>strapCoordinate(0,0,0),/explicit/);
  assert.throws(()=>limitPull(new Vector3(),new Vector3()),/explicit/);
  for(const change of [c=>delete c.garment.contact,c=>c.garment.strap.yTop=c.garment.strap.yAttach,c=>c.soft.profiles.chest.cap=NaN,c=>delete c.views.front,c=>c.synthetic=false]){
    const c=structuredClone(SYNTHETIC);change(c);assert.throws(()=>validateViewerConfig(c));
  }
});

test('timeline releases before falling, recolors while fallen, reseats and honors reduced motion',()=>{
  let previous=0;
  for(let t=0;t<=TRANSITION.duration;t+=0.01){const p=transitionPhase(t);assert.ok(p.morph>=previous);previous=p.morph;if(p.fold>0)assert.equal(p.cut,1);if(p.morph>0&&p.morph<1)assert.ok(p.fold>0.8);}
  assert.equal(transitionPhase(TRANSITION.duration).done,true);
  for(let t=0;t<=0.4;t+=0.02){const p=transitionPhase(t,true);assert.deepEqual([p.fold,p.cut,p.glow],[0,0,0]);}
  assert.equal(fallProfile(0),0);assert.equal(fallProfile(1),1);assert.ok(fallProfile(0.75)<1);
});

test('coordinates and pull resistance use caller dimensions rather than scene names or old defaults',()=>{
  const s=SYNTHETIC.garment.strap;
  assert.equal(strapCoordinate(0.3,0.7,0,s).side,1);assert.equal(strapCoordinate(-0.3,0.7,0,s).side,-1);
  assert.equal(strapCoordinate(0.3,0.2,0,s).side,0);
  const n=new Vector3(0,0,1),d=limitPull(new Vector3(2,0,-2),n,s.maxPull);
  assert.equal(d.z,0);assert.ok(d.length()<=s.maxPull&&d.length()>s.maxPull*0.99);
});

test('independently authored blue texture changes only within the supplied color interval',()=>{
  const pixels=new Uint8ClampedArray([36,92,219,255,238,238,238,255,200,60,60,255]);
  recolorPixels(pixels,SYNTHETIC.garment.colorway);
  assert.ok(pixels[0]>pixels[2]&&pixels[1]>pixels[2]);assert.deepEqual([...pixels.slice(4)],[238,238,238,255,200,60,60,255]);
});

for(const kind of ['strap','panel'])for(const side of [1,-1])test(`${kind} ${side}: actual connected cloth, hard pulls in four directions, hold/rebound/settle and outer-layer probes`,()=>{
  const f=fixture(),g=f.garments,h=hit(f,kind,side),grab=kind==='strap'?g.grabStrap:g.grabPanel,drag=kind==='strap'?g.dragStrap:g.dragPanel,release=kind==='strap'?g.releaseStrap:g.releasePanel;
  const limit=f.config.garment[kind==='strap'?'strap':'panel'].maxPull;
  for(const direction of [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0]]){
    g.reset();g.apply();assert.ok(grab(h,side));
    assert.equal((kind==='strap'?g.grabPanel:g.grabStrap)(hit(f,kind==='strap'?'panel':'strap',side),side),false,'same-side captures cannot overwrite tension');
    drag(side,h.point.clone().add(new Vector3(...direction).multiplyScalar(2)));
    f.step(90);
    const state=(kind==='strap'?g.getState().straps:g.getState().panels).find(p=>p.side===side),length=Math.hypot(...state.offset);
    assert.ok(length>=limit*0.7&&length<=limit*1.001,'hard pull is real and bounded');
    const weights=g.influence(kind,side);assert.ok(weights.some(w=>w>0)&&weights.some(w=>w===0),'connected field is neither empty nor global full weight');
    assert.ok(clearance(f)>=0.0001,'all vertices AND face centres stay strictly above the support while held');
    assert.deepEqual(f.entry.positions,f.entry.rest,'render deformation does not modify soft solver rest');
    release(side);f.step(30);assert.ok(clearance(f)>=0.0001,'rebound stays above support');
    f.step(900);assert.deepEqual(f.mesh.geometry.attributes.position.array,f.entry.rest,'release restores exact rest');
  }
  g.applyPhase({fold:1,cut:1,glow:0,morph:0});g.apply();
  assert.ok(f.mesh.geometry.attributes.position.array.some((v,i)=>Math.abs(v-f.entry.rest[i])>0.001),'release/fold actually moves cloth');
  g.reset();g.apply();assert.deepEqual(f.mesh.geometry.attributes.position.array,f.entry.rest);
  f.dispose();
});

test('contact and outer-layer guard handle an independently authored sharp tent ridge',()=>{
  const f=fixture({height:(x,y)=>0.15*Math.max(0,1-Math.abs(x-0.25)/0.15)}),g=f.garments;
  let measured=0;
  for(const direction of [[1,0,0],[-1,0,0],[1,1,0],[-1,-1,0]]){
    g.reset();g.apply();const h=hit(f,'panel',1);assert.ok(g.grabPanel(h,1));
    g.dragPanel(1,h.point.clone().add(new Vector3(...direction)));
    f.step(90);measured+=g.getState().skinGuard.measuredTriangles;
    assert.ok(clearance(f)>=0.0001,'independent nearest-triangle probe includes ridge-crossing face centres');
    g.releasePanel(1);f.step(30);assert.ok(clearance(f)>=0.0001);
    f.step(900);assert.deepEqual(f.mesh.geometry.attributes.position.array,f.entry.rest);
  }
  assert.ok(measured>0,'ridge really exercises the triangle guard, not only flat contact');
  f.dispose();
});

test('probe negative control detects under-surface cloth rather than a fake clean result',()=>{
  const f=fixture(),p=f.mesh.geometry.attributes.position;
  for(let i=0;i<p.count;i++)p.setZ(i,p.getZ(i)-0.1);
  assert.ok(clearance(f)<-0.05);f.dispose();
});
