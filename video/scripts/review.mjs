export function reviewOffsets(scene,operations){
  if(scene.id==='themes')return [2,7.5,13];
  if(scene.id==='closing')return [3.5,6.3];
  if(scene.id==='group-sources')return [3,6.5];
  const steps=operations.find(o=>o.id===scene.clip)?.steps||[];
  const offsets=[2];
  for(const step of steps){
    if(step.type==='focus'&&step.selector)offsets.push(step.at+step.duration+.7);
    if(step.type==='capture'&&step.name==='agenda')offsets.push(step.at+1.7);
    if(step.type==='type')offsets.push(step.at+step.duration*.6);
    if(step.type==='stream')offsets.push(step.at+step.duration*.5);
    if(step.type==='complete')offsets.push(step.at+1.4);
    if(step.type==='click'&&step.ready)offsets.push(step.at+1);
    if(step.type==='close')offsets.push(step.at-.3);
    if(scene.id==='mobile'&&step.type==='scroll')offsets.push(step.at+step.duration+1);
    if(step.type==='click'&&/data-(messages|decision|settings-tab)|study-references/.test(step.selector))offsets.push(step.at+.9);
  }
  if(steps.length)offsets.push(Math.max(...steps.map(s=>s.at+(s.duration||0)))+1);
  return [...new Set(offsets.map(n=>Math.round(n*60)/60))].filter(n=>n<scene.seconds-1.2).sort((a,b)=>a-b).filter((n,i,values)=>!i||n-values[i-1]>.2);
}
