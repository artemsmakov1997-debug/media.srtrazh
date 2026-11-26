/* Procedural, lit 3D bust. Both renderers project the same triangle mesh. */
(() => {
  'use strict';
  const canvas = document.getElementById('authorMeshCanvas');
  if (!canvas) return;
  const normalize = v => { const n = Math.hypot(...v) || 1; return v.map(x => x/n); };
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const sub = (a,b) => a.map((x,i) => x-b[i]);
  const dot = (a,b) => a.reduce((n,x,i) => n+x*b[i],0);
  const vertices=[], normals=[], indices=[],surfaces=[];
  function profileAt(profile,u) {
    const x=Math.max(0,Math.min(profile.length-1,u*(profile.length-1)));
    const i=Math.min(profile.length-2,Math.floor(x)),f=x-i;
    const a=profile[Math.max(0,i-1)],b=profile[i],c=profile[i+1],d=profile[Math.min(profile.length-1,i+2)];
    return b.map((v,k) => .5*((2*v)+(-a[k]+c[k])*f+(2*a[k]-5*v+4*c[k]-d[k])*f*f+(-a[k]+3*v-3*c[k]+d[k])*f*f*f));
  }
  function surface(profile,rings,segments,kind) {
    const offset=vertices.length/3;
    surfaces.push({offset,rings,segments});
    const point=(u,angle) => {
      const [y,rx,rz,center=0,centerX=0]=profileAt(profile,u),s=Math.sin(angle),c=Math.cos(angle);
      let z=rz*c+center;
      if(kind==='head'&&c>0){
        z=rz*Math.pow(c,.65)+center;
        // A quiet brow, nose bridge and chin give a faceless anatomical volume.
        z+=.075*Math.exp(-Math.pow(angle/.24,2)-Math.pow((y-1.3)/.22,2));
        z+=.025*Math.exp(-Math.pow(angle/.6,2)-Math.pow((y-.9)/.12,2));
      }
      if(kind==='torso'&&c>0) z+=.035*Math.sin(Math.PI*u)*Math.exp(-Math.pow((Math.abs(s)-.45)/.3,2));
      return [rx*s+centerX,y,z];
    };
    for(let r=0;r<=rings;r++)for(let a=0;a<=segments;a++){
      const u=r/rings,theta=a/segments*Math.PI*2-Math.PI,p=point(u,theta);
      const du=sub(point(Math.min(1,u+.0002),theta),point(Math.max(0,u-.0002),theta));
      const da=sub(point(u,theta+.0002),point(u,theta-.0002));
      vertices.push(...p);normals.push(...normalize(cross(da,du)));
    }
    for(let r=0;r<rings;r++)for(let a=0;a<segments;a++){
      const q=offset+r*(segments+1)+a,w=q+segments+1;
      indices.push(q,w,q+1,q+1,w,w+1);
    }
  }
  surface([[-1.08,1.05,.42,0],[-.95,1.22,.48,0],[-.64,1.22,.5,0],[-.3,1.08,.45,0],[-.02,.8,.36,0],[.29,.42,.25,0],[.48,.25,.21,0]],48,72,'torso');
  surface([[.35,.25,.21,0],[.55,.235,.21,0],[.72,.235,.22,.01],[.86,.27,.25,.015]],24,64,'neck');
  surface([[.69,.025,.03,.06],[.79,.225,.23,.06],[.91,.39,.33,.025],[1.13,.48,.37,.015],[1.39,.5,.39,0],[1.65,.48,.385,-.015],[1.87,.38,.33,-.02],[2,.17,.16,-.02],[2.03,.005,.005,-.02]],72,88,'head');
  for(const side of [-1,1])surface([[1.03,.005,.005,0,side*.46],[1.09,.07,.1,0,side*.48],[1.25,.085,.105,0,side*.49],[1.4,.06,.09,0,side*.48],[1.45,.005,.005,0,side*.46]],16,24,'ear');
  surface([[-1.2,.02,.02,0],[-1.195,1.08,.48,0],[-1.12,1.08,.48,0],[-1.1,.02,.02,0]],8,72,'base');
  const count=vertices.length/3;
  canvas.dataset.modelKind='3d-mesh';canvas.dataset.vertices=String(count);canvas.dataset.triangles=String(indices.length/3);
  let gl;
  try { gl=canvas.getContext('webgl',{alpha:true,antialias:true,preserveDrawingBuffer:true}); } catch {}
  const fov=38*Math.PI/180,near=.1,far=30,camera=[0,.6,5.7];
  const projection=aspect => {
    const f=1/Math.tan(fov/2);
    return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0]);
  };
  const rotation=time => -.48+Math.sin(time*.42)*.22;
  function rotate(v,angle){const c=Math.cos(angle),s=Math.sin(angle);return [v[0]*c+v[2]*s,v[1],-v[0]*s+v[2]*c];}
  let lastTime=0,drawGL=null;
  if(gl){
    try {
      const shader=(type,code)=>{const s=gl.createShader(type);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('shader');return s;};
      const program=gl.createProgram();
      gl.attachShader(program,shader(gl.VERTEX_SHADER,`
        attribute vec3 position;attribute vec3 normal;uniform mat4 projection;uniform float angle;
        varying vec3 world;varying vec3 surfaceNormal;
        void main(){float c=cos(angle),s=sin(angle);mat3 turn=mat3(c,0.,-s,0.,1.,0.,s,0.,c);
          world=turn*position;surfaceNormal=normalize(turn*normal);
          gl_Position=projection*vec4(world-vec3(0.,.6,5.7),1.);}`));
      gl.attachShader(program,shader(gl.FRAGMENT_SHADER,`
        precision mediump float;varying vec3 world;varying vec3 surfaceNormal;
        void main(){vec3 n=normalize(surfaceNormal),view=normalize(vec3(0.,.6,5.7)-world);
          vec3 key=normalize(vec3(-.7,1.,1.2)),fill=normalize(vec3(1.,.2,.4));
          float diffuse=max(dot(n,key),0.)*.9+max(dot(n,fill),0.)*.24;
          float spec=pow(max(dot(n,normalize(key+view)),0.),52.);
          float rim=pow(1.-max(dot(n,view),0.),3.);
          vec3 base=vec3(.018,.32,.43);if(world.y < -1.09)base=vec3(.012,.07,.10);
          vec3 color=base*(.18+diffuse)+vec3(.5,.9,1.)*spec*.65+vec3(.015,.28,.44)*rim*.6;
          color=pow(color,vec3(.4545));gl_FragColor=vec4(color,1.);}`));
      gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('program');
      gl.useProgram(program);
      for(const [name,data] of [['position',vertices],['normal',normals]]){
        const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
        const location=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,3,gl.FLOAT,false,0,0);
      }
      const buffer=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,buffer);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW);
      const matrix=gl.getUniformLocation(program,'projection'),angle=gl.getUniformLocation(program,'angle');
      gl.enable(gl.DEPTH_TEST);gl.clearColor(0,0,0,0);
      drawGL=(time)=>{
        gl.viewport(0,0,canvas.width,canvas.height);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
        gl.uniformMatrix4fv(matrix,false,projection(canvas.width/canvas.height));gl.uniform1f(angle,rotation(time));
        gl.drawElements(gl.TRIANGLES,indices.length,gl.UNSIGNED_SHORT,0);
      };
      canvas.dataset.renderer='webgl';
    } catch {
      // A fresh canvas can use the same 3D geometry with the software renderer.
      const replacement=canvas.cloneNode();canvas.replaceWith(replacement);
      window.authorBust3D=createSoftware(replacement);
      return;
    }
  } else { window.authorBust3D=createSoftware(canvas);return; }
  function resize(){
    const ratio=Math.min(devicePixelRatio||1,2),size=Math.max(1,Math.round(canvas.clientWidth*ratio));
    if(canvas.width!==size||canvas.height!==size){canvas.width=size;canvas.height=size;}
  }
  window.authorBust3D={render(time){lastTime=time;resize();drawGL(time);},kind:'3d-mesh'};
  new ResizeObserver(()=>window.authorBust3D.render(lastTime)).observe(canvas);
  window.authorBust3D.render(0);
  function createSoftware(target){
    const ctx=target.getContext('2d');target.dataset.renderer='software-3d';
    let previous=null,previousSize=0,time=0;
    function render(value){
      time=value;const angle=rotation(value),size=Math.max(1,Math.round(target.clientWidth*Math.min(devicePixelRatio||1,2)));
      if(previous!==null&&Math.abs(angle-previous)<.035&&size===previousSize)return;
      previous=angle;previousSize=size;target.width=target.height=size;
      const focal=size/(2*Math.tan(fov/2)),points=[],rotatedNormals=[];
      for(let i=0;i<count;i++){
        const p=rotate(vertices.slice(i*3,i*3+3),angle),depth=camera[2]-p[2];
        points.push([size/2+p[0]*focal/depth,size/2-(p[1]-camera[1])*focal/depth,depth,p[1]]);
        rotatedNormals.push(rotate(normals.slice(i*3,i*3+3),angle));
      }
      const faces=[];
      // A coarser tessellation uses the same surface vertices without holes.
      for(const {offset,rings,segments} of surfaces){
        for(let r=0;r<rings;r+=2)for(let a=0;a<segments;a+=2){
          const r1=Math.min(r+2,rings),a1=Math.min(a+2,segments);
          const q=offset+r*(segments+1)+a,w=offset+r1*(segments+1)+a;
          for(const ids of [[q,w,offset+r*(segments+1)+a1],[offset+r*(segments+1)+a1,w,offset+r1*(segments+1)+a1]])
            faces.push({ids,depth:ids.reduce((sum,id)=>sum+points[id][2],0)/3});
        }
      }
      faces.sort((a,b)=>b.depth-a.depth);
      const light=normalize([-.7,1,1.2]);
      for(const face of faces){
        const n=normalize(face.ids.reduce((v,id)=>v.map((x,i)=>x+rotatedNormals[id][i]),[0,0,0]));
        const diffuse=Math.max(dot(n,light),0),spec=Math.pow(Math.max(dot(n,normalize([-.35,.5,1.6])),0),35);
        const base=points[face.ids[0]][3]<-1.09?[5,19,26]:[5,102,139];
        const color=base.map((v,i)=>Math.min(255,Math.round(v*(.25+diffuse*.95)+[115,190,220][i]*spec*.7)));
        ctx.fillStyle=ctx.strokeStyle=`rgb(${color.join(',')})`;ctx.lineWidth=.5;
        ctx.beginPath();face.ids.forEach((id,i)=>i?ctx.lineTo(points[id][0],points[id][1]):ctx.moveTo(points[id][0],points[id][1]));ctx.closePath();ctx.fill();ctx.stroke();
      }
    }
    const api={render,kind:'3d-mesh'};new ResizeObserver(()=>render(time)).observe(target);render(0);return api;
  }
})();
