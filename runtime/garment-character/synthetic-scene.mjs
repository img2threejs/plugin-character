// SPDX-License-Identifier: Apache-2.0
// Project-authored primitives: a Cartesian support grid, a connected rectangular
// cloth grid, one bone and a translation clip. This is not an anatomical model.
import { AnimationClip, Bone, BufferGeometry, CanvasTexture, Float32BufferAttribute, Group, MeshStandardMaterial, Skeleton, SkinnedMesh, SRGBColorSpace, Uint16BufferAttribute, VectorKeyframeTrack } from 'three';
import { REGION_IDS } from './softbody.mjs';
import { SYNTHETIC } from './synthetic-config.mjs';

export const BOARD = { min:-1.2, max:1.2, divisions:24 };
export const CLOTH = { minX:-0.5,maxX:0.5,minY:-0.6,maxY:1,columns:10,rows:16,gap:0.012 };
const centers = [[0.4,0],[-0.4,0],[0.4,-0.8],[-0.4,-0.8],[0.8,-0.4],[-0.8,-0.4],[0,-0.4],[0.4,0.8],[-0.4,0.8]];
export const supportHeight = (x,y) => 0.02 * Math.cos(Math.PI*x/2.4) * Math.cos(Math.PI*y/2.4);
function grid(x0,x1,y0,y1,nx,ny,gap,height) {
  const positions=[],uv=[],indices=[];
  for(let j=0;j<=ny;j++)for(let i=0;i<=nx;i++){
    const x=x0+(x1-x0)*i/nx,y=y0+(y1-y0)*j/ny;
    positions.push(x,y,height(x,y)+gap);uv.push(i/nx,j/ny);
  }
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
    const a=j*(nx+1)+i,b=a+1,c=a+nx+1,d=c+1;indices.push(a,b,c,b,d,c);
  }
  const g=new BufferGeometry();g.setAttribute('position',new Float32BufferAttribute(positions,3));
  g.setAttribute('uv',new Float32BufferAttribute(uv,2));g.setIndex(indices);g.computeVertexNormals();
  const count=positions.length/3;
  g.setAttribute('skinIndex',new Uint16BufferAttribute(new Uint16Array(count*4),4));
  g.setAttribute('skinWeight',new Float32BufferAttribute(Array.from({length:count*4},(_,i)=>i%4===0?1:0),4));
  return g;
}
export function createSyntheticScene({texture=true,height=supportHeight}={}) {
  const root=new Group(),bone=new Bone();bone.name='BoardAnchor';root.add(bone);
  const skeleton=new Skeleton([bone]);
  const bodyGeometry=grid(BOARD.min,BOARD.max,BOARD.min,BOARD.max,BOARD.divisions,BOARD.divisions,0,height);
  const clothGeometry=grid(CLOTH.minX,CLOTH.maxX,CLOTH.minY,CLOTH.maxY,CLOTH.columns,CLOTH.rows,CLOTH.gap,height);
  let map=null;
  if(texture){
    const canvas=document.createElement('canvas');canvas.width=canvas.height=32;
    const c=canvas.getContext('2d');c.fillStyle='#245cdb';c.fillRect(0,0,32,32);
    c.fillStyle='#eeeeee';c.fillRect(0,14,32,4);map=new CanvasTexture(canvas);map.flipY=false;map.colorSpace=SRGBColorSpace;
  }
  const body=new SkinnedMesh(bodyGeometry,new MeshStandardMaterial({color:0xa8b5c4,roughness:0.8}));body.name=SYNTHETIC.garment.bodyMesh;
  const cloth=new SkinnedMesh(clothGeometry,new MeshStandardMaterial({map,color:map?0xffffff:0x245cdb,roughness:0.9}));cloth.name=SYNTHETIC.garment.garmentMesh;
  root.add(body,cloth);root.updateMatrixWorld(true);body.bind(skeleton);cloth.bind(skeleton);
  const specs=[];
  for(const mesh of [body,cloth]){
    const p=mesh.geometry.attributes.position,regions=[];
    for(let r=0;r<REGION_IDS.length;r++){
      if(mesh===cloth && r>1)continue;
      const values=new Float32Array(p.count),attribute=`region_${r}`;
      for(let i=0;i<p.count;i++){
        const x=p.getX(i),y=p.getY(i);
        values[i]=mesh===cloth ? (y> CLOTH.minY+0.05 && y<0.4 && (r===0?x>0:x<0)?1:0)
          : Math.max(0,1-Math.hypot(x-centers[r][0],y-centers[r][1])/0.32);
      }
      mesh.geometry.setAttribute(attribute,new Float32BufferAttribute(values,1));
      regions.push({id:REGION_IDS[r],attribute,bone:bone.name});
    }
    specs.push({name:mesh.name,regions});
  }
  const clip=new AnimationClip(SYNTHETIC.clip,2,[new VectorKeyframeTrack('BoardAnchor.position',[0,0.5,1,1.5,2],[0,0,0,0.08,0,0,0,0,0,-0.08,0,0,0,0,0])]);
  return {scene:root,animations:[clip],sidecar:{version:1,meshes:specs}};
}
