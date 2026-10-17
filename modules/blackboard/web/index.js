import {sourcePanel, records} from '/assets/campus.js';

export function mount(container, context) {
  return sourcePanel(container, context, (body,snapshot) => {
    body.innerHTML = '<p class="field-hint">读取未完成课程的资料、作业、成绩与公告；结合成绩与提交历史区分未提交、草稿、待评分、已评分和豁免，读取失败会标明待核实。</p>' + records(snapshot.data.courses,context.ui.escape);
  });
}
