export async function mount(container, context) {
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  const e = context.ui.escape, options = {signal: context.signal};
  const cleanup = () => { removeStyle(); container.replaceChildren(); };
  container.innerHTML = `<div class="education-workspace">
    <p>从已同步课程中选择原文，或粘贴自己的资料。生成时会把问题和所选资料发送到设置中配置的 DeepSeek。</p>
    <div class="education-row"><label>学习方式<select data-mode><option value="answer">答疑</option><option value="hint">分步提示</option><option value="quiz">知识自测</option><option value="plan">学习计划</option><option value="notice">通知核对</option></select></label><button type="button" class="button" data-settings>AI 设置</button></div>
    <label>你的问题<textarea data-question rows="3" maxlength="8000" placeholder="例如：结合课堂原文，解释电场叠加，并给一个例子。"></textarea></label>
    <form data-search class="education-row"><label>课程<select data-course><option value="">本学期全部课程</option></select></label><label>检索关键词<input data-query maxlength="200" required placeholder="电场叠加"></label><button class="button" type="submit">检索课程资料</button></form>
    <p role="status" data-status>正在读取课程目录…</p><div data-sources></div>
    <label>补充资料（可选，最多 4000 字）<textarea data-manual rows="4" maxlength="4000" placeholder="粘贴需要核对的原始资料；不要填写账号、密码或密钥。"></textarea></label>
    <div class="education-row"><button type="button" class="button button-secondary" data-preview>预览请求</button><button type="button" class="button button-primary" data-answer>发送所选资料并生成</button></div>
    <details data-preview-panel hidden><summary>请求预览（尚未调用 AI）</summary><pre data-preview-text></pre></details><section data-result aria-live="polite"></section>
  </div>`;
  const find = selector => container.querySelector(selector);
  let sources = [];
  const message = text => { if (!context.signal.aborted) find('[data-status]').textContent = text; };
  async function elrc(path) {
    const response = await fetch('/api/v1/modules/elrc' + path, {signal: context.signal});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '课程模块暂不可用，可先填写补充资料。');
    return value;
  }
  function request() {
    const selected = [...container.querySelectorAll('[data-source]:checked')].map(input => sources[Number(input.dataset.source)]);
    const manual = find('[data-manual]').value.trim();
    if (manual) selected.push({source_id: 'manual:1', text: manual, source_kind: 'manual'});
    if (selected.length > 12) throw new Error('最多选择 12 份资料，包含手填资料。');
    const question = find('[data-question]').value.trim();
    if (!question) throw new Error('请先填写问题。');
    return {question, mode: find('[data-mode]').value, sources: selected};
  }
  find('[data-search]').addEventListener('submit', context.ui.safeAction(find('[data-search] button'), async () => {
    const query = new URLSearchParams({q: find('[data-query]').value, semester: 'current'});
    if (find('[data-course]').value) query.set('course_id', find('[data-course]').value);
    const value = await elrc('/search?' + query);
    if (context.signal.aborted) return;
    sources = value.items;
    find('[data-sources]').innerHTML = sources.map((source, i) => `<label class="education-source"><input type="checkbox" data-source="${i}" ${i < 8 ? 'checked' : ''}><span><strong>${e(source.course_name)} · ${e(source.lesson_label)} · ${source.source_kind === 'summary' ? '学校摘要' : '课堂转写'}</strong><span class="education-text">${e(source.text)}</span></span></label>`).join('');
    message(sources.length ? `找到 ${sources.length} 份资料，请核对后选择。` : '没有匹配资料，请先同步课程或换一个关键词。');
  }), options);
  find('[data-course]').addEventListener('change', () => { sources = []; find('[data-sources]').replaceChildren(); }, options);
  find('[data-settings]').addEventListener('click', () => context.navigate('settings'), options);
  find('[data-preview]').addEventListener('click', context.ui.safeAction(find('[data-preview]'), async () => {
    const value = await context.api('/preview', {method: 'POST', body: request()});
    if (context.signal.aborted) return;
    find('[data-preview-panel]').hidden = false;
    find('[data-preview-panel]').open = true;
    find('[data-preview-text]').textContent = JSON.stringify(value, null, 2);
    message('请求已准备好，尚未调用 AI。');
  }), options);
  find('[data-answer]').addEventListener('click', context.ui.safeAction(find('[data-answer]'), async () => {
    const body = request();
    message('正在生成并校验引用…');
    find('[data-result]').replaceChildren();
    try {
      const value = await context.api('/answer', {method: 'POST', body, timeoutMs:600000});
      if (context.signal.aborted) return;
      const answer = value.answer;
      find('[data-result]').innerHTML = `<h3>学习回答</h3><p class="education-text">${e(answer.answer)}</p>
        ${answer.citations.length ? '<h4>原文依据</h4><ul>' + answer.citations.map(item => `<li><q>${e(item.quote)}</q><br><small>${e(item.source_id)}</small></li>`).join('') + '</ul>' : ''}
        ${answer.uncertainty.length ? '<h4>需要核实</h4><ul>' + answer.uncertainty.map(item => `<li>${e(item)}</li>`).join('') + '</ul>' : ''}
        ${answer.next_steps.length ? '<h4>接下来可以做</h4><ul>' + answer.next_steps.map(item => `<li>${e(item)}</li>`).join('') + '</ul>' : ''}`;
      message('生成完成；引用文字已与所选资料逐字核对，结论仍需结合课程核实。');
    } catch (error) { message(error.message); throw error; }
  }), options);
  try {
    const value = await elrc('/catalog');
    if (!context.signal.aborted) {
      find('[data-course]').innerHTML += value.courses.map(course => `<option value="${e(course.id)}">${e(course.code)} ${e(course.name)}</option>`).join('');
      message(value.courses.length ? '可检索本学期已同步资料。' : '尚未发现课程，可先去课程中心同步，或填写补充资料。');
    }
  } catch (error) { if (!context.signal.aborted) message(error.message); }
  return cleanup;
}
