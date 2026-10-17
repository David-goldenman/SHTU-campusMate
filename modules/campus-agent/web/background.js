import {icon} from '/assets/icons.js';

export async function mount(container,context) {
  const e=context.ui.escape,removeStyle=context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('campus-agent-widget');
  container.innerHTML='<aside class="campus-agent-peek" aria-live="polite" hidden></aside><a class="campus-agent-button" href="#notifications" aria-label="打开通知中心"><span data-agent-light aria-hidden="true"></span>'+icon('◌')+'<span data-agent-count hidden></span></a>';
  let timer,owner,seen=new Map(),initialized=false,shown;
  async function refresh(){
    clearTimeout(timer);
    const value=await context.api('/status');if(context.signal.aborted)return;
    if(owner!==value.owner){seen.clear();initialized=false;owner=value.owner;container.querySelector('aside').hidden=true;}
    const unread=value.notices.filter(item=>!item.read && (item.importance!=='normal'||!(item.citations||[]).some(source=>source.source==='mail'))),badge=container.querySelector('[data-agent-count]');badge.hidden=!unread.length;badge.textContent=String(unread.length);
    if(shown&&!unread.some(item=>item.id===shown)){container.querySelector('aside').hidden=true;shown=null;}
    const light=container.querySelector('[data-agent-light]');light.dataset.state=value.running?'running':value.error?'error':value.enabled?'ready':'off';const entry=container.querySelector('.campus-agent-button');entry.dataset.state=light.dataset.state;entry.title=value.error?'后台检查遇到问题':'通知中心';entry.setAttribute('aria-label','打开通知中心，'+unread.length+' 条未读');
    const fresh=unread.find(item=>seen.get(item.id)!==item.source_revision);
    if(initialized&&fresh&&location.hash.split('?')[0]!=='#notifications'){
      shown=fresh.id;
      const peek=container.querySelector('aside');peek.hidden=false;peek.innerHTML=`<strong>${e(fresh.title)}</strong><p>${e(fresh.summary.slice(0,160))}</p><div><a href="#notifications">查看通知</a><button class="text-button" type="button">稍后</button></div>`;peek.querySelector('button').onclick=()=>{peek.hidden=true;};peek.querySelector('a').onclick=()=>{peek.hidden=true;};
    }
    for(const item of value.notices)seen.set(item.id,item.source_revision);
    initialized=true;timer=setTimeout(()=>refresh().catch(retry),6000);
  }
  function retry(){if(!context.signal.aborted)timer=setTimeout(()=>refresh().catch(retry),15000);}
  const cleanup=()=>{clearTimeout(timer);removeStyle();container.replaceChildren();};context.signal.addEventListener('abort',cleanup,{once:true});
  try{await refresh();}catch{retry();}
  return cleanup;
}
