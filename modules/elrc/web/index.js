import {bindSyncNetwork} from '/assets/sync-network.js';

export async function mount(container, context) {
  const removeStyle = context.ui.useStyle(new URL('./styles.css',import.meta.url),context.signal);
  let poll, wasSyncing = false;
  const cleanup = () => { clearTimeout(poll); removeStyle(); container.replaceChildren(); };
  context.signal.addEventListener('abort', cleanup, {once:true});
  const e = context.ui.escape;
  const options = {signal: context.signal};
  const states = {ready: '已同步', empty: '暂无已发布资料', partial: '部分内容可用', not_synced: '尚未同步', syncing: '同步中', stale: '保留旧缓存，需重试', error: '读取失败'};
  container.innerHTML = `<div class="elrc-workspace">
    <p>查看虚拟社区课程、课堂转写与学校摘要。首次使用请在设置中连接学校 IDS，目标选择 ELRC。</p>
    <div class="elrc-toolbar"><label>学期<select data-term><option value="current">本学期</option><option value="all">全部学期</option></select></label>
    <button class="button button-primary" data-discover>更新课程目录</button><button class="button button-secondary" data-settings>账号设置</button></div>
    <p role="status" data-status>正在读取本地课程目录…</p>
    <div data-network hidden></div>
    <form data-search class="elrc-toolbar"><label>查找已同步的课程资料<input name="query" maxlength="200" required placeholder="例如：电场叠加"></label><button class="button" type="submit">搜索原文</button></form>
    <div data-results></div><div data-courses class="elrc-courses"></div><section data-detail></section>
  </div>`;
  const find = selector => container.querySelector(selector);
  const status = text => { if (!context.signal.aborted) find('[data-status]').textContent = text; };
  const diagnose = bindSyncNetwork(find('[data-network]'), context);
  async function syncAction(action) {
    diagnose.update([]);
    try { await action(); }
    catch (error) {
      if (context.signal.aborted) return;
      status(error.message);
      diagnose.update(error.details?.network_failure ? [error.details.network_failure] : []);
      throw error;
    }
  }
  let activeCourse = '', activeLesson = '', offset = 0;
  let revision = 0;
  const term = () => find('[data-term]').value;

  async function watchSync() {
    clearTimeout(poll);
    const value = await context.api('/sync');
    if (context.signal.aborted) return;
    const running = value.status === 'syncing';
    find('[data-discover]').disabled = running;
    container.querySelectorAll('[data-sync]').forEach(button => {button.disabled = running;});
    diagnose.update(value.network_failure ? [value.network_failure] : []);
    if (running) {
      wasSyncing = true;
      status('后台同步中，可离开此页。' + (value.lesson ? '当前课次：' + value.lesson : '正在读取课程资料…'));
      poll = setTimeout(() => watchSync().catch(error => {if (!context.signal.aborted) status(error.message);}), 1200);
    } else if (wasSyncing) {
      wasSyncing = false;
      await load();
      if (activeCourse && !activeLesson) await showCourse(activeCourse);
      if (value.message) status(value.message);
    }
  }

  async function load() {
    const version = ++revision;
    const value = await context.api('/catalog?semester=' + encodeURIComponent(term()));
    if (version !== revision || context.signal.aborted) return;
    const selected = term();
    find('[data-term]').innerHTML = '<option value="current">本学期</option><option value="all">全部学期</option>' + value.semesters.map(item => `<option value="${e(item.id)}">${e(item.name)}</option>`).join('');
    find('[data-term]').value = selected;
    find('[data-courses]').innerHTML = value.courses.length ? value.courses.map(course => `<article class="panel elrc-card"><h3>${e(course.code)} ${e(course.name)}</h3>
      <p>${e(course.semester)} · ${e(states[course.content_status] || course.content_status)}</p>
      <p>${course.lesson_count} 个课次 · ${course.transcript_count} 份转写 · ${course.summary_count} 份学校摘要 · ${course.material_count} 份课件</p>
      <div class="elrc-actions"><button class="button" data-view="${e(course.id)}">查看内容</button><button class="button button-secondary" data-sync="${e(course.id)}" ${wasSyncing ? 'disabled' : ''}>同步资料</button></div></article>`).join('') : context.ui.empty('还没有课程', '连接学校账号后更新课程目录；已有缓存可离线查看。');
    status(`当前显示 ${value.courses.length} 门课程。${value.updated_at ? '目录更新于 ' + new Date(value.updated_at).toLocaleString('zh-CN') : ''}`);
  }

  async function showCourse(id) {
    activeCourse = id; activeLesson = '';
    const value = await context.api('/courses/' + encodeURIComponent(id));
    if (activeCourse !== id || context.signal.aborted) return;
    find('[data-detail]').innerHTML = `<h3>${e(value.course.name)}</h3><p>${e(states[value.status] || value.status)} ${e(value.error)}</p>
      <a href="${e(value.source_url)}" target="_blank" rel="noopener noreferrer">打开学校课程页</a>
      <div class="elrc-lessons">${value.lessons.map(lesson => `<button class="button" data-lesson="${e(lesson.id)}">${e(lesson.label)} · ${lesson.segments} 段转写 / ${lesson.chapters} 节摘要</button>`).join('') || '<p>同步资料后，已发布的课次会显示在这里。</p>'}</div>
      ${value.materials.length ? '<h4>已发布课件</h4><ul>' + value.materials.map(item => `<li>${e(item.name || item.title || '课程资料')} · 请在学校课程页查看</li>`).join('') + '</ul>' : ''}<div data-transcript></div>`;
  }

  const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  async function showLesson(id, next = 0) {
    activeLesson = id; offset = next;
    const course = activeCourse;
    const value = await context.api(`/courses/${encodeURIComponent(course)}/lessons/${encodeURIComponent(id)}?offset=${next}`);
    if (activeCourse !== course || activeLesson !== id || offset !== next || context.signal.aborted) return;
    find('[data-transcript]').innerHTML = `<h4>${e(value.lesson.label)}</h4><p>转写状态：${e(states[value.voice_state] || value.voice_state)} · 学校摘要状态：${e(states[value.summary_state] || value.summary_state)}</p>
      <details><summary>学校 AI 摘要（${value.summary.length} 节）</summary>${value.summary.map(row => `<h4>${e(row.title)}</h4><p class="elrc-text">${e(row.text)}</p>`).join('') || '<p>暂无学校摘要。</p>'}</details>
      <h4>课堂转写</h4>${value.transcript.map(row => `<p class="elrc-text"><span class="elrc-time">${time(row.start_seconds)}</span> ${e(row.text)}</p>`).join('') || '<p>暂无可读取的转写。</p>'}
      <div class="elrc-actions"><button class="button" data-page="${Math.max(0, next - 100)}" ${next === 0 ? 'disabled' : ''}>上一页</button><span>${value.total ? next + 1 : 0}–${Math.min(next + 100, value.total)} / ${value.total}</span><button class="button" data-page="${next + 100}" ${next + 100 >= value.total ? 'disabled' : ''}>下一页</button></div>`;
  }

  container.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || !container.contains(button) || button.closest('form')) return;
    await context.ui.safeAction(button, async () => {
      if (button.hasAttribute('data-settings')) context.navigate('settings');
      if (button.hasAttribute('data-discover')) {
        status('正在更新学校课程目录…');
        await syncAction(async () => {
          await context.api('/discover', {method: 'POST', body: {semester: term()}});
          await load();
        });
      }
      if (button.dataset.view) await showCourse(button.dataset.view);
      if (button.dataset.sync) {
        status('正在后台同步，可离开此页。已保存的内容可继续读取。');
        await syncAction(async () => {
          await context.api('/courses/' + encodeURIComponent(button.dataset.sync) + '/sync', {method: 'POST', body: {force: false}});
          await watchSync();
        });
      }
      if (button.dataset.lesson) await showLesson(button.dataset.lesson);
      if (button.hasAttribute('data-page')) await showLesson(activeLesson, Number(button.dataset.page));
    })();
  }, options);
  find('[data-term]').addEventListener('change', async () => {
    activeCourse = ''; activeLesson = '';
    find('[data-detail]').replaceChildren(); find('[data-results]').replaceChildren();
    try { await load(); } catch (error) { if (!context.signal.aborted) status(error.message); }
  }, options);
  find('[data-search]').addEventListener('submit', context.ui.safeAction(find('[data-search] button'), async () => {
    const query = find('[name=query]').value;
    const value = await context.api('/search?' + new URLSearchParams({q: query, semester: term()}));
    if (context.signal.aborted) return;
    find('[data-results]').innerHTML = '<h3>搜索结果</h3>' + (value.items.map(item => `<article class="panel elrc-card"><strong>${e(item.course_name)} · ${e(item.lesson_label)} · ${item.source_kind === 'summary' ? '学校摘要' : '课堂转写'}</strong><p class="elrc-text">${e(item.text)}</p><small>${e(item.source_id)} · ${time(item.start_seconds)}</small></article>`).join('') || '<p>没有匹配资料，请先同步课程或换一个关键词。</p>');
  }), options);
  try { await load(); await watchSync(); } catch (error) { if (!context.signal.aborted) status(error.message); }
  return cleanup;
}
