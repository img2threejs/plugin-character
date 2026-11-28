// SPDX-License-Identifier: Apache-2.0
// Independently authored Cartesian board example. No body landmarks, scans, source
// transforms, painted source pixels or measured character ratios are used here.
// Units are metres; the board spans [-1.2,1.2] x [-1.2,1.2].
export const SYNTHETIC = {
  label: 'Synthetic board + cloth • geometric mechanics only', synthetic: true,
  background:0xf0f2f5, lights:{sky:0xffffff,ground:0x8291a3,key:0xffffff,fill:0xe2edff},
  clip: 'BoardSlide', initialView: 'front',
  camera: { fov: 42, near: 0.01, far: 50, minDistance: 1, maxDistance: 12 },
  views: {
    front: { position: [0,0,5], target: [0,0,0] }, quarter: { position: [3,1,5], target: [0,0,0] },
    profile: { position: [5,0,1], target: [0,0,0] }, rear: { position: [0,0,-5], target: [0,0,0] },
    torso: { position: [0,0,3], target: [0,0,0] }, hips: { position: [0,-0.6,3], target: [0,-0.6,0] },
    face: { position: [0,0.8,3], target: [0,0.8,0] },
  },
  regionViews: { 'chest-left':'torso','chest-right':'torso','hips-left':'hips','hips-right':'hips',
    'waist-left':'torso','waist-right':'torso',abdomen:'torso','cheek-left':'face','cheek-right':'face' },
  outfitLabels: { cobalt:'Cobalt', gold:'Gold' }, probes: { panelY: 0, pullDistance: 0.6 },
  soft: {
    profiles: {
      chest: { frequency:3, dampingRatio:0.12, cap:0.02, compression:0.16 },
      hips: { frequency:3, dampingRatio:0.12, cap:0.02, compression:0.16 },
      abdomen: { frequency:3, dampingRatio:0.3, cap:0.02, compression:0.06, pressDepth:0.01 },
      waist: { frequency:5, dampingRatio:0.6, cap:0.01, compression:0.1 },
      cheek: { frequency:5, dampingRatio:0.8, cap:0.004, compression:0, pressDepth:-0.002 },
    },
    pads: { chest:[0.04,0.006],hips:[0.04,0.006],abdomen:[0.04,0.001],waist:[0.03,0.002],cheek:[0.03,0] },
  },
  round: { plateau:0.15, reach:0.4, wallDepth:0.1, wallFade:0.2, midline:0, midlineFade:0.1,
    regions:['chest-left','chest-right'], suffix:'_ROUND' },
  garment: {
    bodyMesh:'SupportBoard', garmentMesh:'ClothGrid', regions:{ 1:'chest-left', '-1':'chest-right' },
    outfits:['cobalt','gold'], origin:[0,0.9,0.012], normalOrigin:[0,0,-1],
    strap:{ yAttach:0.4,yTop:1,maxAbsX:0.55,minZ:-0.1,maxPull:0.06,grabMin:0.1,grabMax:0.9,frequency:7,dampingRatio:0.2,holdFrequency:12,tension:0.6 },
    panel:{ maxPull:0.04,frequency:7,dampingRatio:0.7,normalLift:0.004 },
    strapField:{ reachFactor:1.5,minReach:0.3,fallbackReach:2,pinRange:0.2,liftFade:[0.5,1] },
    cupLift:{ gap:0.025,lead:[-0.5,1],extent:0.3 }, contactSteady:{ maxDisagreement:0.002 },
    flap:{ hinge:0.1,bend:0.12,reach:0.3,lift:0.003,ribbonLift:0.006,cutSpan:0.2,normalRadius:0.2,hang:[0,-1,0.3] },
    contact:{ heightRange:[-1.2,1.2],strapRadius:0.3,panelRadius:0.2,minGap:0.0008,maxGap:0.03 },
    colorway:{ saturation:[0.1,0.4],hueIn:[190,210,250,270],hueOut:48,saturationScale:1,valueScale:1 },
    visual:{ sparkWidth:0.02,noiseScale:20,noiseAmplitude:0.03,waveWidth:0.05,revealWidth:0.03,glowColor:[1,0.8,0.3] },
  },
};
