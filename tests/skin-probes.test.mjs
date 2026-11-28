// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from 'three';

const source=await readFile(new URL('../tools/skin_probes.js',import.meta.url),'utf8');
const triangle=(r,z)=>[-r,-r,z,r,-r,z,0,r,z];
async function measure(bodyPoints,translation=[0,0,0]){
 const bodyGeometry=new THREE.BufferGeometry();bodyGeometry.setAttribute('position',new THREE.Float32BufferAttribute(bodyPoints,3));bodyGeometry.setIndex(Array.from({length:bodyPoints.length/3},(_,i)=>i));
 const clothGeometry=new THREE.BufferGeometry();clothGeometry.setAttribute('position',new THREE.Float32BufferAttribute(triangle(.001,-.001),3));clothGeometry.setIndex([0,1,2]);
 clothGeometry.setAttribute('aStrap',new THREE.Float32BufferAttribute([0,0,0,0,0,0],2));clothGeometry.setAttribute('aPanel',new THREE.Float32BufferAttribute([1,0,1,0,1,0],2));
 const body=new THREE.Mesh(bodyGeometry),cloth=new THREE.Mesh(clothGeometry);body.name='TestSupport';cloth.name='TestCloth';
 const root=new THREE.Group();root.position.fromArray(translation);root.add(body,cloth);root.updateMatrixWorld(true);
 const studio={ready:true,config:{garment:{bodyMesh:body.name,garmentMesh:cloth.name,strap:{yAttach:0.5,minZ:0}}},modelMeshes:[body,cloth],rig:{meshes:new Map([[cloth.name,{rest:clothGeometry.attributes.position.array}]])}};
 const window={garmentStudio:studio};
 new Function('window','__omp_import__',source)(window,async()=>THREE);
 try{return await window.__inside({faces:true});}
 finally{bodyGeometry.dispose();clothGeometry.dispose();body.material.dispose();cloth.material.dispose();}
}

for(const fixture of [
 {name:'crossing triangle remains measurable when every vertex lies outside the coarse ROI',points:triangle(.1,0),depth:1},
 {name:'a nearer wide triangle wins over an outside skin layer already found within60mm',points:[...triangle(.005,-.04),...triangle(.05,0)],depth:1},
 {name:'world-space translated skin and cloth retain the same penetration measurement',points:triangle(.02,0),translation:[3,2,-4],depth:1},
 {name:'cloth farther than the coarse ROI still gets an exact nearest-skin measurement',points:triangle(.1,.1),depth:101},
])test(fixture.name,async()=>{
 const result=await measure(fixture.points,fixture.translation);
 assert.equal(result.samples,4,'all three cloth vertices and the triangle centre must be examined');
 assert.equal(result.insideSkin,4,'a coarse search must not silently turn inward cloth into a clean result');
 assert.ok(Math.abs(result.deepestMm-fixture.depth)<.01,`expected${fixture.depth}mm, observed${result.deepestMm}mm`);
});

test('probes refuse an unready or uncalibrated input instead of returning clean',async()=>{
 const window={garmentStudio:{ready:false}};
 new Function('window','__omp_import__',source)(window,async()=>THREE);
 await assert.rejects(window.__inside({faces:true}),/ready calibrated input/);
 window.garmentStudio.ready=true;
 await assert.rejects(window.__inside({faces:true}),/ready calibrated input/);
});
