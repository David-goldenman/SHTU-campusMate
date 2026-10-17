// Route only on shared OSM nodes. Display-line crossings are not intersections.
const MX=111320*Math.cos(31.18*Math.PI/180), MY=111320;
const xy=p=>[p[0]*MX,p[1]*MY];
const distance=(a,b)=>Math.hypot((a[0]-b[0])*MX,(a[1]-b[1])*MY);
const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
const yes=value=>['yes','designated','permissive','official'].includes(value);
const denied=value=>['no','private','use_sidepath'].includes(value);
function projection(point,a,b) {
  const p=xy(point),u=xy(a),v=xy(b),dx=v[0]-u[0],dy=v[1]-u[1];
  const t=Math.max(0,Math.min(1,((p[0]-u[0])*dx+(p[1]-u[1])*dy)/(dx*dx+dy*dy||1)));
  const foot=mix(a,b,t);return {point:foot,t,gap:distance(point,foot)};
}
export function inside(point,polygon) {
  let result=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
    const a=polygon[i],b=polygon[j];
    if(projection(point,a,b).gap<.3)return true;
    if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])result=!result;
  }
  return result;
}
export function walkable(tags={},node=false) {
  if(denied(tags.foot)||(!yes(tags.foot)&&denied(tags.access)))return false;
  if(tags.indoor&&tags.indoor!=='no'||tags.tunnel&&tags.tunnel!=='no'||tags.level&&Number(tags.level)!==0||Number(tags.layer)<0)return false;
  if(node)return !['wall','fence','hedge','retaining_wall'].includes(tags.barrier);
  if(Number(tags.layer)>0&&!yes(tags.bridge))return false;
  if(tags.motorroad==='yes'||tags.construction)return false;
  return ['footway','path','pedestrian','steps','residential','service','living_street','unclassified'].includes(tags.highway)||tags.highway==='cycleway'&&yes(tags.foot);
}
export function buildWalkingGraph(network) {
  const nodes=new Map(),adj=new Map(),edges=[];
  for(const [id,node] of Object.entries(network.nodes))if(walkable(node.tags,true)){nodes.set(id,node.point);adj.set(id,[]);}
  const add=(a,b,edge)=>adj.get(a).push({to:b,edge,length:edge.length});
  for(const way of network.ways) {
    if(!walkable(way.tags))continue;
    for(let i=1;i<way.refs.length;i++) {
      const a=way.refs[i-1],b=way.refs[i],p=nodes.get(a),q=nodes.get(b);if(!p||!q||a===b)continue;
      const length=distance(network.nodes[a].wgs||p,network.nodes[b].wgs||q);if(!Number.isFinite(length)||length===0)continue;
      const samples=Math.ceil(length/10);
      if(network.boundary?.length&&Array.from({length:samples+1},(_,n)=>mix(p,q,n/samples)).some(v=>!inside(v,network.boundary)))continue;
      const edge={id:edges.length,a,b,p,q,length,way:way.id,tags:way.tags,forward:way.tags['oneway:foot']!=='-1',backward:!['yes','1','true'].includes(way.tags['oneway:foot'])};
      edges.push(edge);if(edge.forward)add(a,b,edge);if(edge.backward)add(b,a,edge);
    }
  }
  return {nodes,adj,edges};
}
// The endpoint is a point on an outdoor road near the footprint, never an indoor connector.
export function snapPlace(graph,place,maxGap=60) {
  if(!place?.polygon?.length)return null;
  const polygon=place.polygon,center=polygon.reduce((a,p)=>[a[0]+p[0]/polygon.length,a[1]+p[1]/polygon.length],[0,0]);
  let best;
  for(const edge of graph.edges) {
    const options=polygon.map(p=>projection(p,edge.p,edge.q));
    for(const [point,t] of [[edge.p,0],[edge.q,1]]) {
      const gaps=polygon.map((p,i)=>projection(point,p,polygon[(i+1)%polygon.length]).gap);
      options.push({point,t,gap:Math.min(...gaps)});
    }
    for(const option of options) {
      // Official footprints and OSM roads are independently surveyed; do not draw across the building.
      if(inside(option.point,polygon)&&option.gap>.5)continue;
      const score=option.gap+distance(center,option.point)*.015;
      if(option.gap<=maxGap&&(!best||score<best.score))best={...option,score,edge,placeId:place.id};
    }
  }
  return best||null;
}
const heading=(a,b)=>Math.atan2((b[0]-a[0])*MX,(b[1]-a[1])*MY)*180/Math.PI;
const delta=(a,b)=>(b-a+540)%360-180;
const compass=angle=>['北','东北','东','东南','南','西南','西','西北'][Math.round((angle+360)/45)%8];
const roadName=tags=>tags.name||(tags.highway==='steps'?'室外台阶':['footway','path','pedestrian'].includes(tags.highway)?'校内步行道':'校内道路');
export function routeSteps(segments) {
  const groups=[];
  for(const segment of segments.filter(s=>s.length>.5)) {
    const angle=heading(segment.from,segment.to),last=groups.at(-1),name=roadName(segment.tags);
    if(last&&last.name===name&&(last.way===segment.way||Math.abs(delta(last.lastAngle,angle))<35)){last.length+=segment.length;last.lastAngle=angle;last.way=segment.way;}
    else groups.push({name,length:segment.length,angle,lastAngle:angle,way:segment.way});
  }
  return groups.map((g,i)=>{
    const turn=i?delta(groups[i-1].lastAngle,g.angle):0;
    const action=!i?'向'+compass(g.angle)+'出发':Math.abs(turn)<30?'继续直行':Math.abs(turn)>150?'折返':turn>0?'右转':'左转';
    return {text:action+'，沿'+g.name,length:g.length};
  });
}
export function planWalk(graph,startPlace,endPlace) {
  if(!startPlace||!endPlace)return {status:'missing'};
  if(startPlace.id===endPlace.id)return {status:'same'};
  const start=snapPlace(graph,startPlace),end=snapPlace(graph,endPlace);
  if(!start||!end)return {status:'unmapped',endpoint:!start?'start':'end'};
  const adjacency=new Map([...graph.adj].map(([id,items])=>[id,[...items]]));
  adjacency.set('@start',[]);adjacency.set('@end',[]);
  const add=(a,b,edge,length,from,to)=>adjacency.get(a).push({to:b,edge,length,from,toPoint:to});
  if(start.edge.forward)add('@start',start.edge.b,start.edge,(1-start.t)*start.edge.length,start.point,start.edge.q);
  if(start.edge.backward)add('@start',start.edge.a,start.edge,start.t*start.edge.length,start.point,start.edge.p);
  if(end.edge.forward)add(end.edge.a,'@end',end.edge,end.t*end.edge.length,end.edge.p,end.point);
  if(end.edge.backward)add(end.edge.b,'@end',end.edge,(1-end.t)*end.edge.length,end.edge.q,end.point);
  if(start.edge===end.edge&&((end.t>=start.t&&start.edge.forward)||(end.t<=start.t&&start.edge.backward)))add('@start','@end',start.edge,Math.abs(end.t-start.t)*start.edge.length,start.point,end.point);
  const distances=new Map([['@start',0]]),previous=new Map(),pending=new Set(['@start']),visited=new Set();
  while(pending.size) {
    let id;for(const candidate of pending)if(id===undefined||distances.get(candidate)<distances.get(id))id=candidate;
    pending.delete(id);if(id==='@end')break;visited.add(id);
    for(const link of adjacency.get(id)||[]) {
      if(visited.has(link.to))continue;
      const value=distances.get(id)+link.length;
      if(value<(distances.get(link.to)??Infinity)){distances.set(link.to,value);previous.set(link.to,{id,link});pending.add(link.to);}
    }
  }
  if(!distances.has('@end'))return {status:'disconnected'};
  const segments=[];
  for(let id='@end';id!=='@start';) {
    const prev=previous.get(id),link=prev.link;
    segments.push({from:link.from||graph.nodes.get(prev.id),to:link.toPoint||graph.nodes.get(id),length:link.length,way:link.edge.way,tags:link.edge.tags});id=prev.id;
  }
  segments.reverse();const length=distances.get('@end');
  return {status:'ok',start,end,length,minutes:Math.max(1,Math.ceil(length/80)),segments,points:[start.point,...segments.map(s=>s.to)],steps:routeSteps(segments),stairs:segments.some(s=>s.tags.highway==='steps')};
}
