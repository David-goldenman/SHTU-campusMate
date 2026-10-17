import {sourcePanel, records, link, time} from '/assets/campus.js';
import {courseSummaries, termLabel} from './summary.js';

const platforms = {timetable:'教务课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'教学社区'};
const kinds = {assignments:'作业',materials:'资料',lessons:'录播',announcements:'公告',posts:'讨论',timetable:'上课安排',grades:'成绩'};
const filters = {all:'全部',available:'有录播',empty:'暂无录播',unknown:'待确认'};
const playIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/></svg>';

export async function mount(container, context) {
  const e = context.ui.escape;
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('course-hub');
  let selected, current = true, query = '', recordingFilter = 'all', activeKind;
  const dispose = await sourcePanel(container,context,async (body,snapshot,context,refresh) => {
    const entries = courseSummaries(snapshot.data), courses = snapshot.data.courses;
    body.innerHTML = `<div class="course-toolbar"><div><span class="course-eyebrow">我的课程</span><p>${e(termLabel(snapshot.data.metadata.current_semester))}</p></div><div class="course-toolbar-actions"><label class="checkbox-label"><input data-current type="checkbox" ${current?'checked':''}>仅本学期</label><button type="button" class="button button-secondary" data-group>关联课程</button></div></div><div class="course-columns"><aside class="course-browser" aria-label="查找课程"><label class="course-search">搜索课程<input data-search type="search" placeholder="课程名称或代码" value="${e(query)}"></label><div class="course-filters" role="group" aria-label="按录播筛选" data-filters></div><p class="course-list-count" data-list-count role="status"></p><nav data-courses aria-label="课程列表"></nav></aside><section class="course-detail" data-detail aria-label="课程内容"></section></div>`;
    const scoped = () => entries.filter(({course}) => (!current || course.current) && `${course.title} ${course.code}`.toLowerCase().includes(query.trim().toLowerCase()));
    function draw() {
      const scope = scoped(), counts = {all:scope.length,available:0,empty:0,unknown:0};
      scope.forEach(item => counts[item.recording.state]++);
      const filterHost = body.querySelector('[data-filters]');
      filterHost.innerHTML = Object.entries(filters).filter(([key]) => key !== 'unknown' || counts.unknown || recordingFilter === key).map(([key,label]) => `<button type="button" data-filter="${key}" aria-pressed="${recordingFilter===key}">${label}<span>${counts[key]}</span></button>`).join('');
      filterHost.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { recordingFilter = button.dataset.filter; draw(); detail(); body.querySelector(`[data-filter="${recordingFilter}"]`)?.focus(); });
      const list = scope.filter(item => recordingFilter === 'all' || item.recording.state === recordingFilter);
      if (!list.some(item => item.course.id === selected)) { selected = list[0]?.course.id; activeKind = undefined; }
      body.querySelector('[data-list-count]').textContent = `显示 ${list.length} 门课程`;
      body.querySelector('[data-courses]').innerHTML = list.map(({course,recording,contents,pending}) => `<button type="button" class="course-choice ${selected===course.id?'selected':''}" data-course="${e(course.id)}" aria-pressed="${selected===course.id}"><span class="course-choice-top"><span class="course-code">${e(course.code||'课程')}</span><span class="course-recording-badge" data-state="${recording.state}">${e(recording.label)}</span></span><strong>${e(course.title)}</strong><span class="course-choice-meta">${pending?`<span class="course-pending">${pending} 项待办</span>`:''}<span>${contents.materials.length} 份资料</span>${!current?`<span>${e(termLabel(course.term))}</span>`:''}</span><small>${e([...new Set(course.sources.map(source => platforms[source.source]||source.source))].join(' · '))}</small></button>`).join('') || '<div class="course-list-empty"><strong>没有符合条件的课程</strong><p>试试其他录播筛选、关键词或学期。</p></div>';
      body.querySelectorAll('[data-course]').forEach(button => button.onclick = () => {
        selected = button.dataset.course; activeKind = undefined; draw(); detail();
        body.querySelector(`[data-course="${CSS.escape(selected)}"]`)?.focus({preventScroll:true});
        if (matchMedia('(max-width:850px)').matches) body.querySelector('[data-detail]').scrollIntoView({block:'start',behavior:'instant'});
      });
    }
    function detail() {
      const host = body.querySelector('[data-detail]'), entry = entries.find(item => item.course.id === selected);
      if (!entry) { host.innerHTML = '<div class="course-content-empty"><h3>选择课程，开始学习</h3><p>调整课程筛选，查看资料、作业和录播。</p></div>'; return; }
      const {course,contents:data,recording,pending} = entry;
      const available = Object.keys(kinds).filter(kind => kind === 'lessons' || data[kind].length);
      if (!available.includes(activeKind)) activeKind = pending?'assignments':data.materials.length?'materials':recording.count?'lessons':available.find(kind=>kind!=='lessons')||'lessons';
      host.innerHTML = `<header class="course-detail-header"><p class="course-eyebrow">${e(course.code||'课程')}<span>·</span>${e(termLabel(course.term))}</p><h3>${e(course.title)}</h3><div class="course-platforms" aria-label="课程原站入口">${course.sources.filter(source=>source.url).map(source=>link(source.url,platforms[source.source]||source.source,e)).join('')}</div></header><div class="course-recording-summary" data-state="${recording.state}"><span class="course-recording-icon">${playIcon}</span><div><strong>${e(recording.label)}</strong><p>${e(recording.hint)}</p></div>${recording.count?'<button type="button" class="button button-secondary" data-view-recordings>查看录播 <span aria-hidden="true">→</span></button>':''}</div><div class="course-content-tabs" role="tablist" aria-label="课程内容">${available.map(kind=>`<button type="button" role="tab" id="course-tab-${kind}" aria-controls="course-content" aria-selected="${activeKind===kind}" tabindex="${activeKind===kind?'0':'-1'}" data-kind="${kind}">${kinds[kind]}<span>${data[kind].length}</span></button>`).join('')}</div><div id="course-content" role="tabpanel" tabindex="0" data-course-content></div>`;
      function content(kind) {
        activeKind = kind;
        host.querySelectorAll('[data-kind]').forEach(button=>{button.setAttribute('aria-selected',String(button.dataset.kind===kind));button.tabIndex=button.dataset.kind===kind?0:-1;});
        const panel = host.querySelector('[data-course-content]'); panel.setAttribute('aria-labelledby','course-tab-'+kind);
        if (kind === 'lessons') {
          panel.innerHTML = recording.count?`<div class="course-section-label">${recording.count} 条录播<span>在教学社区打开观看</span></div><div class="course-recording-list">${data.lessons.map((item,index)=>`<article class="course-recording-row"><span class="course-recording-number">${String(index+1).padStart(2,'0')}</span><div><h4>${link(item.url,item.title,e)}</h4><p>${e(item.body_text?'含课堂转写':'课堂录播')}${item.summary_text?' · 含内容摘要':''}</p></div><span class="course-recording-open">${link(item.url,'打开录播 ↗',e)}</span></article>`).join('')}</div>`:`<div class="course-content-empty"><span class="course-empty-icon">${playIcon}</span><h4>${e(recording.label)}</h4><p>${e(recording.hint)}</p></div>`;
        } else if (kind === 'timetable') panel.innerHTML = data.timetable.map(item=>`<article class="campus-item"><h4>周${'一二三四五六日'[item.weekday-1]} · 第 ${item.period_start}–${item.period_end} 节</h4><p>${e(item.location||'地点待定')}</p><p class="field-hint">第 ${e(item.weeks.join('、'))} 周</p></article>`).join('');
        else if (kind === 'assignments') panel.innerHTML = data.assignments.map(item=>`<article class="campus-item course-assignment"><h4>${link(item.url,item.title,e)}</h4><p class="course-assignment-due">${item.due_at?'截止 '+e(time(item.due_at)):'截止时间未提供'}</p><p class="field-hint">${e(platforms[item.source]||item.source)} · ${item.submitted===true?'已提交':item.submitted===false?'未提交':'提交状态未提供'}${item.score!=null?' · 得分 '+e(item.score)+(item.max_score!=null?' / '+e(item.max_score):''):''}</p></article>`).join('');
        else if (kind === 'grades') panel.innerHTML = data.grades.map(item=>`<article class="campus-item"><h4>${e(item.title)}</h4><p>${e(item.score??'成绩未公布')}${item.max_score!=null?' / '+e(item.max_score):''}</p><p class="field-hint">${e(platforms[item.source]||item.source)}</p></article>`).join('');
        else panel.innerHTML = records(data[kind],e);
      }
      host.querySelectorAll('[data-kind]').forEach((button,index)=>{
        button.onclick = ()=>content(button.dataset.kind);
        button.onkeydown = event=>{
          const offset = {ArrowLeft:-1,ArrowRight:1}[event.key];
          if(offset || ['Home','End'].includes(event.key)){
            event.preventDefault();
            const position = event.key==='Home'?0:event.key==='End'?available.length-1:(index+offset+available.length)%available.length;
            const next = host.querySelectorAll('[data-kind]')[position]; next.click(); next.focus();
          }
        };
      });
      const watch = host.querySelector('[data-view-recordings]');
      if(watch) watch.onclick=()=>{content('lessons');host.querySelector('[data-kind="lessons"]').focus();};
      content(activeKind);
    }
    body.querySelector('[data-current]').onchange=event=>{current=event.currentTarget.checked;draw();detail();};
    body.querySelector('[data-search]').oninput=event=>{query=event.currentTarget.value;draw();detail();};
    const groupButton=body.querySelector('[data-group]');
    groupButton.onclick=context.ui.safeAction(groupButton,async()=>{
      const {groups}=await context.api('/groups'); if(context.signal.aborted)return;
      const form=document.createElement('form');form.className='campus-form';
      form.innerHTML=`<p class="field-hint">同一课程的各平台入口可合为一组。课程代码和学期一致时会自动关联。</p><label>课程名称<input name="title" maxlength="120" required></label><fieldset class="course-group-options"><legend>选择至少两个课程入口</legend>${courses.flatMap(item=>item.sources).map(source=>`<label class="checkbox-label"><input type="checkbox" name="member" value="${e(source.id)}"><span>${e(source.title)}<small>${e(platforms[source.source]||source.source)} · ${e(source.code)} · ${e(source.term)}</small></span></label>`).join('')}</fieldset><div class="form-actions"><button class="button button-primary">保存关联</button><button class="text-button" data-reset type="button">恢复自动关联</button></div>`;
      const dialog=context.ui.dialog('关联课程',form);
      form.onsubmit=async event=>{
        event.preventDefault();const course_ids=[...form.querySelectorAll('[name=member]:checked')].map(node=>node.value);
        if(course_ids.length<2){context.ui.toast('请选择至少两个入口。');return;}
        try{await context.api('/groups',{method:'PUT',body:{groups:[...groups.filter(group=>!group.course_ids.some(id=>course_ids.includes(id))),{id:crypto.randomUUID(),title:form.elements.title.value,course_ids}]}});dialog.close();await refresh();}
        catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}
      };
      const reset=form.querySelector('[data-reset]');
      reset.onclick=context.ui.safeAction(reset,async()=>{if(await context.ui.confirmDialog('恢复自动关联','移除当前手动课程分组，重新按课程代码和学期关联。')){await context.api('/groups',{method:'PUT',body:{groups:[]}});dialog.close();await refresh();}});
      context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
    });
    draw();detail();
  });
  return()=>{dispose?.();removeStyle();};
}
