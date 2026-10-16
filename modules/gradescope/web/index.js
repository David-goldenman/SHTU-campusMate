import {sourcePanel, records} from '/assets/campus.js';

export function mount(container, context) {
  return sourcePanel(container, context, (body, snapshot) => {
    body.innerHTML = '<p class="field-hint">课程、作业能力与题目文件会一起同步；跨平台课程及待办可在课程中心和作业管理中查看。</p>' + records(snapshot.data.courses,context.ui.escape);
  });
}
