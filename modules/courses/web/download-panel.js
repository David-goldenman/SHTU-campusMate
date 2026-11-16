import {courseFiles, downloadFiles, readResponse} from './downloads.js';
import {downloadKey, folderStore} from './download-store.js';
import {courseFolder, withDownloadLock, savedRoot, removeEmptyCourseFolders} from './download-folders.js';
import {downloadIntervals, downloadInterval} from './download-schedule.js';

const autoEnabled = (root,binding) => root?.auto === true && binding.auto !== false;

export function downloadNotice(course,directory,result) {
  if (!result.saved.length) return null;
  return {course:course.code || course.title,directory:directory.name,at:Date.now(),count:result.saved.length,
    names:result.saved.slice(0,20).map(file=>file.name),remaining:result.failed.length+result.remaining.length};
}

export function downloadNoticeMessage(notices) {
  if (!notices.length) return '';
  const messages = notices.slice(0,3).map(notice=>`${notice.course}：已保存 ${notice.count} 份新增或更新的文件到“${notice.directory}”${notice.remaining?`，另有 ${notice.remaining} 份未完成`:''}`);
  if (notices.length > 3) messages.push(`另外 ${notices.length-3} 批已保存 ${notices.slice(3).reduce((count,notice)=>count+notice.count,0)} 份文件，可在课程资料区查看最近拉取记录`);
  return messages.join('；')+'。';
}

