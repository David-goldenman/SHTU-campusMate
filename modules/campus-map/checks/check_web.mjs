import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const base = process.argv[2] || 'http://127.0.0.1:16666';
const output = resolve('.codex/tmp/campus-map-ui');
const profile = resolve(output, 'browser-' + process.pid);
await mkdir(profile, {recursive:true});
function browser(action) {
  const result = spawnSync(process.execPath, [resolve('scripts/browser.mjs')], {
    input:JSON.stringify({action, profile, url:'about:blank', headless:true}), encoding:'utf8', windowsHide:true,
  });
  assert.equal(result.status, 0, result.stderr);
}
function fixture() {
  const original = window.fetch.bind(window);
  const state = window.mapCheck = {writes:[], days:[], unavailable:false,
    conditions:{version:0, account_revision:'synthetic', items:[], history:[], undo_available:false}};
  const json = value => new Response(JSON.stringify(value), {headers:{'Content-Type':'application/json'}});
  window.fetch = async (url, options = {}) => {
    const target = new URL(url, location.origin), path = target.pathname, method = options.method || 'GET';
    if (path === '/api/v1/bootstrap') {
      const value = await (await original(url, options)).json();
      // Keep synthetic theme checks in browser-only mode; never save real workspace preferences.
      delete value.settings.appearance;
      // Exercise the real app shell and theme loader without unrelated background modules.
      value.modules = value.modules.filter(module => module.id === 'campus-map');
      return json(value);
    }
    if (path === '/api/v1/modules/campus-map/day') {
      const day = target.searchParams.get('date'); state.days.push(day);
      if (day === '2026-10-22') await new Promise(resolve => setTimeout(resolve, 250));
      return json({date:day, available:!state.unavailable, status:state.unavailable?'unavailable':'partial',
        issues:state.unavailable?['时间表模块未启用，地图仍可查看。']:['合成来源尚未就绪'],
        events:state.unavailable?[]:[
          {id:'synthetic-class', title:'合成课程 '+day, event_type:'class', location:'信息学院1D-102', period_start:3, period_end:4},
          {id:'synthetic-deadline', title:'合成作业', event_type:'deadline', at:day+'T00:30:00+08:00'},
        ]});
    }
    if (path === '/api/v1/modules/campus-map/conditions') {
      if (method === 'POST') {
        const body = JSON.parse(options.body); state.writes.push(body);
        state.conditions = {...state.conditions, version:state.conditions.version+1,
          items:[{...body.item, id:'synthetic-condition', created_at:'2026-10-18T12:00:00+08:00'}]};
      }
      return json(state.conditions);
    }
    if (path === '/api/v1/modules/campus-map/discovery') return json({version:0, account_revision:'synthetic',
      settings:{enabled:false, official:true, mail:true}, items:[], sources:{}, running:false, coverage:'合成检查，不读取真实邮件。'});
    if (method !== 'GET') throw new Error('Unexpected write: '+path);
    return original(url, options);
  };
}

