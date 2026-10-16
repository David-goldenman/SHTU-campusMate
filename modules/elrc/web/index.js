import {sourcePanel, records, link} from '/assets/campus.js';

export function mount(container,context) {
  const e = context.ui.escape;
  return sourcePanel(container,context,(body,snapshot) => {
    body.innerHTML = '<details><summary>课程与章节资料</summary>' + records([...snapshot.data.courses,...snapshot.data.materials],e) + '</details><div class="campus-list">' + snapshot.data.lessons.map(item => `<article class="campus-item"><h4>${link(item.url,item.title,e)}</h4><p class="field-hint">${e(item.term)}</p><button type="button" class="text-button" data-recording="${e(item.id)}">读取录播课次</button></article>`).join('') + '</div><div class="campus-detail" data-lessons></div><div class="campus-detail" data-transcript aria-live="polite"></div>';
    body.querySelectorAll('[data-recording]').forEach(button => button.onclick = context.ui.safeAction(button,async () => {
      const item = snapshot.data.lessons.find(item => item.id === button.dataset.recording);
      const data = await context.api('/recording?' + new URLSearchParams({course_id:item.recording_course_id,recording_id:item.source_id}));
      body.querySelector('[data-lessons]').innerHTML = data.lessons.map(lesson => `<article class="campus-item"><h4>${e(lesson.title)}</h4>${lesson.streams.map(stream => `<button type="button" class="text-button" data-stream="${e(stream.id)}">${e(stream.name)} · 转写与摘要</button>`).join(' ')}</article>`).join('') || '<p>该录播暂未提供可读课次。</p>';
      body.querySelectorAll('[data-stream]').forEach(control => control.onclick = context.ui.safeAction(control,async () => {
        const result = await context.api('/transcript?stream_id=' + encodeURIComponent(control.dataset.stream));
        body.querySelector('[data-transcript]').innerHTML = '<article class="campus-item"><h3>学校摘要</h3>' + result.summary.map(item => `<h4>${e(item.title)}</h4><p>${e(item.body_text)}</p>`).join('') + '<h3>课程转写</h3>' + result.transcript.map(line => `<p>${line.start === null ? '' : '[' + Math.floor(line.start / 60) + ':' + String(Math.floor(line.start % 60)).padStart(2,'0') + '] '}${e(line.text)}</p>`).join('') + '<p class="field-hint">' + e(result.issues.join('；')) + '</p></article>';
      }));
    }));
  });
}
