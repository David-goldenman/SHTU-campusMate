import {sourcePanel, records} from '/assets/campus.js';

export function mount(container, context) {
  return sourcePanel(container, context, (body, snapshot) => {
    const data = snapshot.data;
    body.innerHTML = `<p class="field-hint">只读同步课程、课件、公告和作业。课件 ${data.materials.length} 条 · 公告 ${data.announcements.length} 条 · 作业 ${data.assignments.length} 项。按课程浏览完整内容，作业状态统一显示在作业管理中。</p>` + records(data.courses, context.ui.escape);
  });
}
