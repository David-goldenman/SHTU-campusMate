const actions={restriction:'疑似施工 / 封路',reopening:'恢复通行线索',caution:'通行影响待核实'};
export function createDiscovery({context,host,onReview,onAccountChange,onUpdate}) {
  const e=context.ui.escape,on=(type,fn)=>host.addEventListener(type,fn,{signal:context.signal});
  let snapshot,busy=false,message='',timer,controller,retired=false,loading=false,settingsDirty=false;
  context.signal.addEventListener('abort',()=>{clearTimeout(timer);controller?.abort();},{once:true});
  function render() {
    if(!snapshot){host.innerHTML=`<p class="map-condition-hint">${e(message||'正在读取自动发现状态…')}</p><button type="button" data-discovery-refresh>刷新自动发现</button>`;return;}
    const pending=snapshot.items.filter(i=>i.state==='pending'),items=retired?snapshot.items:pending;
    host.innerHTML=`<div class="map-discovery-heading"><h3>自动发现 · 待你核实 <span>${pending.length}</span></h3><button type="button" data-discovery-check ${busy||snapshot.running?'disabled':''}>${snapshot.running?'正在检查…':'检查一次'}</button></div><p class="map-condition-hint">从学校公告和校园邮件筛选施工、封路与恢复信息。核实并保存后才影响路线；未处理线索不会自动封路或开放。</p><form data-discovery-settings><label><input type="checkbox" name="enabled" ${snapshot.settings.enabled?'checked':''}>每 30 分钟自动检查</label><label><input type="checkbox" name="official" ${snapshot.settings.official?'checked':''}>校方公开公告</label><label><input type="checkbox" name="mail" ${snapshot.settings.mail?'checked':''}>校园邮箱</label><button type="submit" ${busy?'disabled':''}>保存发现设置</button></form><p class="map-condition-hint">${e(snapshot.coverage)} 本机规则筛选，不向模型发送邮件；应用关闭后停止检查。</p><p class="map-discovery-time">上次完成：${e(snapshot.last_checked?.slice(0,16).replace('T',' ')||'尚未检查')}${snapshot.settings.enabled&&snapshot.next_check?' · 下次约 '+e(snapshot.next_check.slice(0,16).replace('T',' ')):''}</p>${Object.entries(snapshot.sources).map(([key,value])=>`<p class="map-discovery-source"><strong>${key==='mail'?'校园邮箱':'校方公告'}</strong> · ${e(value.message)}${value.needs_auth?` <a href="#settings?tab=accounts">连接校园邮箱 ↗</a>`:""}</p>`).join('')}${message||snapshot.error?`<p role="status" class="map-condition-message">${e(message||snapshot.error)}</p>`:''}<div class="map-condition-toolbar"><button type="button" data-discovery-refresh>刷新列表</button><label><input type="checkbox" data-discovery-retired ${retired?'checked':''}>显示已处理线索</label></div><div class="map-discovery-list">${items.slice().reverse().map(item=>`<article class="map-discovery-item"><div><strong>${e(item.title)}</strong><span>${e(item.state==='pending'?actions[item.action]:item.state==='dismissed'?'已忽略':item.state==='superseded'?'原文已更新，旧线索失效':'已核实应用')}</span></div><small>${item.source==='mail'?'校园邮件':'校方公告'} · ${e(item.date_unknown?'来源日期待核对':item.source_date)}${item.source_revision>1?' · 原文更新第 '+item.source_revision+' 版':''}</small><blockquote>${e(item.evidence)}</blockquote><ul>${item.flags.map(flag=>`<li>${e(flag)}</li>`).join('')}</ul>${item.date_text.length?`<p>原文日期：${e(item.date_text.join('、'))}（需核对生效区间）</p>`:''}<div class="map-condition-actions"><a href="${item.source==='mail'?'#mail?message='+encodeURIComponent(item.source_id):e(item.source_url)}" ${item.source==='mail'?'':'target="_blank" rel="noopener noreferrer"'}>查看原文 ↗</a>${item.state==='pending'?`<button type="button" data-discovery-review="${e(item.id)}" ${busy?'disabled':''}>${item.action==='reopening'?'关联限制并核实恢复':'核实位置与通行影响'}</button><button type="button" data-discovery-dismiss="${e(item.id)}" ${busy?'disabled':''}>忽略此线索</button>`:''}</div></article>`).join('')||'<p class="map-condition-hint">暂无待核实发现。未发现信息不代表校园各处已经确认畅通。</p>'}</div>`;
  }
  function schedule(){clearTimeout(timer);if(!context.signal.aborted)timer=setTimeout(()=>void load(),snapshot?.running?2000:30000);}
  async function load() {
    if(loading||busy||context.signal.aborted)return;loading=true;
    controller?.abort();controller=new AbortController();
    try {const value=await context.api('/discovery',{signal:controller.signal});if(context.signal.aborted)return;const changed=snapshot&&snapshot.account_revision!==value.account_revision;snapshot=value;if(changed){settingsDirty=false;message='账号已切换，已读取当前账号的发现列表。';onAccountChange?.();}onUpdate?.(snapshot.items.filter(i=>i.state==='pending').length);if(!settingsDirty)render();}
    catch(error){if(context.signal.aborted)return;message=error.message||'自动发现暂不可用。';render();}
    finally{loading=false;schedule();}
  }
  async function write(path,method,extra={}) {
    if(!snapshot||busy)return;busy=true;message='';render();
    try {await context.api(path,{method,body:{version:snapshot.version,account_revision:snapshot.account_revision,...extra}});if(context.signal.aborted)return;message=path.endsWith('/check')?'已请求检查，完成后会更新列表。':'已保存。';}
    catch(error){if(context.signal.aborted)return;message=error.message||'操作未完成，请刷新后重试。';}
    finally{busy=false;if(!context.signal.aborted)await load();}
  }
  on('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.hasAttribute('data-discovery-refresh'))void load();
    if(button.hasAttribute('data-discovery-check'))void write('/discovery/check','POST');
    if(button.dataset.discoveryDismiss)void write('/discovery/'+encodeURIComponent(button.dataset.discoveryDismiss)+'/dismiss','POST');
    if(button.dataset.discoveryReview){const lead=snapshot.items.find(i=>i.id===button.dataset.discoveryReview);if(lead)void onReview(lead,snapshot.account_revision);}
  });
  on('change',event=>{if(event.target.closest('[data-discovery-settings]'))settingsDirty=true;if(event.target.hasAttribute('data-discovery-retired')){retired=event.target.checked;render();}});
  on('submit',event=>{if(!event.target.matches('[data-discovery-settings]'))return;event.preventDefault();const form=event.target;settingsDirty=false;void write('/discovery/settings','PUT',Object.fromEntries(['enabled','official','mail'].map(key=>[key,form.elements[key].checked])));});
  render();
  return {load};
}