let socket;
browser('open');
try {
  const port = (await readFile(profile+'/DevToolsActivePort','utf8')).split(/\r?\n/)[0];
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  let serial = 0; const pending = new Map(), errors = [];
  socket.addEventListener('message', ({data}) => {
    const message = JSON.parse(data);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    const task = pending.get(message.id); if (!task) return;
    clearTimeout(task.timer); pending.delete(message.id);
    message.error?task.reject(new Error(JSON.stringify(message.error))):task.resolve(message.result);
  });
  const command = (method,params={}) => new Promise((resolve,reject) => {
    const id = ++serial, timer = setTimeout(() => reject(new Error(method)), 20000);
    pending.set(id,{resolve,reject,timer}); socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate = expression => command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true}).then(result => {
    assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
  });
  const wait = expression => evaluate(`(async()=>{for(let i=0;i<200;i++){if(${expression})return;await new Promise(r=>setTimeout(r,50));}throw new Error('Timed out: '+${JSON.stringify(expression)});})()`);
  const ready = () => wait("document.querySelector('.map-building') && document.querySelector('[data-route-start]')?.disabled===false && document.querySelector('[data-condition-status]')?.textContent.includes('已确认限制')");
  await command('Page.enable'); await command('Runtime.enable');
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`(${fixture})()`});
  await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await command('Page.navigate',{url:base+'/#campus-map?date=2026-10-21&event=synthetic-class'});
  await ready();
  await wait("document.querySelector('[data-detail]').textContent.includes('信息学院1')");
  assert(await evaluate("document.querySelector('[data-agenda]').textContent.includes('第 3–4 节') && document.querySelector('[data-agenda]').textContent.includes('截止 00:30')"));
  await evaluate("var start=document.querySelector('[data-route-start]');start.value=[...start.options].find(o=>o.text==='北门').value;start.dispatchEvent(new Event('change',{bubbles:true}));document.querySelector('[data-walk-event]').click()");
  await wait("document.querySelector('.map-route-line') && document.querySelector('.map-route-course')");
  await evaluate("for(const day of ['2026-10-22','2026-10-23']){const input=document.querySelector('[data-date]');input.value=day;input.dispatchEvent(new Event('change',{bubbles:true}));}new Promise(r=>setTimeout(r,400))");
  assert(await evaluate("document.querySelector('[data-agenda]').textContent.includes('2026-10-23') && !document.querySelector('[data-agenda]').textContent.includes('2026-10-22') && document.querySelector('[data-route-end]').value===''"));
  await evaluate("document.querySelector('[data-walk-event]').click();document.querySelector('.map-maintenance').open=true;document.querySelector('[data-condition-new]').click();var form=document.querySelector('[data-condition-form]');var values={title:'合成北门封闭',state:'confirmed',place_id:document.querySelector('[data-route-start]').value,starts_on:'2026-10-18',review_on:'2026-10-25',source_kind:'onsite',source_title:'合成现场核实',source_date:'2026-10-18',note:'合成检查：北门行人通道暂时关闭'};for(const [key,value] of Object.entries(values)){form.elements[key].value=value;form.elements[key].dispatchEvent(new Event('input',{bubbles:true}));}form.requestSubmit()");
  await wait("mapCheck.writes.length===1 && document.querySelector('[data-route-result]').textContent.includes('已确认通行限制') && !document.querySelector('.map-route-line')");
  assert.equal(await evaluate('mapCheck.writes[0].account_revision'),'synthetic');
  await evaluate("mapCheck.conditions.items=[];document.querySelector('[data-condition-reload]').click();document.querySelector('.map-maintenance').open=false");
  await wait("document.querySelector('.map-route-line')");

  for (const theme of ['default','observatory','star-notes','arknights']) {
    await evaluate(`(async()=>{const appearance=await import('/assets/themes/appearance.js');await appearance.themeContext().select(${JSON.stringify(theme)});})()`);
    await ready();
    assert.equal(await evaluate('document.documentElement.dataset.theme'),theme);
    await evaluate("document.querySelector('.map-label[data-building]').dispatchEvent(new MouseEvent('click',{bubbles:true}))");
    await wait("document.querySelector('.map-label.is-selected text')");
    const contrast=await evaluate(`(()=>{const label=document.querySelector('.map-label.is-selected'),ctx=document.createElement('canvas').getContext('2d');
      const light=color=>{ctx.fillStyle=color;ctx.fillRect(0,0,1,1);const c=[...ctx.getImageData(0,0,1,1).data].slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return c[0]*.2126+c[1]*.7152+c[2]*.0722;};
      const a=light(getComputedStyle(label.querySelector('text')).fill),b=light(getComputedStyle(label.querySelector('.map-label-bg')).fill);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);})()`);
    assert(contrast>=4.5,theme+' selected-building label contrast '+contrast);
    if(theme==='arknights')assert.equal(await evaluate("getComputedStyle(document.querySelector('.map-panel')).borderTopLeftRadius"),'0px');
    for (const [width,height,label] of [[1440,1100,'desktop'],[390,844,'mobile']]) {
      await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<800});
      await evaluate("scrollTo(0,0);new Promise(r=>setTimeout(r,400))");
      assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),theme+' '+label+' overflow');
      await writeFile(resolve(output,theme+'-'+label+'.png'),Buffer.from((await command('Page.captureScreenshot',{captureBeyondViewport:false})).data,'base64'));
    }
  }
  await evaluate("mapCheck.unavailable=true;document.querySelector('[data-day=next]').click()");
  await wait("document.querySelector('[data-agenda]').textContent.includes('日程暂不可用')");
  assert(await evaluate("document.querySelectorAll('.map-building').length>50 && !document.querySelector('[data-route-start]').disabled"));
  await evaluate("window.oldMap=document.querySelector('.campus-map');location.hash='settings'");
  await wait("!document.querySelector('.campus-map') && ![...document.querySelectorAll('link[rel=stylesheet]')].some(link=>link.href.includes('/campus-map/'))");
  assert(await evaluate("!oldMap.isConnected && !oldMap.classList.contains('campus-map')"));
  assert.deepEqual(errors,[]);
  console.log('PASS: real app navigation, dated timetable/deep links, route planning and restrictions, four themes on desktop/mobile, optional timetable and cleanup');
} finally {socket?.close();browser('close');}
