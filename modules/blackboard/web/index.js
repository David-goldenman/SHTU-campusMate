import {sourcePanel, records} from '/assets/campus.js';

export function mount(container, context) {
  return sourcePanel(container, context, (body,snapshot) => {
    body.innerHTML = '<p class="field-hint">读取未完成课程的资料、作业、成绩与公告；来源未确认的提交状态会保留为未知。</p>' + records(snapshot.data.courses,context.ui.escape);
  });
}
