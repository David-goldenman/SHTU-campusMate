export async function waitForStyles(){
  await Promise.all([...document.querySelectorAll('link[rel="stylesheet"]')].map(link=>link.sheet?Promise.resolve():new Promise((ok,no)=>{link.addEventListener('load',ok,{once:true});link.addEventListener('error',()=>no(new Error('Stylesheet failed: '+link.href)),{once:true});})));
  await document.fonts.ready;
  const visible=[...document.images].filter(img=>{const rect=img.getBoundingClientRect();return img.getAttribute('src')&&rect.width>0&&rect.top<innerHeight&&rect.bottom>0;});
  await Promise.all(visible.map(img=>img.decode().catch(error=>{throw new Error(`Image not ready: ${img.currentSrc} (${error.message})`);}))); 
}

export function installReplay(definition) {
  const state=window.filmDemo, processed=new Set(),active=new Map(),captures=[],framing=[];
  let previous=-1,transition=-100,clickTime=-100,maxPointerStep=0,maxClickError=0,modalFrames=0;
  const pointer={x:innerWidth-36,y:innerHeight-30};
  const cursor=document.createElement('div');cursor.id='film-pointer';cursor.style.cssText='position:fixed;width:24px;height:30px;z-index:100000;pointer-events:none;filter:drop-shadow(0 1px 2px #2e344040)';
  cursor.hidden=!!definition.mobile;
  cursor.innerHTML='<svg width="24" height="30" viewBox="0 0 24 30"><path d="M3 2 4 24 10 18 14 27 19 25 15 16 23 15Z" fill="#2e3440" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/></svg>';
  document.body.append(cursor);
  const ring=document.createElement('div');ring.style.cssText='position:fixed;width:32px;height:32px;border:2px solid #5e81ac;border-radius:50%;z-index:99999;pointer-events:none;opacity:0';document.body.append(ring);
  ring.hidden=!!definition.mobile;
  const style=document.createElement('style');style.textContent='html{scroll-behavior:auto!important}*,*::before,*::after{animation-play-state:paused!important;transition-duration:0s!important}#main{will-change:opacity,transform}';document.head.append(style);
  if(['observatory','star-notes'].includes(definition.theme))document.querySelectorAll('[aria-label="开场白"]').forEach(node=>node.remove());
  const find=selector=>{const node=document.querySelector(selector);if(!node)throw new Error('Replay target missing: '+selector);return node;};
  const settle=()=>new Promise(r=>setTimeout(r,24));
  const wait=async selector=>{for(let n=0;n<160;n++){if(document.querySelector(selector)){await window.filmStyleReady();return;}await new Promise(r=>setTimeout(r,25));}throw new Error('Replay view missing: '+selector);};
  const point=selector=>{const node=find(selector),r=node.getBoundingClientRect();return node.matches('input,textarea')?{x:r.right-18,y:r.bottom-18}:{x:r.left+r.width/2,y:r.top+r.height/2};};
  const arrive=selector=>{if(definition.mobile)return;const target=point(selector),error=Math.hypot(pointer.x-target.x,pointer.y-target.y);maxClickError=Math.max(maxClickError,error);if(error>5)throw new Error(`Pointer did not reach ${selector}: ${error.toFixed(1)}px`);};
  const smooth=value=>{const p=Math.max(0,Math.min(1,value));return p*p*(3-2*p);};
  state.advance=async t=>{
    if(t<previous)throw new Error('Replay time must increase');
    let dirty=previous<0;const oldPointer={...pointer};
    for(const [i,step] of definition.steps.entries()){
      if(t+0.00001<step.at||processed.has(i))continue;
      processed.add(i);dirty=true;
      if(step.type==='move'){
        const to=point(step.selector),dx=to.x-pointer.x,dy=to.y-pointer.y,distance=Math.hypot(dx,dy),bend=Math.min(56,distance*.12);
        active.set(i,{...step,from:{...pointer},to,control:{x:(pointer.x+to.x)/2-dy/(distance||1)*bend,y:(pointer.y+to.y)/2+dx/(distance||1)*bend}});
      }
      if(step.type==='click'){
        arrive(step.selector);find(step.selector).click();clickTime=t;
        if(step.ready)await wait(step.ready);
        if(!document.activeElement.matches('input,textarea,select'))document.activeElement.blur();
        if(step.transition)transition=t;
      }
      if(step.type==='navigate'){location.hash=step.route;await wait(step.ready);transition=t;}
      if(step.type==='close'){arrive(step.selector);find(step.selector).click();clickTime=t;}
      if(step.type==='type'){
        const node=find(step.selector),text=step.replyPrompt?state.reply.prompt:step.text;
        arrive(step.selector);node.focus({preventScroll:true});active.set(i,{...step,node,text,shown:-1});clickTime=t;
      }
      if(step.type==='scroll'){
        const target=document.scrollingElement,from=target.scrollTop,to=from+find(step.selector).getBoundingClientRect().top-(step.top||80);
        active.set(i,{...step,node:target,from,to:Math.min(to,target.scrollHeight-innerHeight)});
      }
      if(step.type==='scrollModal'){
        const node=find('#dialog'),target=find(step.selector);
        active.set(i,{...step,type:'scroll',node,from:node.scrollTop,to:Math.min(node.scrollHeight-node.clientHeight,node.scrollTop+target.getBoundingClientRect().top-node.getBoundingClientRect().top-130)});
      }
      if(step.type==='scrollInside'){
        const node=find(step.container),target=find(step.selector);
        active.set(i,{...step,type:'scroll',node,from:node.scrollTop,to:Math.min(node.scrollHeight-node.clientHeight,node.scrollTop+target.getBoundingClientRect().top-node.getBoundingClientRect().top-(step.top||24))});
      }
      if(step.type==='scrollChat'){
        const node=find('.study-messages');active.set(i,{...step,type:'scroll',node,from:node.scrollTop,to:(node.scrollHeight-node.clientHeight)*step.fraction});
      }
      if(step.type==='activity')state.emit({type:'activity',steps:step.steps});
      if(step.type==='stream'){state.emit({type:'reset'});active.set(i,{...step,text:state.reply.text,shown:0});}
      if(step.type==='complete')state.complete();
      if(step.type==='notify')await state.notify();
      if(step.type==='capture')captures.push({selector:step.selector,name:step.name});
      if(step.type==='focus'){
        const rect=step.selector?find(step.selector).getBoundingClientRect():null,padding=step.padding||0;
        framing.push({at:step.at,duration:step.duration||.8,label:step.label||'',rect:rect?{x:(rect.x-padding)*1840/innerWidth,y:(rect.y-padding)*900/innerHeight,width:(rect.width+padding*2)*1840/innerWidth,height:(rect.height+padding*2)*900/innerHeight}:null});
      }
      if(step.type==='select'){arrive(step.selector);const node=find(step.selector);node.value=step.value;node.dispatchEvent(new Event('change',{bubbles:true}));clickTime=t;}
    }
    for(const [i,item] of active){
      const amount=Math.max(0,Math.min(1,(t-item.at)/item.duration)),progress=smooth(amount);
      if(item.type==='move'){for(const axis of ['x','y'])pointer[axis]=(1-progress)**2*item.from[axis]+2*(1-progress)*progress*item.control[axis]+progress**2*item.to[axis];dirty=true;}
      if(item.type==='scroll'){item.node.scrollTop=Math.round(item.from+(item.to-item.from)*progress);dirty=true;}
      if(item.type==='type'){
        const count=Math.floor(item.text.length*amount);
        if(count!==item.shown){item.node.value=item.text.slice(0,count);item.node.dispatchEvent(new Event('input',{bubbles:true}));item.shown=count;dirty=true;}
      }
      if(item.type==='stream'){
        const count=Math.floor(item.text.length*amount);
        if(count!==item.shown){state.emit({type:'delta',text:item.text.slice(item.shown,count)});item.shown=count;dirty=true;}
      }
      if(amount===1)active.delete(i);
    }
    const main=document.querySelector('#main'),p=Math.max(0,Math.min(1,(t-transition)/.85));
    main.style.opacity=String(smooth(p));main.style.transform=`translateY(${Math.round((1-smooth(p))*14)}px)`;
    if(p<1||previous-transition<.85)dirty=true;
    const pointerStep=Math.hypot(pointer.x-oldPointer.x,pointer.y-oldPointer.y);maxPointerStep=Math.max(maxPointerStep,pointerStep);
    if(previous>=0&&pointerStep>48)throw new Error(`Pointer discontinuity: ${pointerStep.toFixed(1)}px`);
    // Native dialogs paint above the document stacking order.
    const layer=document.querySelector('dialog[open]')||document.body;
    if(cursor.parentNode!==layer)layer.append(cursor,ring);
    cursor.style.left=pointer.x+'px';cursor.style.top=pointer.y+'px';
    if(!definition.mobile){
      const rect=cursor.getBoundingClientRect();
      if(Math.hypot(rect.x-pointer.x,rect.y-pointer.y)>1||!cursor.checkVisibility())throw new Error('Pointer viewport or visibility changed');
      if(layer.tagName==='DIALOG')modalFrames++;
    }
    const pulse=Math.max(0,Math.min(1,(t-clickTime)/.34));
    ring.style.left=pointer.x-16+'px';ring.style.top=pointer.y-16+'px';ring.style.transform=`scale(${.5+pulse})`;ring.style.opacity=String((1-pulse)*.65);
    if(pulse<1||previous-clickTime<.34)dirty=true;
    if(state.streamStarted&&state.history.length===0){document.querySelectorAll('.spinner').forEach(node=>node.style.transform=`rotate(${Math.round(t*240)}deg)`);dirty=true;}
    let routeMoving=false;
    const route=document.querySelector('.map-route-line');
    if(route){
      const start=definition.steps.find(s=>definition.mobile?s.type==='select'&&s.selector==='[data-route-end]':s.type==='click'&&s.selector.includes('data-walk-event'))?.at??0,matrix=route.getScreenCTM(),length=route.getTotalLength()*Math.hypot(matrix.a,matrix.b),draw=smooth((t-start)/1.6);
      route.style.strokeDasharray=draw===1?'none':`${length} ${length}`;route.style.strokeDashoffset=String(length*(1-draw));
      routeMoving=draw<1;dirty ||= routeMoving;
    }
    await settle();previous=t;
    const still=active.size===0&&p===1&&pulse===1&&!routeMoving&&(!state.streamStarted||state.history.length>0);
    const next=still?definition.steps.find((_,i)=>!processed.has(i))?.at:undefined;
    return {dirty,next:still?(next??definition.seconds):undefined,captures:captures.splice(0),framing,pointer:{maxStep:maxPointerStep,maxClickError,modalFrames},unexpected:state.unexpected,events:state.replayEvents,invalidDialog:document.querySelector('#dialog[open]')?.innerText.includes('undefined')||false};
  };
}
