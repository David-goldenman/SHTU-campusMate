import {sourcePanel, records, link, time, submissionLabel} from '/assets/campus.js';
import {decorateCourse} from './appearance.js';

const platforms={timetable:'教务课表',blackboard:'Blackboard',gradescope:'Gradescope',piazza:'Piazza',elrc:'录播',ecourse:'E 云课堂'};
const kinds={assignments:'作业',materials:'资料',announcements:'公告',posts:'讨论',lessons:'录播',timetable:'上课安排',grades:'成绩'};

export async function mount(container,context) {
  const e=context.ui.escape, removeStyle=context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  container.classList.add('course-hub');
  let selected, current=true, query='';
  const dispose=await sourcePanel(container,context,async(body,snapshot,context,refresh)=>{
    const groups=(await context.api('/groups')).groups, courses=snapshot.data.courses;
    body.innerHTML=`<div class="campus-toolbar"><label class="checkbox-label"><input data-current type="checkbox" ${current?'checked':''}>本学期</label><input data-search type="search" placeholder="搜索课程名称或代码" aria-label="搜索课程" value="${e(query)}"><span class="field-hint">${e(snapshot.data.metadata.current_semester)}</span><button type="button" class="button button-secondary" data-group>关联课程</button></div><div class="course-columns"><nav data-courses aria-label="课程列表"></nav><section class="course-detail" data-detail aria-label="课程内容"></section></div>`;
    const values=()=>courses.filter(item=>(!current||item.current)&&(item.title+' '+item.code).toLowerCase().includes(query.toLowerCase()));
    function draw(){
      const list=values();if(!list.some(item=>item.id===selected))selected=list[0]?.id;
      body.querySelector('[data-courses]').innerHTML=list.map(item=>`<button type="button" class="course-choice ${selected===item.id?'selected':''}" data-course="${e(item.id)}" aria-pressed="${selected===item.id}"><span>${e(item.code || '课程')}</span><strong>${e(item.title)}</strong></button>`).join('')||'<p class="field-hint">当前范围没有课程。可查看其他学期，或连接账号后同步。</p>';
      body.querySelectorAll('[data-course]').forEach(button=>{decorateCourse(button,list.find(item=>item.id===button.dataset.course));button.onclick=context.ui.safeAction(button,async()=>{selected=button.dataset.course;draw();await detail();});});
    }
    async function detail(){
      const host=body.querySelector('[data-detail]');
      if(!selected){host.innerHTML='<p class="field-hint">同步后，课程资料会按课程汇总在这里。</p>';return;}
      const identity=selected;host.innerHTML='<p role="status">正在读取课程…</p>';
      const data=await context.api('/course?course_id='+encodeURIComponent(identity));
      if(context.signal.aborted||identity!==selected)return;
      data.grades=data.course.sources.flatMap(source=>(source.grades||[]).map(item=>({...item,source:source.source})));
      const available=Object.keys(kinds).filter(kind=>data[kind].length);
      host.innerHTML=`<header><p class="field-hint">${e(data.course.code)} · ${e(data.course.term)}</p><h3>${e(data.course.title)}</h3><div class="course-platforms">${data.course.sources.map(source=>link(source.url,platforms[source.source]||source.source,e)).join('')}</div></header><div class="course-content-tabs" role="tablist" aria-label="课程内容">${available.map((kind,index)=>`<button type="button" role="tab" id="course-tab-${kind}" aria-controls="course-content" aria-selected="${index===0}" tabindex="${index===0?'0':'-1'}" data-kind="${kind}">${kinds[kind]} <span>${data[kind].length}</span></button>`).join('')}</div><div id="course-content" role="tabpanel" data-content></div>`;
      decorateCourse(host.querySelector('header'),data.course);
      function content(kind){
        host.querySelectorAll('[data-kind]').forEach(button=>{button.setAttribute('aria-selected',String(button.dataset.kind===kind));button.tabIndex=button.dataset.kind===kind?0:-1;});
        const panel=host.querySelector('[data-content]');panel.setAttribute('aria-labelledby','course-tab-'+kind);
        if(kind==='timetable')panel.innerHTML=data.timetable.map(item=>`<article class="campus-item"><h4>周${'一二三四五六日'[item.weekday-1]} · 第 ${item.period_start}–${item.period_end} 节</h4><p>${e(item.location || '地点待定')}</p><p class="field-hint">第 ${e(item.weeks.join('、'))} 周</p></article>`).join('');
        else if(kind==='assignments')panel.innerHTML=data.assignments.map(item=>`<article class="campus-item"><h4>${link(item.url,item.title,e)}</h4><p class="field-hint" title="${e(item.submission_reason || '')}">${e(platforms[item.source]||item.source)} · ${item.due_at?'截止 '+e(time(item.due_at)):'截止时间未提供'} · ${e(submissionLabel(item))}${item.score!=null?' · 得分 '+e(item.score)+(item.max_score!=null?' / '+e(item.max_score):''):''}</p></article>`).join('');
        else if(kind==='grades')panel.innerHTML=data.grades.map(item=>`<article class="campus-item"><h4>${e(item.title)}</h4><p>${e(item.score??'成绩未公布')}${item.max_score!=null?' / '+e(item.max_score):''}</p><p class="field-hint">${e(platforms[item.source]||item.source)}</p></article>`).join('');
        else panel.innerHTML=records(data[kind],e);
      }
      host.querySelectorAll('[data-kind]').forEach((button,index)=>{button.onclick=()=>content(button.dataset.kind);button.onkeydown=event=>{const offset={ArrowLeft:-1,ArrowRight:1}[event.key];if(offset){event.preventDefault();const next=host.querySelectorAll('[data-kind]')[(index+offset+available.length)%available.length];next.click();next.focus();}};});
      if(available.length)content(available[0]);else host.querySelector('[data-content]').innerHTML='<p class="field-hint">已关联课程入口，平台暂未提供资料。</p>';
    }
    body.querySelector('[data-current]').onchange=async event=>{current=event.currentTarget.checked;draw();try{await detail();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
    body.querySelector('[data-search]').oninput=async event=>{query=event.currentTarget.value;draw();try{await detail();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
    body.querySelector('[data-group]').onclick=()=>{
      const form=document.createElement('form');form.className='campus-form';
      form.innerHTML=`<p class="field-hint">同一课程的各平台入口可合为一组。课程代码和学期一致时会自动关联。</p><label>课程名称<input name="title" maxlength="120" required></label><fieldset class="course-group-options"><legend>选择至少两个课程入口</legend>${courses.flatMap(item=>item.sources).map(source=>`<label class="checkbox-label"><input type="checkbox" name="member" value="${e(source.id)}"><span>${e(source.title)}<small>${e(platforms[source.source]||source.source)} · ${e(source.code)} · ${e(source.term)}</small></span></label>`).join('')}</fieldset><div class="form-actions"><button class="button button-primary">保存关联</button><button class="text-button" data-reset type="button">恢复自动关联</button></div>`;
      const dialog=context.ui.dialog('关联课程',form);
      form.onsubmit=async event=>{event.preventDefault();const course_ids=[...form.querySelectorAll('[name=member]:checked')].map(node=>node.value);if(course_ids.length<2){context.ui.toast('请选择至少两个入口。');return;}try{await context.api('/groups',{method:'PUT',body:{groups:[...groups.filter(group=>!group.course_ids.some(id=>course_ids.includes(id))),{id:crypto.randomUUID(),title:form.elements.title.value,course_ids}]}});dialog.close();await refresh();}catch(error){if(!context.signal.aborted)context.ui.toast(error.message);}};
      const reset=form.querySelector('[data-reset]');reset.onclick=context.ui.safeAction(reset,async()=>{if(await context.ui.confirmDialog('恢复自动关联','移除当前手动课程分组，重新按课程代码和学期关联。')){await context.api('/groups',{method:'PUT',body:{groups:[]}});dialog.close();await refresh();}});
      context.signal.addEventListener('abort',()=>dialog.close(),{once:true});
    };
    draw();await detail();
  });
  return()=>{dispose?.();removeStyle();};
}
