import {sourcePanel, records, link} from '/assets/campus.js';

export function mount(container,context) {
  const e = context.ui.escape;
  return sourcePanel(container,context,async (body,snapshot,context,refresh) => {
    const groups = (await context.api('/groups')).groups;
    const courses = snapshot.data.courses;
    body.innerHTML = '<div class="campus-toolbar"><label class="checkbox-label"><input data-current type="checkbox" checked>本学期</label><input data-search placeholder="搜索课程名称或代码" aria-label="搜索课程"><span>' + e(snapshot.data.metadata.current_semester) + '</span></div><details><summary>手动关联课程</summary><p class="field-hint">代码和学期一致的课程自动关联；其余可选择两个以上平台课程组成课程组。</p><form data-group class="campus-form"><label>课程组名称<input name="title" required maxlength="120"></label><label>平台课程（按住 Ctrl 或 Command 多选）<select name="members" multiple size="6">' + courses.flatMap(item => item.sources).map(item => `<option value="${e(item.id)}">${e(item.source + ' · ' + item.code + ' · ' + item.term + ' · ' + item.title)}</option>`).join('') + '</select></label><button class="button button-secondary">保存关联</button></form><button class="text-button" data-reset type="button">恢复自动关联</button></details><div class="campus-list" data-courses></div>';
    const draw = () => {
      const current = body.querySelector('[data-current]').checked;
      const search = body.querySelector('[data-search]').value.toLowerCase();
      const values = courses.filter(item => (!current || item.current) && (item.title + ' ' + item.code).toLowerCase().includes(search));
      body.querySelector('[data-courses]').innerHTML = values.map(item => `<details class="campus-item" data-course="${e(item.id)}"><summary><strong>${e(item.code)} ${e(item.title)}</strong> · ${e(item.term)} · ${e(item.sources.map(value => value.source).join(' / '))}</summary><div data-body></div></details>`).join('') || '<p class="field-hint">该范围没有课程。可取消本学期筛选，或连接账号后同步。</p>';
      body.querySelectorAll('[data-course]').forEach(details => details.ontoggle = async () => {
        if (!details.open || details.dataset.loaded) return;
        details.dataset.loaded = 'yes';
        try {
          const data = await context.api('/course?course_id=' + encodeURIComponent(details.dataset.course));
          details.querySelector('[data-body]').innerHTML = data.course.sources.map(platform => `<details><summary>${e(platform.source)} · ${link(platform.url,platform.title,e)}</summary>${['assignments','materials','announcements','posts','lessons'].map(kind => '<h4>' + {assignments:'作业',materials:'课程资料',announcements:'公告',posts:'讨论',lessons:'录播'}[kind] + '</h4>' + records(data[kind].filter(item => item.course_id === platform.id),e)).join('')}${platform.grades?.length ? '<h4>成绩</h4>' + platform.grades.map(grade => '<p>' + e(grade.title) + ' · ' + e(grade.score ?? '未提供') + ' / ' + e(grade.max_score ?? '未提供') + '</p>').join('') : ''}</details>`).join('') + '<details><summary>上课安排</summary>' + data.timetable.map(item => '<p>周' + '一二三四五六日'[item.weekday - 1] + ' · 第 ' + item.period_start + '–' + item.period_end + ' 节 · ' + e(item.location) + ' · 第 ' + e(item.weeks.join('、')) + ' 周</p>').join('') + '</details>';
        } catch(error) { delete details.dataset.loaded; if (!context.signal.aborted) context.ui.toast(error.message); }
      });
    };
    body.querySelector('[data-current]').onchange = draw;
    body.querySelector('[data-search]').oninput = draw;
    body.querySelector('[data-group]').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const course_ids = [...form.elements.members.selectedOptions].map(option => option.value);
      if (course_ids.length < 2) { context.ui.toast('请选择至少两个平台课程。'); return; }
      const retained = groups.filter(group => !group.course_ids.some(id => course_ids.includes(id)));
      try { await context.api('/groups',{method:'PUT',body:{groups:[...retained,{id:crypto.randomUUID(),title:form.elements.title.value,course_ids}]}}); await refresh(); context.ui.toast('课程已关联。'); }
      catch(error) { if (!context.signal.aborted) context.ui.toast(error.message); }
    };
    const reset = body.querySelector('[data-reset]');
    reset.onclick = context.ui.safeAction(reset,async () => {
      if (await context.ui.confirmDialog('恢复自动关联','将移除手动课程分组，按课程代码和学期重新组织。')) { await context.api('/groups',{method:'PUT',body:{groups:[]}}); await refresh(); context.ui.toast('已恢复自动关联。'); }
    });
    draw();
  });
}
