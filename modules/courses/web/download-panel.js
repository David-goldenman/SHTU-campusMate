import {courseFiles, downloadFiles, readResponse} from './downloads.js';
import {downloadKey, folderStore} from './download-store.js';

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
  const bindings = new Map(), states = new Map(), views = new Map(), manual = new Set(), choices = new Map();
  let revision, courses = [], pending = false, draining = false, current, picking = false;
  const dispose = () => { current?.controller.abort(); views.clear(); pending = false; manual.clear(); };
  context.signal.addEventListener('abort',dispose,{once:true});
  const bindingFor = course => bindings.get(downloadKey(revision,course.id));
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
    if (revision !== value.account_revision) { states.clear(); revision = value.account_revision; }
    return value;
  }
  async function load() {
    const records = await storage.all();
    bindings.clear(); for (const record of records) bindings.set(record.key,record);
  }
  function paint() {
    if (context.signal.aborted) return;
    const e = context.ui.escape;
    for (const [id,view] of views) {
      const {host,course,count} = view;
      if (!host.isConnected) { views.delete(id); continue; }
      const binding = bindingFor(course), state = states.get(id) || {}, running = current?.course.id === id;
      const auto = binding?.auto ?? choices.get(id) ?? false;
      host.innerHTML = `<div><strong>Piazza 文件${count?' · '+count+' 份':''}</strong><p>${binding?`保存到 <strong>${e(binding.directory.name)}</strong>`:'选择并记住保存文件夹，自行决定是否自动拉取。'}</p><label class="course-download-auto"><span class="settings-switch"><input type="checkbox" role="switch" aria-label="文件自动拉取" data-auto ${auto?'checked':''}><span aria-hidden="true"></span></span><span>文件自动拉取 · ${auto?'已开启':'已关闭'}</span></label><p class="field-hint">${auto?'开启后，进入课程中心或点击页顶“同步”会自动补齐文件。':'关闭时，刷新或同步不会下载文件；可点击“立即检查”手动下载。'}已有文件跳过，本地修改保留。</p><p class="course-download-status" role="status" aria-live="polite">${e(state.message || '')}</p>${running?`<progress max="${Math.max(state.total||1,1)}" value="${state.done||0}" aria-label="课程文件下载进度"></progress>`:''}${state.errors?.length?`<ul>${state.errors.map(message=>`<li>${e(message)}</li>`).join('')}</ul>`:''}</div><div class="course-download-actions"><button type="button" class="button button-secondary" data-choose ${running||picking?'disabled':''}>${binding?'更换文件夹':'选择并记住文件夹'}</button>${binding?`<button type="button" class="button button-secondary" data-check ${running?'disabled':''}>${state.permission?'允许访问并继续':'立即检查'}</button><button type="button" class="text-button" data-forget ${running?'disabled':''}>忘记文件夹</button>`:''}${running?'<button type="button" class="text-button" data-stop>停止本次</button>':''}</div>`;
      const recent = binding?.lastDownload;
      if (recent?.count) {
        const at = new Date(recent.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'});
        host.firstElementChild.insertAdjacentHTML('beforeend',`<details class="course-download-recent"><summary>最近拉取 ${recent.count} 份文件 · ${e(at)}</summary><ul>${recent.names.map(name=>`<li>${e(name)}</li>`).join('')}</ul>${recent.count>recent.names.length?`<p class="field-hint">另有 ${recent.count-recent.names.length} 份文件已保存。</p>`:''}</details>`);
      }
      // Keep permission requests directly in click handlers to retain user activation.
      host.querySelector('[data-choose]').onclick = () => { void choose(course).catch(fail); };
      host.querySelector('[data-auto]').onchange = event => {
        const enabled = event.currentTarget.checked;
        void setAuto(course,binding,enabled).catch(error=>{paint();fail(error);});
      };
      if (binding) {
        host.querySelector('[data-check]').onclick = () => { void check(course,binding).catch(fail); };
        host.querySelector('[data-forget]').onclick = action(async()=>{
          await storage.remove(binding.key); bindings.delete(binding.key); states.delete(id); choices.delete(id); paint();
        });
      }
      if (running) host.querySelector('[data-stop]').onclick = () => current?.controller.abort();
    }
  }
  async function setAuto(course,binding,auto) {
    if (!binding) { choices.set(course.id,auto); paint(); return; }
    if (!auto && current?.course.id === course.id) current.controller.abort();
    if (!auto) manual.delete(course.id);
    await storage.update(binding.key,record=>record && {...record,auto});
    await load(); paint(); if (auto) refresh(courses);
  }
  async function choose(course) {
    if (picking || context.signal.aborted) return;
    if (typeof window.showDirectoryPicker !== 'function') {
      context.ui.toast('请在 Edge 或 Chrome 中打开工作台，再选择保存文件夹。'); return;
    }
    picking = true;
    try {
      const directory = await window.showDirectoryPicker({id:'campusmate-course-files',mode:'readwrite',startIn:'downloads'});
      context.signal.throwIfAborted();
      await snapshot(); await load();
      const key = downloadKey(revision,course.id), previous = bindings.get(key);
      const same = previous && await previous.directory.isSameEntry(directory);
      const auto = previous?.auto ?? choices.get(course.id) ?? false;
      const record = {key,revision,courseId:course.id,directory,auto,token:same?previous.token:crypto.randomUUID(),files:same?previous.files:{},lastDownload:same?previous.lastDownload:undefined};
      context.signal.throwIfAborted(); await storage.put(record); bindings.set(key,record);
      choices.delete(course.id);
      status(course,{message:auto?'已记住文件夹，正在检查已有文件…':'已记住文件夹。自动拉取已关闭，可点击“立即检查”手动下载。'});
      if (auto) refresh(courses);
    } finally { picking = false; paint(); }
  }
  async function check(course,binding) {
    if (await binding.directory.requestPermission({mode:'readwrite'}) !== 'granted') {
      status(course,{message:'需要允许访问此文件夹，才能继续保存。',permission:true}); return;
    }
    context.signal.throwIfAborted(); manual.add(course.id); refresh(courses);
  }
  async function run(course,source,explicit,report) {
    const key = downloadKey(revision,course.id);
    async function work() {
      const binding = await storage.get(key);
      if (!binding || (!binding.auto && !explicit) || context.signal.aborted) return;
      bindings.set(key,binding);
      if (await binding.directory.queryPermission({mode:'readwrite'}) !== 'granted') {
        status(course,{message:'文件夹已记住。点击“允许访问并继续”恢复下载。',permission:true}); return;
      }
      const controller = new AbortController();
      const signal = AbortSignal.any([controller.signal,context.signal]);
      current = {course,controller};
      try {
        const result = await downloadFiles({items:courseFiles(source,course),directory:binding.directory,
          revision:binding.revision,files:binding.files,signal,request,
          onRecord:async(id,record)=>{
            // Merge only the manifest so pause/forget/change in another tab wins.
            await storage.update(key,latest=>latest?.token === binding.token ? {...latest,files:{...latest.files,[id]:record}} : null);
          },
          onProgress:value=>status(course,{message:value.current?`正在检查 ${value.done+1}/${value.total}：${value.current}`:'正在整理结果…',done:value.done,total:value.total}),
        });
        const remaining = result.failed.length + result.remaining.length;
        status(course,{message:`${result.cancelled?'本次已停止。':''}新增或更新 ${result.saved.length} 个，跳过已有 ${result.skipped.length} 个${remaining?`，${remaining} 个未完成，可点击“立即检查”重试`:'，已检查完成'}。`,
          errors:result.failed.map(({item,message})=>item.title+'：'+message)});
        const notice = downloadNotice(course,binding.directory,result);
        if (notice) {
          report({...notice,revision:binding.revision});
          await storage.update(key,latest=>latest?.token === binding.token ? {...latest,lastDownload:notice} : null);
        }
      } finally { current = null; await load(); paint(); }
    }
    if (navigator.locks) {
      await navigator.locks.request('campusmate-download:'+key,{ifAvailable:true},async lock=>{
        if (lock) await work(); else status(course,{message:'另一个窗口正在检查此课程，完成后可再次检查。'});
      });
    } else await work();
  }
  async function drain() {
    if (draining || context.signal.aborted) return;
    draining = true;
    const notices = [];
    try {
      while (pending && !context.signal.aborted) {
        pending = false; await load();
        if (!bindings.size) { paint(); continue; }
        const source = await snapshot(); paint();
        if (source.status === 'syncing') continue;
        for (const course of courses) {
          const explicit = manual.delete(course.id), binding = bindingFor(course);
          if (binding && (binding.auto || explicit)) {
            try { await run(course,source,explicit,notice=>notices.push(notice)); }
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
  function refresh(nextCourses) { courses = nextCourses; pending = true; return drain(); }
  return {refresh,dispose,attach(host,course,count) { views.set(course.id,{host,course,count}); paint(); }};
}
