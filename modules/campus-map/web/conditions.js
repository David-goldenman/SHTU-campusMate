// A planned end is a review cue, never evidence that a closed route reopened.
export function conditionPhase(item,day) {
  if(['resolved','withdrawn'].includes(item.state))return item.state;
  if(item.starts_on>day)return 'scheduled';
  const due=day>=item.review_on||item.expected_end&&day>item.expected_end;
  return item.state==='pending'?(due?'pending_due':'pending'):(due?'review_due':'confirmed');
}
export const phaseLabels={pending:'待核实',pending_due:'待核实 · 已到复核日',confirmed:'已确认',review_due:'需复核 · 保持限制',scheduled:'计划中',resolved:'已恢复',withdrawn:'已撤回'};
export function segmentHitsBounds(a,b,bounds) {
  if(!bounds||bounds.length!==4||!bounds.every(Number.isFinite))return false;
  const [x1,y1,x2,y2]=bounds;
  const dx=b[0]-a[0],dy=b[1]-a[1],p=[-dx,dx,-dy,dy],q=[a[0]-x1,x2-a[0],a[1]-y1,y2-a[1]];
  let low=0,high=1;
  for(let i=0;i<4;i++) {
    if(p[i]===0){if(q[i]<0)return false;}
    else {const t=q[i]/p[i];if(p[i]<0)low=Math.max(low,t);else high=Math.min(high,t);}
  }
  return low<=high;
}
export function conditionHitsEdge(item,edge) {
  return item.scope==='edges'?item.edge_keys.includes(edge.key):item.scope==='area'?segmentHitsBounds(edge.p,edge.q,item.bounds):false;
}
export function conditionPlaceIds(item,buildings) {
  if(item.scope==='place')return [item.place_id];
  if(item.scope!=='area'||item.bounds.length!==4)return [];
  const [x1,y1,x2,y2]=item.bounds;
  return buildings.filter(b=>{const center=b.polygon.reduce((v,p)=>[v[0]+p[0]/b.polygon.length,v[1]+p[1]/b.polygon.length],[0,0]);return center[0]>=x1&&center[0]<=x2&&center[1]>=y1&&center[1]<=y2;}).map(b=>b.id);
}
export function compileConditions(base,items,day,buildings,avoidPending=false) {
  const placeIds=new Set(buildings.map(b=>b.id)),blockedPlaces=new Map(),blockedEdges=new Set(),invalid=[],active=[];
  for(const item of items) {
    const phase=conditionPhase(item,day);if(['resolved','withdrawn','scheduled'].includes(phase))continue;
    const blocks=item.effect==='blocked'&&(item.state==='confirmed'||avoidPending);
    const missing=item.scope==='place'?!placeIds.has(item.place_id):item.scope==='edges'?item.edge_keys.some(k=>!base.knownEdgeKeys.has(k)):false;
    const row={...item,phase,blocks,missing,affectedPlaces:conditionPlaceIds(item,buildings)};active.push(row);
    if(missing){if(blocks)invalid.push(row);continue;}
    if(blocks)for(const id of row.affectedPlaces)blockedPlaces.set(id,row);
    if(blocks)for(const edge of base.edges)if(conditionHitsEdge(item,edge))blockedEdges.add(edge.key);
  }
  const graph={...base,edges:base.edges.filter(e=>!blockedEdges.has(e.key)),adj:new Map([...base.adj].map(([id,links])=>[id,links.filter(link=>!blockedEdges.has(link.edge.key))]))};
  return {graph,blockedPlaces,blockedEdges,invalid,active};
}
export function routeConditionWarnings(route,state) {
  if(route?.status!=='ok')return [];
  return state.active.filter(item=>!item.blocks&&(item.affectedPlaces.some(id=>[route.start.placeId,route.end.placeId].includes(id))||(
    item.scope==='place'?false:
    item.scope==='edges'?route.segments.some(s=>item.edge_keys.includes(s.edgeKey)):
    route.segments.some(s=>segmentHitsBounds(s.from,s.to,item.bounds)))));
}