export function courseDownloader(context, {storage = folderStore(), request = fetch} = {}) {
  const bindings = new Map(), roots = new Map(), states = new Map(), views = new Map(), manual = new Set(), choices = new Map();
  let revision, courses = [], pending = false, draining = false, drainingJob, current, picking = false, rootHost, rootMessage = '', rootPermission = false;
  const settingsChanged = () => globalThis.window?.dispatchEvent?.(new Event('campus:courses-download-settings'));
  const dispose = () => { current?.controller.abort(); views.clear(); rootHost = undefined; pending = false; manual.clear(); };
  context.signal.addEventListener('abort',dispose,{once:true});
  const bindingFor = course => bindings.get(downloadKey(revision,course.id));
  const rootFor = () => roots.get(revision);
  function status(course, value) { states.set(course.id,value); paint(); }
  const fail = error => { if (!context.signal.aborted && error.name !== 'AbortError') context.ui.toast(error.message); };
  const action = fn => () => { Promise.resolve().then(fn).catch(fail); };
  async function snapshot() {
    const response = await readResponse(await request('/api/v1/modules/piazza/snapshot',{
      signal:AbortSignal.any([context.signal,AbortSignal.timeout(30000)]),credentials:'same-origin',
    }));
    const value = await response.json();
    context.signal.throwIfAborted();
    if (!value.account_revision) throw new Error('请先连接 Piazza 并同步课程资料。');
    if (revision !== value.account_revision) { states.clear(); rootMessage = ''; rootPermission = false; revision = value.account_revision; }
    return value;
  }
  async function load() {
    const [records, savedRoots] = await Promise.all([storage.all(),storage.roots()]);
    bindings.clear(); for (const record of records) bindings.set(record.key,record);
    roots.clear(); for (const root of savedRoots) roots.set(root.revision,root);
  }
  function paintRoot() {
    if (!rootHost?.isConnected) return;
    const e = context.ui.escape, root = rootFor();
    rootHost.innerHTML = `<div><strong>课程资料总目录</strong><p>${root?`保存到 <strong>${e(root.directory.name || '所选总目录')}</strong> / 学期 / 课程`:'选择一次，所有课程共用；后续新增课程会自动按学期建立文件夹。'}</p><label class="course-download-auto"><span class="settings-switch"><input type="checkbox" role="switch" aria-label="所有课程自动拉取" data-auto-all ${root?.auto?'checked':''} ${root?'':'disabled'}><span aria-hidden="true"></span></span><span>自动拉取总开关 · ${root?.auto?'已开启':'已关闭'}</span></label><p class="field-hint">${root?'新增课程默认跟随总开关，每门课也可单独关闭。总开关关闭时暂停所有自动拉取，仍可手动检查下载 Piazza 文件。':'先选择资料总目录，再开启自动拉取。'}每份资料只保留最新版，本地修改保留。</p><p role="status" aria-live="polite" data-root-status>${e(rootMessage)}</p></div><div class="course-download-actions"><button type="button" class="button button-secondary" data-choose ${picking?'disabled':''}>${root?'更换资料总目录':'选择并记住资料总目录'}</button>${root?`<button type="button" class="button button-secondary" data-check-all>${rootPermission?'允许访问并继续':'检查全部课程'}</button><button type="button" class="text-button" data-forget>忘记总目录</button>`:''}</div>`;
    rootHost.querySelector('[data-choose]').onclick = () => { void choose().catch(fail); };
    const interval = downloadInterval(root);
    rootHost.firstElementChild.insertAdjacentHTML('beforeend',`<label class="course-download-interval">后台检查间隔 <select aria-label="自动拉取检查间隔" data-auto-interval ${root?'':'disabled'}>${downloadIntervals.map(minutes=>`<option value="${minutes}" ${minutes===interval?'selected':''}>${minutes===60?'1 小时':minutes+' 分钟'}</option>`).join('')}</select></label><p class="field-hint">工作台网页保持打开时，后台每 ${interval} 分钟检查 Piazza 资料，切换页面后继续；关闭浏览器后暂停。</p>${root?.lastAutoCheckAt?`<p class="field-hint" data-auto-status>最近后台检查：${e(new Date(root.lastAutoCheckAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}))} · ${e(root.lastAutoMessage || '')}</p>`:''}`);
    if (root) {
      rootHost.querySelector('[data-auto-interval]').onchange = event => {
        void setIntervalMinutes(root,Number(event.currentTarget.value)).catch(error=>{paint();fail(error);});
      };
      if (root.lastAutoState === 'permission') rootHost.querySelector('[data-check-all]').textContent = '允许访问并继续';
      rootHost.querySelector('[data-auto-all]').onchange = event => {
        void setGlobalAuto(root,event.currentTarget.checked).catch(error=>{paint();fail(error);});
      };
      rootHost.querySelector('[data-check-all]').onclick = () => { void checkAll(root).catch(fail); };
      rootHost.querySelector('[data-forget]').onclick = action(async()=>{
        const owner = root.revision;
        current?.controller.abort();manual.clear();pending = false;
        await withDownloadLock(context.signal,async()=>{
          if ((await storage.getRoot(owner))?.token !== root.token) throw new Error('总目录设置已变化，请刷新后重试。');
          await storage.removeRoot(owner);
          for (const binding of await storage.all()) if (binding.revision === owner) await storage.remove(binding.key);
        });
        await load();if (revision !== owner) return;
        states.clear();choices.clear();manual.clear();
        rootMessage = '已忘记总目录，磁盘上的文件保留。';paint();settingsChanged();
      });
    }
  }
  function paint() {
    if (context.signal.aborted) return;
    paintRoot();
    const e = context.ui.escape;
    for (const [id,view] of views) {
      const {host,course,count} = view;
      if (!host.isConnected) { views.delete(id); continue; }
      const binding = bindingFor(course), state = states.get(id) || {}, running = current?.course.id === id;
      const follows = (binding ? binding.auto : choices.get(id)) !== false;
      const auto = binding && autoEnabled(rootFor(),binding);
      host.innerHTML = `<div><strong>Piazza 文件${count?' · '+count+' 份':''}</strong><p>${binding?`保存到 <strong>${e(binding.relativePath || binding.directory.name)}</strong>`:'在页顶选择一次资料总目录，每门课自动建立独立文件夹。'}</p><label class="course-download-auto"><span class="settings-switch"><input type="checkbox" role="switch" aria-label="文件自动拉取" data-auto ${follows?'checked':''}><span aria-hidden="true"></span></span><span>文件自动拉取 · ${follows?`跟随总设置（${auto?'已开启':'已暂停'}）`:'此课程已关闭'}</span></label><p class="field-hint">${follows?'总开关开启后，进入课程中心或点击页顶“同步”会自动补齐文件。':'此课程不会自动下载，重新打开课程开关即可跟随总设置。'}可点击“立即检查”手动下载。每份资料只保留最新版；本地修改保留并暂停自动更新。</p><p class="course-download-status" role="status" aria-live="polite">${e(state.message || '')}</p>${running?`<progress max="${Math.max(state.total||1,1)}" value="${state.done||0}" aria-label="课程文件下载进度"></progress>`:''}${state.errors?.length?`<ul>${state.errors.map(message=>`<li>${e(message)}</li>`).join('')}</ul>`:''}</div><div class="course-download-actions">${binding?`<button type="button" class="button button-secondary" data-check ${running?'disabled':''}>${state.permission?'允许访问并继续':'立即检查'}</button>`:''}${running?'<button type="button" class="text-button" data-stop>停止本次</button>':''}</div>`;
      const recent = binding?.lastDownload;
      if (recent?.count) {
        const at = new Date(recent.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'});
        host.firstElementChild.insertAdjacentHTML('beforeend',`<details class="course-download-recent"><summary>最近拉取 ${recent.count} 份文件 · ${e(at)}</summary><ul>${recent.names.map(name=>`<li>${e(name)}</li>`).join('')}</ul>${recent.count>recent.names.length?`<p class="field-hint">另有 ${recent.count-recent.names.length} 份文件已保存。</p>`:''}</details>`);
      }
      // Keep permission requests directly in click handlers to retain user activation.
      host.querySelector('[data-auto]').onchange = event => {
        const enabled = event.currentTarget.checked;
        void setAuto(course,binding,enabled).catch(error=>{paint();fail(error);});
      };
      if (binding) {
        host.querySelector('[data-check]').onclick = () => { void check(course,binding).catch(fail); };
      }
      if (running) host.querySelector('[data-stop]').onclick = () => current?.controller.abort();
    }
  }
  async function setAuto(course,binding,auto) {
    if (!binding) { choices.set(course.id,auto?null:false); paint(); return; }
    if (!auto && current?.course.id === course.id && !current.explicit) current.controller.abort();
    await storage.update(binding.key,record=>record?.token === binding.token ? {...record,auto:auto?null:false} : null);
    await load(); paint();settingsChanged();if (auto) refresh(courses);
  }
  async function setGlobalAuto(root,auto) {
    if (!auto && current && !current.explicit) current.controller.abort();
    let changed = false;
    await storage.updateRoot(root.revision,latest=>{
      if (latest?.token !== root.token) return null;
      changed = true;return {...latest,auto};
    });
    if (!changed) throw new Error('总目录设置已变化，请刷新后重试。');
    await load();paint();settingsChanged();if (auto) refresh(courses);
  }
  async function setIntervalMinutes(root,minutes) {
    if (!downloadIntervals.includes(minutes)) throw new Error('请选择有效的检查间隔。');
    let changed = false;
    await storage.updateRoot(root.revision,latest=>{
      if (latest?.token !== root.token) return null;
      changed = true;return {...latest,checkIntervalMinutes:minutes};
    });
    if (!changed) throw new Error('总目录设置已变化，请刷新后重试。');
    await load();paint();settingsChanged();
  }
  async function choose() {
    if (picking || context.signal.aborted) return;
    if (typeof window.showDirectoryPicker !== 'function') {
      context.ui.toast('请在 Edge 或 Chrome 中打开工作台，再选择保存文件夹。'); return;
    }
    picking = true;
    const owner = revision;
    try {
      const directory = await window.showDirectoryPicker({id:'campusmate-course-files',mode:'readwrite',startIn:'downloads'});
      context.signal.throwIfAborted();
      current?.controller.abort();
      await withDownloadLock(context.signal,async()=>{
        await snapshot();
        if (owner && owner !== revision) throw new Error('账号已变化，请重新选择资料总目录。');
        const previous = await storage.getRoot(revision);
        const same = previous && await previous.directory.isSameEntry(directory);
        context.signal.throwIfAborted();
        await storage.putRoot({...previous,revision,directory,token:same?previous.token:crypto.randomUUID(),
          ...(!same || previous.lastAutoState==='permission'?{lastAutoCheckAt:0,lastAutoState:'',lastAutoMessage:''}:{})});
      });
      await load();rootMessage = '已记住总目录，正在按学期整理所有课程文件夹…';rootPermission = false;paint();settingsChanged();
      void refresh(courses);
    } finally { picking = false; paint(); }
  }
  function permissions(binding) {
    return [...new Set([binding.parentDirectory || binding.directory,...Object.values(binding.files || {}).map(record=>record.directory).filter(Boolean)])];
  }
  async function checkAll(root) {
    const handles = [root.directory,...[...bindings.values()].filter(binding=>binding.revision === revision).flatMap(binding=>
      binding.rootToken === root.token ? Object.values(binding.files || {}).map(record=>record.directory).filter(Boolean) : permissions(binding))];
    const allowed = await Promise.all([...new Set(handles)].map(handle=>handle.requestPermission({mode:'readwrite'})));
    context.signal.throwIfAborted();
    if (allowed.some(value=>value !== 'granted')) { rootPermission = true;rootMessage = '需要允许访问总目录及已有资料的保存位置。';paint();return; }
    if (root.lastAutoState === 'permission') {
      await storage.updateRoot(root.revision,latest=>latest?.token === root.token && latest.lastAutoState === 'permission'
        ? {...latest,lastAutoCheckAt:0,lastAutoState:'ready',lastAutoMessage:'已恢复目录访问。'} : null);
      await load();settingsChanged();
    }
    rootPermission = false;for (const course of courses) manual.add(course.id);return refresh(courses);
  }
  async function check(course,binding) {
    const allowed = await Promise.all(permissions(binding).map(handle=>handle.requestPermission({mode:'readwrite'})));
    if (allowed.some(value=>value !== 'granted')) {
      status(course,{message:'需要允许访问此文件夹，才能继续保存。',permission:true}); return;
    }
    context.signal.throwIfAborted(); manual.add(course.id); refresh(courses);
  }
  async function run(course,explicit,report) {
    const key = downloadKey(revision,course.id);
    async function work() {
      let binding = await storage.get(key);
      if (!binding || (!explicit && !autoEnabled(await storage.getRoot(binding.revision),binding)) || context.signal.aborted) return;
      bindings.set(key,binding);
      if (await (binding.parentDirectory || binding.directory).queryPermission({mode:'readwrite'}) !== 'granted') {
        status(course,{message:'文件夹已记住。点击“允许访问并继续”恢复下载。',permission:true}); return;
      }
      // A queued tab must use the current snapshot and the manifest saved by its predecessor.
      const source = await snapshot();
      if (source.account_revision !== binding.revision || source.status === 'syncing') return;
      binding = await courseFolder(binding,course,storage,context.signal,await storage.getRoot(binding.revision));
      bindings.set(key,binding);
      const controller = new AbortController();
      const signal = AbortSignal.any([controller.signal,context.signal]);
      current = {course,controller,explicit};
      try {
        const result = await downloadFiles({items:courseFiles(source,course),directory:binding.directory,legacyDirectory:binding.legacyDirectory,
          revision:binding.revision,files:binding.files,signal,request,
          checkActive:async()=>{
            if (!explicit) {
              const [latest,root] = await Promise.all([storage.get(key),storage.getRoot(binding.revision)]);
              if (latest?.token !== binding.token || !autoEnabled(root,latest)) controller.abort();
            }
            signal.throwIfAborted();
          },
          onRecord:async(id,record)=>{
            // Merge only the manifest so pause/forget/change in another tab wins.
            let recorded = false;
            await storage.update(key,latest=>{
              if (latest?.token !== binding.token) return null;
              recorded = true; return {...latest,files:{...latest.files,[id]:record}};
            });
            if (!recorded) throw new Error('文件夹设置已变化，已保存文件保留，请重新检查。');
          },
          onProgress:value=>status(course,{message:value.current?`正在检查 ${value.done+1}/${value.total}：${value.current}`:'正在整理结果…',done:value.done,total:value.total}),
        });
        const remaining = result.failed.length + result.remaining.length;
        status(course,{message:`${result.cancelled?'本次已停止。':''}新增或更新 ${result.saved.length} 个，跳过已有 ${result.skipped.length} 个${result.preserved.length?`，保留本地文件 ${result.preserved.length} 个（已暂停这些资料的自动更新）`:''}${remaining?`，${remaining} 个未完成，可点击“立即检查”重试`:'，已检查完成'}。`,
          errors:[...result.failed.map(({item,message})=>item.title+'：'+message),...result.preserved.map(({name,message})=>name+'：'+message)]});
        const notice = downloadNotice(course,binding.directory,result);
        if (notice) {
          report({...notice,revision:binding.revision});
          await storage.update(key,latest=>latest?.token === binding.token ? {...latest,lastDownload:notice} : null);
        }
        await removeEmptyCourseFolders(binding);
      } finally { current = null; await load(); paint(); }
    }
    status(course,{message:'正在等待下载队列…'});
    await withDownloadLock(context.signal,()=>navigator.locks.request('campusmate-download:'+key,{signal:context.signal},work));
  }
  async function drain() {
    if (draining || context.signal.aborted) return;
    draining = true;
    const notices = [];
    try {
      while (pending && !context.signal.aborted) {
        pending = false; await load();
        if (!bindings.size && !roots.size) { paint(); continue; }
        const source = await snapshot(); paint();
        await prepareFolders();
        if (rootPermission) continue;
        if (source.status === 'syncing') continue;
        for (const course of courses) {
          const explicit = manual.delete(course.id), binding = bindingFor(course);
          if (binding && (autoEnabled(rootFor(),binding) || explicit)) {
            try { await run(course,explicit,notice=>notices.push(notice)); }
            catch(error) { if (!context.signal.aborted) status(course,{message:error.message}); }
          }
          if (context.signal.aborted) break;
        }
      }
    } catch(error) { fail(error); }
    finally {
      draining = false;
      const message = downloadNoticeMessage(notices.filter(notice=>notice.revision === revision));
      if (!context.signal.aborted && message) context.ui.toast(message);
    }
  }
  async function prepareFolders() {
    await withDownloadLock(context.signal,async()=>{
      const root = await savedRoot(revision,storage,context.signal);
      if (!root) {
        rootMessage = [...bindings.values()].some(binding=>binding.revision === revision)?'已有多个保存位置，请选择统一资料总目录。':'';return;
      }
      roots.set(revision,root);
      if (await root.directory.queryPermission({mode:'readwrite'}) !== 'granted') {
        rootPermission = true;rootMessage = '总目录已记住，允许访问后即可继续。';return;
      }
      rootPermission = false;
      for (const course of [...courses]) {
        context.signal.throwIfAborted();
        const key = downloadKey(revision,course.id);
        let binding = await storage.get(key);
        if (!binding) {
          binding = {key,revision,courseId:course.id,directory:root.directory,auto:choices.get(course.id) ?? null,token:crypto.randomUUID(),files:{}};
          await storage.put(binding);choices.delete(course.id);
        }
        binding = await courseFolder(binding,course,storage,context.signal,root);
        bindings.set(key,binding);
      }
      rootMessage = `总目录已记住，${courses.length} 门课程按学期分类；新增课程会自动建立文件夹。`;
    });
    paint();
  }
  function refresh(nextCourses) {
    courses = nextCourses;pending = true;
    return drainingJob || (drainingJob=drain().finally(()=>{drainingJob=undefined;}));
  }
  async function repaint() {await load();paint();}
  return {refresh,dispose,repaint,detach() {views.clear();rootHost=undefined;},attachRoot(host) {rootHost = host;paint();},attach(host,course,count) { views.set(course.id,{host,course,count}); paint(); }};
}
