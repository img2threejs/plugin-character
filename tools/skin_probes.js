// SPDX-License-Identifier: Apache-2.0
// Browser-side probes for "is the skin ever in front of the garment?". Load into the page with
//   await tab.evaluate(src => (0,eval)(src), <contents of this file>)
// then: await window.__inside({faces:true}) -> { samples, insideSkin, deepestMm, byPart, examples }
// A sample is a garment vertex (and, with faces, each triangle centre) whose signed distance to the
// nearest SKIN triangle (configured CPU-skinned support mesh, outward normal) is below -0.3 mm.
// Pull helpers (API-driven, bypass the mouse): __comboStart({pulls:[{kind:'strap'|'panel',side:1|-1,dir:[x,y,z]}]}),
// __comboRun(frames, sampleEvery), __comboRelease(), __comboResult().
window.__inside=async (opts = {}) => {
    const T = await (typeof __omp_import__ === "function" ? __omp_import__ : (s, o) => (typeof __omp_import__ === "function" ? __omp_import__ : (s, o) => import(s, o))(s, o))("three");
    const s = window.garmentStudio;
    if (!s?.ready || !s.config?.garment) throw new Error('garmentStudio: ready calibrated input required');
    const body = s.modelMeshes.find((m) => m.name === s.config.garment.bodyMesh), bik = s.modelMeshes.find((m) => m.name === s.config.garment.garmentMesh);
    if (!body || !bik) throw new Error('garmentStudio: configured meshes missing');
    body.updateMatrixWorld(true);
    bik.updateMatrixWorld(true);
    const gp = bik.geometry.attributes.position, gi = bik.geometry.index.array, bp = body.geometry.attributes.position, bi = body.geometry.index.array;
    const nG = gp.count, v = new T.Vector3;
    const G = new Float32Array(nG * 3);
    for (let i = 0;i < nG; i++) {
      bik.getVertexPosition(i, v);
      v.applyMatrix4(bik.matrixWorld);
      G[i * 3] = v.x;
      G[i * 3 + 1] = v.y;
      G[i * 3 + 2] = v.z;
    }
    let mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9];
    for (let i = 0;i < nG; i++)
      for (let k = 0;k < 3; k++) {
        mn[k] = Math.min(mn[k], G[i * 3 + k]);
        mx[k] = Math.max(mx[k], G[i * 3 + k]);
      }
    const M = 0.06, BW = new Float32Array(bp.count * 3);
    for (let i = 0;i < bp.count; i++) {
      body.getVertexPosition(i, v);
      v.applyMatrix4(body.matrixWorld);
      BW[i * 3] = v.x;
      BW[i * 3 + 1] = v.y;
      BW[i * 3 + 2] = v.z;
    }
    // Partition by triangle bounds in posed world space, never by all vertices inside.
    const tris = new Uint32Array(bi.length);
    let nearEnd = 0, farEnd = bi.length;
    for (let t = 0;t < bi.length; t += 3) {
      const a = bi[t], b = bi[t + 1], c = bi[t + 2];
      let overlaps = true;
      for (let k = 0;k < 3; k++) {
        const x = BW[a * 3 + k], y = BW[b * 3 + k], z = BW[c * 3 + k];
        if (Math.max(x,y,z) < mn[k] - M || Math.min(x,y,z) > mx[k] + M) { overlaps = false; break; }
      }
      let dst;
      if (overlaps) { dst = nearEnd; nearEnd += 3; } else { farEnd -= 3; dst = farEnd; }
      tris[dst] = a; tris[dst + 1] = b; tris[dst + 2] = c;
    }
    const nROI = nearEnd / 3, nT = tris.length / 3;
    const radius = new Float64Array(nT);
    for (let t = 0; t < nT; t++) {
      const a = tris[t * 3] * 3, b = tris[t * 3 + 1] * 3, c = tris[t * 3 + 2] * 3;
      radius[t] = Math.max(Math.hypot(BW[b]-BW[a], BW[b+1]-BW[a+1], BW[b+2]-BW[a+2]), Math.hypot(BW[c]-BW[a], BW[c+1]-BW[a+1], BW[c+2]-BW[a+2]));
    }
    const P = [], tag = [];
    const aS = bik.geometry.attributes.aStrap, aP = bik.geometry.attributes.aPanel, restB = s.rig.meshes.get(s.config.garment.garmentMesh).rest, strap = s.config.garment.strap;
    const part = (i) => aS.getX(i) !== 0 ? "ribbon" : aP.getX(i) !== 0 ? "cup" : restB[i * 3 + 1] >= strap.yAttach && restB[i * 3 + 2] < strap.minZ ? "loop" : "band";
    for (let i = 0;i < nG; i++) {
      P.push(G[i * 3], G[i * 3 + 1], G[i * 3 + 2]);
      tag.push(part(i));
    }
    if (opts.faces !== false)
      for (let t = 0;t < gi.length; t += 3) {
        const a = gi[t], b = gi[t + 1], c = gi[t + 2];
        P.push((G[a * 3] + G[b * 3] + G[c * 3]) / 3, (G[a * 3 + 1] + G[b * 3 + 1] + G[c * 3 + 1]) / 3, (G[a * 3 + 2] + G[b * 3 + 2] + G[c * 3 + 2]) / 3);
        tag.push(part(a));
      }
    const nP = tag.length;
    const cp = (px, py, pz, a, b, c, out) => {
      const abx = BW[b * 3] - BW[a * 3], aby = BW[b * 3 + 1] - BW[a * 3 + 1], abz = BW[b * 3 + 2] - BW[a * 3 + 2], acx = BW[c * 3] - BW[a * 3], acy = BW[c * 3 + 1] - BW[a * 3 + 1], acz = BW[c * 3 + 2] - BW[a * 3 + 2];
      const apx = px - BW[a * 3], apy = py - BW[a * 3 + 1], apz = pz - BW[a * 3 + 2];
      const d1 = abx * apx + aby * apy + abz * apz, d2 = acx * apx + acy * apy + acz * apz;
      let u, w;
      if (d1 <= 0 && d2 <= 0) {
        u = 0;
        w = 0;
      } else {
        const bpx = px - BW[b * 3], bpy = py - BW[b * 3 + 1], bpz = pz - BW[b * 3 + 2];
        const d3 = abx * bpx + aby * bpy + abz * bpz, d4 = acx * bpx + acy * bpy + acz * bpz;
        if (d3 >= 0 && d4 <= d3) {
          u = 1;
          w = 0;
        } else {
          const vc = d1 * d4 - d3 * d2;
          if (vc <= 0 && d1 >= 0 && d3 <= 0) {
            u = d1 / (d1 - d3);
            w = 0;
          } else {
            const cpx = px - BW[c * 3], cpy = py - BW[c * 3 + 1], cpz = pz - BW[c * 3 + 2];
            const d5 = abx * cpx + aby * cpy + abz * cpz, d6 = acx * cpx + acy * cpy + acz * cpz;
            if (d6 >= 0 && d5 <= d6) {
              u = 0;
              w = 1;
            } else {
              const vb = d5 * d2 - d1 * d6;
              if (vb <= 0 && d2 >= 0 && d6 <= 0) {
                u = 0;
                w = d2 / (d2 - d6);
              } else {
                const va = d3 * d6 - d5 * d4;
                if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) {
                  w = (d4 - d3) / (d4 - d3 + (d5 - d6));
                  u = 1 - w;
                } else {
                  const den = 1 / (va + vb + vc);
                  u = vb * den;
                  w = vc * den;
                }
              }
            }
          }
        }
      }
      out[0] = BW[a * 3] + abx * u + acx * w;
      out[1] = BW[a * 3 + 1] + aby * u + acy * w;
      out[2] = BW[a * 3 + 2] + abz * u + acz * w;
    };
    const q = [0, 0, 0], worst = {}, counts = {};
    let tot = 0, inside = 0, deepest = 0;
    const deep = [];
    for (let p = 0;p < nP; p++) {
      const px = P[p * 3], py = P[p * 3 + 1], pz = P[p * 3 + 2];
      let best = 1e9, bt = -1, bq = null;
      for (let t = 0;t < nT; t++) {
        // Excluded bounds are at least M from every garment point. Otherwise scan them too.
        if (t === nROI && bt >= 0 && best < M) break;
        const a = tris[t * 3], b = tris[t * 3 + 1], c = tris[t * 3 + 2];
        const dx = px - BW[a * 3], dy = py - BW[a * 3 + 1], dz = pz - BW[a * 3 + 2];
        if (bt >= 0 && dx * dx + dy * dy + dz * dz > (best + radius[t]) ** 2)
          continue;
        cp(px, py, pz, a, b, c, q);
        const d = (q[0] - px) ** 2 + (q[1] - py) ** 2 + (q[2] - pz) ** 2;
        if (d < best * best || bt < 0) {
          if (d < best * best) {
            best = Math.sqrt(d);
            bt = t;
            bq = [q[0], q[1], q[2]];
          }
        }
      }
      if (bt < 0)
        continue;
      const a = tris[bt * 3], b = tris[bt * 3 + 1], c = tris[bt * 3 + 2];
      const ux = BW[b * 3] - BW[a * 3], uy = BW[b * 3 + 1] - BW[a * 3 + 1], uz = BW[b * 3 + 2] - BW[a * 3 + 2], wx = BW[c * 3] - BW[a * 3], wy = BW[c * 3 + 1] - BW[a * 3 + 1], wz = BW[c * 3 + 2] - BW[a * 3 + 2];
      let nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
      const l = Math.hypot(nx, ny, nz) || 1;
      nx /= l;
      ny /= l;
      nz /= l;
      const sd = (px - bq[0]) * nx + (py - bq[1]) * ny + (pz - bq[2]) * nz;
      const k = tag[p];
      counts[k] = (counts[k] ?? 0) + 1;
      tot++;
      if (sd < -0.0003) {
        inside++;
        const e = worst[k] ??= { n: 0, maxMm: 0 };
        e.n++;
        e.maxMm = Math.max(e.maxMm, +(-sd * 1000).toFixed(1));
        deepest = Math.max(deepest, -sd);
        if (deep.length < 6)
          deep.push({ k, x: +px.toFixed(3), y: +py.toFixed(3), z: +pz.toFixed(3), mm: +(-sd * 1000).toFixed(1), nearestMm: +(best * 1000).toFixed(1) });
      }
    }
    return { samples: tot, counts, insideSkin: inside, deepestMm: +(deepest * 1000).toFixed(1), byPart: worst, examples: deep, bodyTris: nT };
  };

