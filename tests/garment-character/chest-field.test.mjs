// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { BufferGeometry, Float32BufferAttribute, Group, Mesh } from 'three';
import { roundChestMasks, roundChestWeight } from '../../runtime/garment-character/chest-field.mjs';
import { SYNTHETIC } from '../../runtime/garment-character/synthetic-config.mjs';
function fixture(points){
  const geometry=new BufferGeometry(),positions=[0.5,0,0,-0.5,0,0,...points.flat()],count=positions.length/3;
  geometry.setAttribute('position',new Float32BufferAttribute(positions,3));
  const left=new Float32Array(count),right=new Float32Array(count);left[0]=1;right[1]=1;
  geometry.setAttribute('left',new Float32BufferAttribute(left,1));geometry.setAttribute('right',new Float32BufferAttribute(right,1));
  const mesh=new Mesh(geometry);mesh.name='TestSurface';const root=new Group();root.add(mesh);
  return {root,geometry,sidecar:{meshes:[{name:mesh.name,regions:[{id:'chest-left',attribute:'left'},{id:'chest-right',attribute:'right'}]}]},dispose(){geometry.dispose();mesh.material.dispose();}};
}
test('round fields have direction-independent falloff in explicit input units',()=>{
  const points=Array.from({length:8},(_,i)=>[0.5+0.25*Math.cos(i*Math.PI/4),0.25*Math.sin(i*Math.PI/4),0]);
  const f=fixture(points),c={...SYNTHETIC.round,midline:-1};roundChestMasks(f.root,f.sidecar,c);
  const weights=f.geometry.attributes.left_ROUND;
  for(let i=2;i<weights.count;i++)assert.ok(Math.abs(weights.getX(i)-roundChestWeight(0.25,c.plateau,c.reach))<1e-5);
  f.dispose();
});
test('explicit medial and depth exclusion, shared support and original paint preservation',()=>{
  const f=fixture([[0,0,0],[0.5,0,-1]]),before=f.geometry.attributes.left.array.slice();
  const result=roundChestMasks(f.root,f.sidecar,SYNTHETIC.round);
  assert.equal(f.geometry.attributes.left_ROUND.getX(0),1);assert.equal(f.geometry.attributes.left_ROUND.getX(2),0);assert.equal(f.geometry.attributes.left_ROUND.getX(3),0);
  assert.deepEqual(f.geometry.attributes.left.array,before);assert.equal(f.sidecar.meshes[0].regions[0].attribute,'left');
  assert.equal(result.sidecar.meshes[0].regions[0].attribute,'left_ROUND');
  assert.deepEqual(result.original.TestSurface['chest-left'],before);
  roundChestMasks(f.root,f.sidecar,{...SYNTHETIC.round,plateau:1,reach:2,midline:-1});
  assert.equal(f.geometry.attributes.left_ROUND.getX(2),0.5);assert.equal(f.geometry.attributes.right_ROUND.getX(2),0.5);
  f.dispose();
});
test('missing and invalid round calibration cannot silently reuse a case',()=>{
  const f=fixture([]);
  assert.throws(()=>roundChestMasks(f.root,f.sidecar),/configuration required/);
  assert.throws(()=>roundChestMasks(f.root,f.sidecar,{...SYNTHETIC.round,reach:0.1}),/reach must exceed/);
  assert.throws(()=>roundChestWeight(0.2),/explicit/);f.dispose();
});
