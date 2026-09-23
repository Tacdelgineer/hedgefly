'use strict';
/* visuals/lib/neon-riso.js — the shared drawing core of the neon riso look (visuals/style.md).
   Loaded by visuals/hq2/ and visuals/posters/; scripts/build_standalone.mjs inlines it.
   Adapted from the riso-rooms engine: black paper, fluorescent inks, additive plates. */
/* =====================================================================
   NEON RISO — the shared drawing core (visuals/style.md).
   A risograph engine turned inside out: black paper, fluorescent inks, and plates that ADD
   light where they overlap instead of darkening. Used by visuals/hq2 and visuals/posters.
   ===================================================================== */
const TAU=Math.PI*2;
const clamp=(v,a,b)=>v<a?a:v>b?b:v;
const lerp=(a,b,t)=>a+(b-a)*t;
const ease=u=>u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;

/* ---------- seeded randomness: same keys -> same numbers, every frame ---------- */
function hashStr(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619)}return h>>>0}
function mulberry(a){return()=>{a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
function stream(...keys){let h=0x9E3779B9;for(const k of keys){h=Math.imul(h^hashStr(String(k)),0x85EBCA6B);h^=h>>>13}const r=mulberry(h>>>0);r();r();return r}
const rand=(R,a,b)=>a+R()*(b-a);
const randi=(R,a,b)=>Math.floor(rand(R,a,b+1));
const pick=(R,arr)=>arr[Math.floor(R()*arr.length)];
function hash2(x,y,s){let h=Math.imul(x|0,374761393)+Math.imul(y|0,668265263)+Math.imul(s|0,1442695041);h=Math.imul(h^h>>>13,1274126177);return((h^h>>>16)>>>0)/4294967296}
function noise(x,y,s=0){const xi=Math.floor(x),yi=Math.floor(y),u=x-xi,v=y-yi,a=u*u*(3-2*u),b=v*v*(3-2*v);
  return lerp(lerp(hash2(xi,yi,s),hash2(xi+1,yi,s),a),lerp(hash2(xi,yi+1,s),hash2(xi+1,yi+1,s),a),b)*2-1}

/* ---------- polyline helpers ---------- */
function resample(P,step){
  const out=[P[0].slice()];let need=step;
  for(let n=1;n<P.length;n++){let x0=P[n-1][0],y0=P[n-1][1];const x1=P[n][0],y1=P[n][1];let d=Math.hypot(x1-x0,y1-y0);
    while(d>=need&&d>0){const t=need/d;x0+=(x1-x0)*t;y0+=(y1-y0)*t;out.push([x0,y0]);d-=need;need=step}need-=d}
  const L=P[P.length-1],E=out[out.length-1];if(Math.hypot(L[0]-E[0],L[1]-E[1])>step*.25)out.push(L.slice());
  return out}
function smooth(P,closed=false,it=2){let p=P;
  for(let k=0;k<it;k++){const q=[],n=p.length;if(!closed)q.push(p[0]);
    for(let i=0;i<(closed?n:n-1);i++){const a=p[i],b=p[(i+1)%n];q.push([a[0]*.75+b[0]*.25,a[1]*.75+b[1]*.25],[a[0]*.25+b[0]*.75,a[1]*.25+b[1]*.75])}
    if(!closed)q.push(p[n-1]);p=q}
  return p}

/* ---------- isometric projection: i runs right-down, j runs left-down, z up ---------- */
const TW=64,TH=32,TZ=32;
const iso=(i,j,z=0)=>[(i-j)*TW/2,(i+j)*TH/2-z*TZ];

/* ---------- paper and inks: every colour means one thing (visuals/style.md) ---------- */
const PAPER=[7,7,11];                               // near-black stock, a violet cast, never #000
const INKS={
  cyan:[39,242,210],    // the real tribe, and nothing else
  magenta:[255,61,154], // the scrambled tribe, and nothing else
  gold:[255,201,60],    // the hero lineage alone
  amber:[255,122,26],   // the locked test set alone
  slate:[91,108,255],   // architecture: walls, floors, furniture
  ghost:[216,220,255],  // linework and small type
};
// The riso prop library was written for four warm inks. Its defaults are mapped onto the two
// neutral inks here, so no piece of furniture can ever print in a tribe's colour by accident.
const ALIAS={blue:'ghost', coral:'slate', yellow:'ghost', teal:'slate'};
const inkOf=k=>INKS[k]?k:(ALIAS[k]||'ghost');
const ANGLE={cyan:15,magenta:75,gold:0,amber:30,slate:45,ghost:105};   // screen angles: the moiré is the point
const MISREG=1.1;                                   // plate misregistration in world px
const css=(c,a=1)=>`rgba(${c[0]},${c[1]},${c[2]},${a})`;
const PAPER_CSS=css(PAPER);

/* ---------- halftone screens ---------- */
const SS=4,CELL=2.3,TILE_N=8,LEVELS=16;   // CELL = dot pitch in world px
const tiles=new Map();
function halftoneTile(ink,level){
  const key=ink+'|'+level;let cv=tiles.get(key);if(cv)return cv;
  ink=inkOf(ink);
  const cell=CELL*SS,size=cell*TILE_N,tone=level/LEVELS,salt=hashStr(ink)%9973;
  cv=document.createElement('canvas');cv.width=cv.height=size;
  const c=cv.getContext('2d');c.fillStyle=css(INKS[ink]);
  if(level>=LEVELS)c.fillRect(0,0,size,size);
  else if(tone<=.5){                                  // growing dots
    for(let y=0;y<TILE_N;y++)for(let x=0;x<TILE_N;x++){
      const r=cell*Math.sqrt(tone/Math.PI)*(.9+hash2(x,y,salt+level)*.18);
      const jx=(hash2(x,y,salt)-.5)*.08*cell,jy=(hash2(y,x,salt)-.5)*.08*cell;
      c.beginPath();c.arc((x+.5)*cell+jx,(y+.5)*cell+jy,r,0,TAU);c.fill()}
  }else{                                              // solid with shrinking holes
    c.fillRect(0,0,size,size);c.globalCompositeOperation='destination-out';
    for(let y=0;y<=TILE_N;y++)for(let x=0;x<=TILE_N;x++){
      const r=cell*Math.sqrt((1-tone)/Math.PI)*(.9+hash2(x%TILE_N,y%TILE_N,salt+level)*.18);
      c.beginPath();c.arc(x*cell,y*cell,r,0,TAU);c.fill()}
  }
  c.globalCompositeOperation='destination-out';       // worn-drum specks
  const R=stream('speck',ink,level),n=size*size/260;
  for(let k=0;k<n;k++){const s=rand(R,1,3.4);c.globalAlpha=rand(R,.25,.9);c.fillRect(R()*size,R()*size,s,s)}
  tiles.set(key,cv);return cv}
const screens=new WeakMap();
function screen(ctx,ink,tone,dx,dy){
  let bank=screens.get(ctx);if(!bank)screens.set(ctx,bank=new Map());
  const level=clamp(Math.round(tone*LEVELS),1,LEVELS),key=`${ink}|${level}|${dx.toFixed(2)}|${dy.toFixed(2)}`;
  let pat=bank.get(key);if(pat)return pat;
  pat=ctx.createPattern(halftoneTile(ink,level),'repeat');
  pat.setTransform(new DOMMatrix().translateSelf(dx,dy).rotateSelf(ANGLE[ink]||0).scaleSelf(1/SS));
  bank.set(key,pat);return pat}

/* ---------- paper grain ---------- */
let grainPattern=null;
function grain(ctx){
  if(grainPattern)return grainPattern;
  const cv=document.createElement('canvas');cv.width=cv.height=384;const c=cv.getContext('2d'),R=stream('grain');
  for(let k=0;k<2600;k++){c.fillStyle=css(INKS.ghost,rand(R,.02,.07));const s=rand(R,.6,1.8);c.fillRect(R()*384,R()*384,s,s)}
  for(let k=0;k<120;k++){c.strokeStyle=css(pick(R,[INKS.slate,INKS.ghost]),rand(R,.03,.07));c.lineWidth=.6;const x=R()*384,y=R()*384,a=R()*TAU,l=rand(R,4,12);
    c.beginPath();c.moveTo(x,y);c.quadraticCurveTo(x+Math.cos(a+.6)*l*.5,y+Math.sin(a+.6)*l*.5,x+Math.cos(a)*l,y+Math.sin(a)*l);c.stroke()}
  return grainPattern=ctx.createPattern(cv,'repeat')}

/* =====================================================================
   THE PEN — every mark goes through here. Points are screen-space [x,y]
   arrays; pen.p(i,j,z) turns room coordinates into them.
   ===================================================================== */
function makePen(ctx,opt={}){
  const ox=opt.ox||0,oy=opt.oy||0,boil=opt.boil||0,variant=boil%3;
  const plate={};for(const k in INKS){const J=stream('plate',k,variant);plate[k]=[rand(J,-1,1)*MISREG,rand(J,-1,1)*MISREG]}
  const pen={ctx,boil,ox,oy};
  const p=pen.p=(i,j,z=0)=>{const q=iso(i,j,z);return [q[0]+ox,q[1]+oy]};
  const trace=(P,dx=0,dy=0)=>{ctx.beginPath();for(let n=0;n<P.length;n++){const x=P[n][0]+dx,y=P[n][1]+dy;n?ctx.lineTo(x,y):ctx.moveTo(x,y)}};
  const withInk=(ink,tone,fn)=>{ink=inkOf(ink);const [dx,dy]=plate[ink];
    ctx.globalCompositeOperation='screen';fn(screen(ctx,ink,tone,dx,dy),dx,dy);ctx.globalCompositeOperation='source-over'};

  /* --- fills --- */
  pen.knock=(P,a=1)=>{if(P.length<3)return;trace(P);ctx.closePath();ctx.fillStyle=a===1?PAPER_CSS:css(PAPER,a);ctx.fill()};
  pen.tint=(P,ink,tone=1)=>{if(tone<=0||P.length<3)return;if(ink==='blue'){ink='slate';tone*=.6}withInk(ink,tone,(st,dx,dy)=>{trace(P,dx,dy);ctx.closePath();ctx.fillStyle=st;ctx.fill()})};
  pen.fill=(P,ink,tone=1)=>{pen.knock(P);if(ink&&ink!=='paper')pen.tint(P,ink,tone)};
  // light cannot cast a shadow by adding light: a shadow is the paper showing through, darker
  pen.shade=(P,a=.6)=>pen.knock(P,a);

  /* --- the hand-drawn line --- */
  pen.line=(P,ink='blue',w=1.3,o={})=>{
    if(!P||P.length<2)return;
    const legacy=ink==='blue';                         // prop linework: architecture, kept quiet
    const src=o.closed?[...P,P[0]]:P;
    let Q=resample(src,Math.max(2.5,w*1.5));if(Q.length<2)return;
    const amp=o.amp??(.35+w*.15);
    if(amp>0){
      const seed=(hash2(Math.round(src[0][0]*3),Math.round(src[0][1]*3),boil*7+1)*1e6)|0;let s=0;
      Q=Q.map((q,n)=>{if(n)s+=Math.hypot(q[0]-Q[n-1][0],q[1]-Q[n-1][1]);
        return [q[0]+noise(s*.045,.5,seed)*amp+(hash2(n,seed,1)-.5)*amp*.3,q[1]+noise(s*.045,7.5,seed)*amp+(hash2(seed,n,2)-.5)*amp*.3]});
      if(o.closed)Q[Q.length-1]=Q[0].slice();
    }
    withInk(ink,(o.tone??1)*(legacy?.5:1),(st,dx,dy)=>{ctx.strokeStyle=st;ctx.lineWidth=w;ctx.lineCap=o.cap||'round';ctx.lineJoin='round';
      if(o.dash)ctx.setLineDash(o.dash);trace(Q,dx,dy);ctx.stroke();if(o.dash)ctx.setLineDash([])});
  };
  pen.shape=(P,fill,o={})=>{if(fill)pen.fill(P,fill[0],fill[1]);if(o.line!==false)pen.line(P,o.line||'ghost',o.w??1.2,{closed:true,amp:o.amp,tone:o.lineTone??.5})};
  pen.dot=(x,y,r,ink='blue',tone=1)=>pen.tint(pen.circle(x,y,r,10),ink,tone);

  /* --- geometry (all return point arrays) --- */
  pen.floorQuad=(i,j,w,d,z=0)=>[p(i,j,z),p(i+w,j,z),p(i+w,j+d,z),p(i,j+d,z)];
  pen.wallQuad=(wall,u,z,w,h,off=.02)=>{const W=(a,zz)=>wall==='i'?p(u+a,off,zz):p(off,u+a,zz);return [W(0,z),W(w,z),W(w,z+h),W(0,z+h)]};
  pen.ellipse=(ci,cj,z,ri,rj=ri,n=28)=>Array.from({length:n},(_,k)=>{const a=k/n*TAU;return p(ci+Math.cos(a)*ri,cj+Math.sin(a)*rj,z)});
  pen.circle=(x,y,r,n=18)=>Array.from({length:n},(_,k)=>[x+Math.cos(k/n*TAU)*r,y+Math.sin(k/n*TAU)*r]);
  pen.blob=(x,y,rx,ry,key='blob',lump=.22,n=9)=>{const R=stream('blob',key),P=[];
    for(let k=0;k<n;k++){const a=k/n*TAU+rand(R,-.2,.2),m=1+rand(R,-lump,lump);P.push([x+Math.cos(a)*rx*m,y+Math.sin(a)*ry*m])}
    return smooth(P,true,3)};
  pen.leaf=(a,b,wid)=>{const mx=(a[0]+b[0])/2,my=(a[1]+b[1])/2,dx=b[0]-a[0],dy=b[1]-a[1],L=Math.hypot(dx,dy)||1,nx=-dy/L*wid,ny=dx/L*wid;
    return smooth([a,[mx+nx,my+ny],b,[mx-nx,my-ny]],true,2)};

  /* --- solids --- */
  pen.box=(i,j,z,w,d,h,o={})=>{
    const ink=o.ink||'coral',tone=o.tone??.5;
    if(o.shadow!==false)pen.shade(pen.floorQuad(i+.12,j+.18,w,d,z),.6);
    const top=pen.floorQuad(i,j,w,d,z+h);
    const faceJ=[p(i,j+d,z),p(i+w,j+d,z),p(i+w,j+d,z+h),p(i,j+d,z+h)];   // lower-left face
    const faceI=[p(i+w,j,z),p(i+w,j+d,z),p(i+w,j+d,z+h),p(i+w,j,z+h)];   // lower-right face
    pen.fill(faceJ,o.leftInk||ink,o.left??clamp(tone+.3,0,1));
    pen.fill(faceI,o.rightInk||ink,o.right??clamp(tone+.15,0,1));
    pen.fill(top,o.topInk||ink,o.top??tone);
    if(o.line!==false){const lw=o.w??1.1;for(const F of[faceJ,faceI,top])pen.line(F,'blue',lw,{closed:true})}
    return {top,faceI,faceJ}};

  /* --- the room shell --- */
  pen.shell=(r)=>{
    const {w,d,h}=r,st=r.style||{},T=.25;
    const [fi,ft]=st.floor||['blue',.65],[wi,wt]=st.wall||['coral',.3],[wi2,wt2]=st.wall2||[wi,Math.min(1,wt+.12)];
    const sideJ=[p(-T,d,0),p(w,d,0),p(w,d,-.5),p(-T,d,-.5)],sideI=[p(w,-T,0),p(w,d,0),p(w,d,-.5),p(w,-T,-.5)];
    pen.shape(sideJ,[fi,Math.min(1,ft+.25)]);pen.shape(sideI,[fi,Math.min(1,ft+.12)]);
    pen.shape(pen.floorQuad(-T,-T,w+T,d+T,0),[fi,ft],{w:1.4});
    if(st.planks!==false)for(let a=st.plank||.8;a<d;a+=st.plank||.8)pen.line([p(0,a,0),p(w,a,0)],'blue',.6,{tone:.9,amp:.25});
    if(h>0){
      pen.shape(pen.wallQuad('j',0,0,d,h,0),[wi2,wt2]);
      pen.shape(pen.wallQuad('i',0,0,w,h,0),[wi,wt]);
      pen.shape([p(w,-T,0),p(w,0,0),p(w,0,h),p(w,-T,h)],[wi,Math.min(1,wt+.3)]);
      pen.shape([p(-T,d,0),p(0,d,0),p(0,d,h),p(-T,d,h)],[wi2,Math.min(1,wt2+.3)]);
      pen.shape([p(-T,-T,h),p(w,-T,h),p(w,0,h),p(0,0,h),p(0,d,h),p(-T,d,h)],['paper',0]);
      pen.line([p(0,d,.12),p(0,0,.12),p(w,0,.12)],'blue',.8,{tone:.8});
    }};

  /* --- furniture & props --- */
  pen.table=(i,j,w,d,h=.75,o={})=>{const ink=o.ink||'coral',tone=o.tone??.55,L=.12;
    pen.shade(pen.floorQuad(i+.2,j+.25,w,d,0),.6);
    for(const [a,b] of [[i,j],[i+w-L,j],[i,j+d-L],[i+w-L,j+d-L]])pen.box(a,b,0,L,L,h-.1,{ink,tone:tone+.2,shadow:false,w:.8});
    pen.box(i-.05,j-.05,h-.1,w+.1,d+.1,.1,{ink,tone,shadow:false});
    return p(i+w/2,j+d/2,h)};
  pen.chair=(i,j,o={})=>{const ink=o.ink||'yellow',tone=o.tone??.7,L=.07;
    pen.shade(pen.floorQuad(i+.1,j+.15,.5,.5,0),.6);
    for(const [a,b] of [[i,j],[i+.5-L,j],[i,j+.5-L],[i+.5-L,j+.5-L]])pen.box(a,b,0,L,L,.4,{ink:'blue',tone:.8,shadow:false,w:.6});
    if(o.back==='j')pen.box(i,j,.45,.5,.07,.55,{ink,tone,shadow:false,w:.9});
    else pen.box(i,j,.45,.07,.5,.55,{ink,tone,shadow:false,w:.9});
    pen.box(i,j,.4,.5,.5,.06,{ink,tone,shadow:false,w:.9})};
  pen.rug=(i,j,w,d,o={})=>{const ink=o.ink||'teal',tone=o.tone??.45;
    pen.shape(pen.floorQuad(i,j,w,d,.01),[ink,tone],{w:1});
    pen.line(pen.floorQuad(i+.3,j+.3,w-.6,d-.6,.01),o.border||'coral',1.1,{closed:true,tone:.8});
    for(let a=.1;a<d;a+=.18){pen.line([p(i,j+a,0),p(i-.2,j+a,0)],ink,.6,{amp:.1});pen.line([p(i+w,j+a,0),p(i+w+.2,j+a,0)],ink,.6,{amp:.1})}};
  pen.bookcase=(wall,u,wid,hgt,o={})=>{
    const R=stream('shelf',wall,u),rows=o.rows||4,dep=o.depth||.45,ink=o.ink||'coral';
    const [bi,bj,bw,bd]=wall==='i'?[u,0,wid,dep]:[0,u,dep,wid];
    pen.box(bi,bj,0,bw,bd,hgt,{ink,tone:.65});
    const F=(a,z)=>wall==='i'?p(u+a,dep,z):p(dep,u+a,z);
    const rowH=(hgt-.2)/rows;
    for(let r=0;r<rows;r++){const z0=.12+r*rowH,z1=z0+rowH-.08;
      pen.fill([F(.08,z0),F(wid-.08,z0),F(wid-.08,z1),F(.08,z1)],'blue',.85);
      let a=.1;
      while(a<wid-.18){const bw_=rand(R,.07,.14),bh=(z1-z0)*rand(R,.62,.95);
        if(R()<.07){a+=rand(R,.12,.3);continue}
        const q=[F(a,z0),F(a+bw_,z0),F(a+bw_,z0+bh),F(a,z0+bh)];
        pen.fill(q,pick(R,['coral','yellow','teal','paper','coral','teal']),rand(R,.45,.95));
        pen.line(q,'blue',.55,{closed:true,amp:.1});a+=bw_+.012}
      pen.line([F(0,z0),F(wid,z0)],'blue',1.3)}};
  pen.window=(wall,u,z,wid,hgt,o={})=>{
    const q=pen.wallQuad(wall,u,z,wid,hgt),W=(a,zz)=>wall==='i'?p(u+a,.02,zz):p(.02,u+a,zz);
    pen.fill(q,o.sky||'teal',.22);pen.tint(pen.wallQuad(wall,u,z,wid,hgt*.4),'yellow',.3);
    pen.line(q,'blue',1.8,{closed:true});
    pen.line([W(wid/2,z),W(wid/2,z+hgt)],'blue',1.1);pen.line([W(0,z+hgt*.55),W(wid,z+hgt*.55)],'blue',1.1);
    pen.line([W(-.12,z-.03),W(wid+.12,z-.03)],'blue',2.4);
    if(o.patch!==false)pen.sunPatch(wall,u,z,wid,hgt,o)};
  pen.sunPatch=(wall,u,z,wid,hgt,o={})=>{const k=o.reach??1.1,s=o.shear??.45,F=(a,b)=>wall==='i'?p(a,b,.01):p(b,a,.01);
    const q=[F(u+z*s,z*k),F(u+wid+z*s,z*k),F(u+wid+(z+hgt)*s,(z+hgt)*k),F(u+(z+hgt)*s,(z+hgt)*k)];
    pen.light(q,o.light??.5)};
  // light can't come from multiply alone: lift the paper first, then print yellow on top
  pen.light=(P,strength=.5,ink='ghost')=>pen.tint(P,ink,.12+.3*strength);
  pen.glow=(i,j,z,r,ink='ghost',strength=.6)=>{for(let k=0;k<4;k++){const E=pen.ellipse(i,j,z,r*(1-k*.22));pen.tint(E,ink,strength*(k+1)/9)}};
  pen.halo=(x,y,r,ink,strength=.5)=>{for(let k=0;k<3;k++)pen.tint(pen.circle(x,y,r*(1-k*.28),18),ink,strength*(k+1)/7)};
  pen.lamp=(i,j,o={})=>{const h=o.h??1.8,t=o.t||0,on=o.on!==false,fl=.85+.15*noise(t*5,0,hashStr(`${i},${j}`)%999);
    if(on)pen.glow(i,j,0,1.7,'yellow',.55*fl);
    pen.fill(pen.ellipse(i,j,0,.22),'blue',.7);
    pen.line([p(i,j,0),p(i,j,h)],'blue',1.5,{amp:.2});
    const [sx,sy]=p(i,j,h);
    if(on)pen.light([[sx-7,sy+5],[sx+7,sy+5],[sx+30,sy+h*TZ],[sx-30,sy+h*TZ]],.25*fl);
    pen.shape([[sx-8,sy+5],[sx+8,sy+5],[sx+4,sy-6],[sx-4,sy-6]],[o.ink||'teal',.8])};
  pen.plant=(i,j,z=0,o={})=>{const R=stream('plant',i,j),s=o.size||1,ink=o.ink||'teal',t=o.t||0;
    pen.box(i-.2*s,j-.2*s,z,.4*s,.4*s,.38*s,{ink:o.pot||'coral',tone:.55});
    const [x,y]=p(i,j,z+.38*s),n=o.leaves||8;
    for(let k=0;k<n;k++){const a=-Math.PI/2+rand(R,-1.2,1.2),len=rand(R,14,28)*s,sway=Math.sin(t*1.4+k)*1.2;
      pen.shape(pen.leaf([x,y],[x+Math.cos(a)*len+sway,y+Math.sin(a)*len],rand(R,3.5,6.5)*s),[ink,rand(R,.55,.95)],{w:.8})}};
  pen.books=(i,j,z,n,o={})=>{const R=stream('books',i,j);let zz=z;
    for(let k=0;k<n;k++){const th=rand(R,.08,.14),dx=rand(R,-.06,.06);
      pen.box(i+dx,j+dx*.5,zz,.5,.36,th,{ink:pick(R,['coral','teal','yellow','blue']),tone:rand(R,.4,.8),shadow:k===0,w:.8,top:0});zz+=th}};
  pen.steam=(x,y,t,o={})=>{for(let k=0;k<(o.n||2);k++){const P=[],ph=t*1.6+k*1.7;
    for(let s=0;s<=10;s++){const u=s/10;P.push([x+(k-.5)*4+Math.sin(ph*3+u*5)*2.5*u,y-u*(o.h||18)])}
    pen.line(P,o.ink||'blue',.8,{tone:.55*(1-((t*.8+k*.5)%1)*.5),amp:.2})}};
  pen.sparkle=(x,y,r,ink='yellow',t=0)=>{const a0=t*1.5,k=.6+.4*Math.sin(t*4+x);
    for(let q=0;q<4;q++){const a=a0+q*Math.PI/4,rr=r*k*(q%2?.55:1);pen.line([[x-Math.cos(a)*rr,y-Math.sin(a)*rr],[x+Math.cos(a)*rr,y+Math.sin(a)*rr]],ink,1.1,{amp:0})}};

  /* --- characters: every one of them is a fly (see FLIES below) --- */
  installFlies(pen);

  return pen;
}

/* =====================================================================
   FLIES — every character is one (visuals/style.md). Installed on each pen.
   ===================================================================== */
const ellipse2=(cx,cy,rx,ry,rot=0,n=20)=>Array.from({length:n},(_,k)=>{const a=k/n*TAU,x=Math.cos(a)*rx,y=Math.sin(a)*ry;
  return [cx+x*Math.cos(rot)-y*Math.sin(rot), cy+x*Math.sin(rot)+y*Math.cos(rot)]});
function installFlies(pen){
  const p=pen.p;
  /* A fly character standing, sitting or hovering at room point (i,j,z). s=1 is about the
     height of a chair back. `ink` says who it is: a tribe, the hero, or 'slate' for staff. */
  pen.fly=(i,j,z=0,o={})=>{
    const t=o.t||0,s=o.scale||1,f=o.facing===-1?-1:1,ink=o.ink||'slate',tone=o.tone??.85;
    const pose=o.pose||'stand',ph=t*TAU*(o.speed||.6)+(o.phase||0);
    const lift=pose==='hover'?12+Math.sin(ph*1.3)*3:pose==='sit'?-4:0;
    const [bx,by0]=p(i,j,z),by=by0-lift*s,X=v=>bx+v*s*f,Y=v=>by+v*s;
    const eyes=ink==='slate'?'ghost':ink;
    if(!o.noShadow)pen.shade(pen.ellipse(i,j,z,.26*s,.2*s,14),.55);
    if(o.glow!==false)pen.halo(X(0),Y(-18),24*s,ink,.32*(o.glowStrength??1));
    for(const [lx,dx] of [[-5,-7],[-1,-2],[3,5]]){                                   // six legs
      if(pose==='hover')pen.line([[X(lx),Y(-12)],[X(lx+dx*.4),Y(-3)],[X(lx+dx*.6),Y(3)]],'ghost',.8*s,{tone:.5});
      else pen.line([[X(lx),Y(-12)],[X(lx+dx),Y(-8)],[X(lx+dx*1.2),Y(0)]],'ghost',.9*s,{tone:.7});
    }
    const beat=o.dead?0:Math.sin(t*30+(o.phase||0)*7);                              // wings flicker every frame
    // wings are light, not card: tinted without knocking out what is behind them
    for(const [root,tip,wid,tone] of [[[X(-1),Y(-21)],[X(-16),Y(-35-beat*5)],5.5*s,.22],[[X(0),Y(-22)],[X(-7),Y(-41+beat*5)],4.8*s,.18]]){
      const L=pen.leaf(root,tip,wid);pen.tint(L,ink,tone);pen.line(L,'ghost',.7,{closed:true,tone:.45});
    }
    pen.shape(ellipse2(X(-5),Y(-13),7.5*s,5.5*s,.35*f),[ink,tone*.75],{line:ink,w:1*s,lineTone:.9});   // abdomen
    for(const k of[-2,1.5])pen.line([[X(-6+k),Y(-18)],[X(-4+k),Y(-8)]],'paper',1*s,{tone:1,amp:.2});
    pen.shape(pen.circle(X(1),Y(-19),5*s,14),[ink,tone],{line:ink,w:1*s,lineTone:.95});    // thorax
    const hy=pose==='sit'?-22:-24;
    pen.shape(pen.circle(X(6),Y(hy),4.3*s,14),[ink,tone*.9],{line:ink,w:.9*s});              // head
    for(const [ex,ey,er] of [[8,hy-1.4,2.7],[4.6,hy-2,2.3]]){                                // compound eyes
      pen.shape(pen.circle(X(ex),Y(ey),er*s,12),[eyes,1],{line:false});
      pen.dot(X(ex+.7),Y(ey-.8),.7*s,'ghost',.9);
    }
    pen.line([[X(6),Y(hy-4)],[X(8),Y(hy-9)]],'ghost',.7*s,{tone:.6});                      // antennae
    pen.line([[X(5),Y(hy-4)],[X(4),Y(hy-9)]],'ghost',.7*s,{tone:.6});
    return {head:[X(6),Y(hy)],hand:[X(10),Y(-10)],top:[X(-8),Y(-42)]};
  };
  /* A crowd fly: cheap enough to draw a hundred of. Body, eye, two wing strokes. */
  pen.minifly=(x,y,s,ink,tone=.9,t=0,phase=0)=>{
    const beat=Math.sin(t*30+phase*7)*1.6*s;
    pen.line([[x-1*s,y-1*s],[x-5*s,y-4*s-beat]],'ghost',.7,{tone:.55,amp:0});
    pen.line([[x+.5*s,y-1.2*s],[x-2*s,y-5.5*s+beat]],'ghost',.7,{tone:.5,amp:0});
    pen.dot(x,y,2.1*s,ink,tone);
    pen.dot(x+2*s,y-.8*s,1.1*s,ink,Math.min(1,tone+.1));
  };
  /* An eliminated fly: on its back, legs up, wings flat. For the pile. */
  pen.deadfly=(x,y,s,ink,tone=.55,rot=0)=>{
    const c=Math.cos(rot),sn=Math.sin(rot),R=(dx,dy)=>[x+dx*c-dy*sn,y+dx*sn+dy*c];
    pen.dot(...R(0,0),2.4*s,ink,tone);
    pen.dot(...R(2.6*s,0),1.3*s,ink,tone*.9);
    for(const k of[-1.4,0,1.4])pen.line([R(k*s,-1.2*s),R(k*s+.6*s,-3.4*s)],ink,.6,{tone:tone*.8,amp:0});
  };
}

/* =====================================================================
   LETTERING — a stencil alphabet drawn through the same wobbly pen
   ===================================================================== */
/* Digits must survive a small chart label: 0 carries a slash and 8 is two loops pinched at
   the waist, so neither can be read as the other. */
const GLYPHS={
 A:'062046|1434', B:'0006|003041423303|033344453606', C:'4130100105163645',
 D:'0006|003041453606', E:'40000646|0333', F:'400006|0333', G:'41301001051636454424',
 H:'0006|4046|0343', I:'2026|1030|1636', J:'3035261605', K:'0006|0340|0346',
 L:'000646', M:'0600234046', N:'06004640', O:'103041453616050110',
 P:'0006|003041423303', Q:'103041453616050110|3546', R:'0006|003041423303|3346',
 S:'413010010213334445361605', T:'2026|0040', U:'000516364540', V:'002640',
 W:'0016233640', X:'0046|4006', Y:'0023|4023|2326', Z:'00400646',
 0:'103041453616050110|4006', 1:'112026|1636', 2:'01103041420646',
 3:'0040234445361605', 4:'36300444', 5:'400003334445361605',
 6:'40100105163645443303', 7:'004026', 8:'103041423313020110|133344453616050413',
 9:'4313030201103041453616', '$':'413010010213334445361605|2027', '%':'0010|4006|3646',
 '-':'1343', '+':'1343|2125', '.':'2625', ',':'2635', ':':'2221|2524', '/':'4006',
 '(':'30121436', ')':'10323416', '*':'2024|0422|4022', '·':'2323', "'":'2021', '!':'2023|2626', '?':'011030414223|2626',
};
function text(pen,str,at,size,o={}){
  const ink=o.ink||'ghost',tone=o.tone==null?.9:o.tone,w=o.w||1.1,gap=o.gap==null?.38:o.gap;
  let ux=[size*.62,0],uy=[0,size];
  if(o.wall==='i'){ux=[size*.62*Math.cos(.4636),size*.62*Math.sin(.4636)]}
  if(o.wall==='j'){ux=[size*.62*Math.cos(.4636),-size*.62*Math.sin(.4636)]}
  let [cx,cy]=at;
  for(const ch of String(str).toUpperCase()){
    const g=GLYPHS[ch];
    if(g)for(const stroke of g.split('|')){
      const P=[];
      for(let k=0;k+1<stroke.length;k+=2)
        P.push([cx+(+stroke[k]/4)*ux[0]+(+stroke[k+1]/6)*uy[0], cy+(+stroke[k]/4)*ux[1]+(+stroke[k+1]/6)*uy[1]]);
      if(P.length===1||(P.length===2&&P[0][0]===P[1][0]&&P[0][1]===P[1][1]))pen.dot(P[0][0],P[0][1],w*.8,ink,tone);
      else pen.line(P,ink,w,{tone,amp:o.amp??.35});
    }
    cx+=ux[0]*(1+gap);cy+=ux[1]*(1+gap);
  }
  return [cx,cy];
}
const textWidth=(str,size,gap=.38)=>String(str).length*size*.62*(1+gap);
function textCentred(pen,str,at,size,o={}){return text(pen,str,[at[0]-textWidth(str,size,o.gap)/2,at[1]],size,o)}
const money=v=>'$'+Math.round(v).toLocaleString('en-US');

/* =====================================================================
   HEADLINES — the narrator's, when the run carries one that passed the Fact Guard; otherwise
   chosen by rules from a generation's numbers. Either way they carry no numbers of their own:
   the model's "Generation N:" is dropped (the card prints the generation from the data), and a
   narrator headline still holding a digit gives way to the rules.
   Shared by the poster cards and the Archive room so the two always agree.
   ===================================================================== */
function toldHeadline(f){
  const told=f.story&&f.story.headline;if(!told)return null;
  const h=String(told).replace(/^\s*gen(?:eration)?\s*\d+\s*[:.\-–—]\s*/i,'').trim();
  return h&&!/\d/.test(h)?h:null;
}
function headlineFor(run,g){
  const f=run.frames[g],prev=g?run.frames[g-1]:null,r=f.tribes.real,s=f.tribes.scrambled,h=f.heroes.real;
  const told=toldHeadline(f);if(told)return told;
  if(g===0)return 'The swarm wakes up';
  if(h.origin==='newcomer')return 'A stranger takes the crown';
  if(h.generations_lived>=4)return 'The old guard holds';
  if(prev&&r.trades.median_per_day<prev.tribes.real.trades.median_per_day*.7)return 'The flies learn to sit still';
  if(r.equity.median>s.equity.median&&r.equity.best>s.equity.best)return 'The real brains pull ahead';
  if(s.equity.median>r.equity.median&&s.equity.best>r.equity.best)return 'The shuffled brains strike back';
  return 'Neck and neck';
}
