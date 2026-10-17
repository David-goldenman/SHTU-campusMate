import {sourcePanel, records} from '/assets/campus.js';

export function mount(container, context) {
  return sourcePanel(container, context, (body,snapshot) => {
    body.innerHTML = '<p class="field-hint">读取未完成课程的资料、作业、成绩与公告；作业没有提交记录时显示为未提交。</p>' + records(snapshot.data.courses,context.ui.escape);
  });
}