window.__comboStart=async(spec)=>{const T=await import('three');const s=window.garmentStudio;
  if(!s?.ready || !s.config?.garment || !s.config?.probes)throw new Error('garmentStudio: ready calibrated input required');
  const g=s.garments,bik=s.modelMeshes.find(m=>m.name===s.config.garment.garmentMesh);
  s.reset();s.setPaused(true);bik.updateMatrixWorld(true);
  const aS=bik.geometry.attributes.aStrap,aP=bik.geometry.attributes.aPanel,idx=bik.geometry.index.array,v=new T.Vector3();
  const faceFor=(kind,side)=>{let best=null,bd=Infinity;for(let t=0;t<idx.length;t+=3){const ids=[idx[t],idx[t+1],idx[t+2]];if(kind==='strap'){if(!ids.every(i=>aS.getX(i)===side))continue;const sm=ids.reduce((a,i)=>a+aS.getY(i),0)/3;const d=Math.abs(sm-0.5);if(d<bd){bd=d;best={t,ids};}}else{if(!ids.every(i=>aP.getX(i)===side))continue;const c=ids.reduce((a,i)=>a+bik.geometry.attributes.position.getY(i),0)/3;const d=Math.abs(c-s.config.probes.panelY);if(d<bd){bd=d;best={t,ids};}}}return best;};
  const worldOf=(ids)=>{const c=new T.Vector3();for(const i of ids){bik.getVertexPosition(i,v);v.applyMatrix4(bik.matrixWorld);c.add(v);}return c.divideScalar(3);};
  const grabs=[];for(const it of spec.pulls){const f=faceFor(it.kind,it.side);if(!f)return{error:'no configured face '+JSON.stringify(it)};const hit={object:bik,faceIndex:f.t/3,face:{a:f.ids[0],b:f.ids[1],c:f.ids[2]},point:worldOf(f.ids)};const ok=it.kind==='strap'?g.grabStrap(hit,it.side):g.grabPanel(hit,it.side);if(!ok)return{error:'grab refused '+JSON.stringify(it)};grabs.push({it,p0:hit.point.clone()});}
  for(const gr of grabs){const d=new T.Vector3(...gr.it.dir).normalize().multiplyScalar(s.config.probes.pullDistance);(gr.it.kind==='strap'?g.dragStrap:g.dragPanel)(gr.it.side,gr.p0.clone().add(d));}
  window.__combo={grabs,worst:{insideSkin:-1},samples:0};return{ok:true};};
window.__comboRun=async(frames,every)=>{const s=window.garmentStudio,c=window.__combo;for(let i=0;i<frames;i++){s.step(1/60);if((i+1)%every===0){const p=await window.__inside({});c.samples++;if(p.insideSkin>c.worst.insideSkin)c.worst={...p,frame:i+1};}}return{worst:c.worst.insideSkin,samples:c.samples};};
window.__comboRelease=()=>{const g=window.garmentStudio.garments;for(const gr of window.__combo.grabs)(gr.it.kind==='strap'?g.releaseStrap:g.releasePanel)(gr.it.side);return true;};
window.__comboResult=()=>{const c=window.__combo;return{inside:c.worst.insideSkin,deepestMm:c.worst.deepestMm,byPart:c.worst.byPart,samples:c.samples};};

