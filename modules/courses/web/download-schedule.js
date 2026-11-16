import {folderStore} from './download-store.js';

export const downloadIntervals = [5,15,30,60];
export const downloadInterval = root => downloadIntervals.includes(root?.checkIntervalMinutes) ? root.checkIntervalMinutes : 15;
const due = (root,time) => root.lastAutoState === 'checking' || !Number.isFinite(root.lastAutoCheckAt) || root.lastAutoCheckAt <= 0
  || time-root.lastAutoCheckAt >= downloadInterval(root)*60000 || root.lastAutoCheckAt > time+300000;

function sleep(delay,signal) {
  return new Promise((resolve,reject)=>{
    const abort=()=>{clearTimeout(timer);reject(signal.reason);};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},delay);
    signal.addEventListener('abort',abort,{once:true});if(signal.aborted)abort();
  });
}

/** Local settings checks are cheap; remote syncs run only at the saved interval. */
export function downloadSchedule(context,downloads,{storage=folderStore(),source,syncSource,
  now=Date.now,pause=sleep,schedule=setTimeout,cancel=clearTimeout,events=globalThis.window}={}) {
  const lifetime=new AbortController(),signal=AbortSignal.any([context.signal,lifetime.signal]);
  let timer,running,stopped=false;
  const dispose=()=>{
    if(stopped)return;stopped=true;lifetime.abort();cancel(timer);
    context.signal.removeEventListener('abort',dispose);
    events?.removeEventListener?.('campus:courses-download-settings',wake);
  };
  const active=async root=>{
    signal.throwIfAborted();const latest=await storage.getRoot(root.revision);
    return latest?.token===root.token && latest.auto;
  };
  async function cycle() {
    let root,started;
    async function finish(state,message) {
      if(!root || signal.aborted)return;
      try {
        await storage.updateRoot(root.revision,latest=>latest?.token===root.token && latest.lastAutoCheckAt===started
          ? {...latest,lastAutoState:state,lastAutoMessage:message} : null);
        await downloads.repaint?.();
      } catch { /* A storage outage must not create repeated background alerts. */ }
    }
    try {
      const roots=await storage.roots();
      if(stopped || signal.aborted || !roots.some(item=>item.auto && due(item,now())) || !globalThis.navigator?.locks)return;
      // Non-waiting Web Locks reject the combination of ifAvailable and signal.
      // Check our lifetime in the callback; network/file requests remain abortable.
      await navigator.locks.request('campusmate-course-auto-check',{ifAvailable:true},async lock=>{
        if(!lock || stopped || signal.aborted)return;
        // The host delays initial background GETs until the foreground has loaded.
        await context.api('/view-state',{signal});
        signal.throwIfAborted();let value=await source(signal);
        root=await storage.getRoot(value.account_revision);
        if(!root?.auto || !due(root,now()))return;
        started=now();let claimed=false;
        await storage.updateRoot(root.revision,latest=>{
          if(latest?.token!==root.token || !latest.auto || !due(latest,started))return null;
          claimed=true;return {...latest,lastAutoCheckAt:started,lastAutoState:'checking',lastAutoMessage:'正在后台检查 Piazza 资料…'};
        });
        if(!claimed)return;
        await downloads.repaint?.();
        if(await root.directory.queryPermission({mode:'readwrite'})!=='granted') {
          await finish('permission','需要重新允许访问总目录，请到课程中心点击“允许访问并继续”。');return;
        }
        if(!await active(root))return;
        if(value.status!=='syncing')await syncSource(signal);
        value=await source(signal);
        const deadline=now()+300000;
        while(value.status==='syncing') {
          if(value.account_revision!==root.revision || !await active(root))return;
          if(now()>=deadline) {await finish('waiting','Piazza 目录仍在同步，将在下次检查时继续。');return;}
          await pause(2000,signal);value=await source(signal);
        }
        if(value.account_revision!==root.revision || !await active(root))return;
        if(['error','not_connected','login_required','verification_required'].includes(value.status)) {
          throw new Error(typeof value.message === 'string' && value.message.trim()
            ? value.message : 'Piazza 暂时无法同步，请检查连接或完成登录验证；稍后会自动重试。');
        }
        const snapshot=await context.api('/snapshot',{signal});
        if(!await active(root))return;
        await downloads.refresh(snapshot.data?.courses || []);
        await finish('ready','后台检查完成，下次按所选间隔继续。');
      });
    } catch(error) {
      if(!stopped && !signal.aborted)await finish('error',error.message || '后台检查暂未完成，将在下次检查时重试。');
    }
  }
  function check() {
    cancel(timer);
    if(stopped || signal.aborted)return Promise.resolve();
    if(running)return running;
    running=cycle().finally(()=>{
      running=null;
      // This only reads local IndexedDB while idle, including changes in other tabs.
      if(!stopped && !signal.aborted)timer=schedule(check,30000);
    });
    return running;
  }
  function wake() {void check();}
  context.signal.addEventListener('abort',dispose,{once:true});
  events?.addEventListener?.('campus:courses-download-settings',wake);
  if(!signal.aborted)timer=schedule(check,0);else dispose();
  return {check,dispose};
}
