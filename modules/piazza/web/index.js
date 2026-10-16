export async function mount(container, context) {
  const style = document.createElement('link');
  style.rel = 'stylesheet'; style.href = new URL('./styles.css', import.meta.url);
  document.head.append(style);
  const cleanup = () => { style.remove(); container.replaceChildren(); };
  const e = context.ui.escape, options = {signal: context.signal};
  const levels = {high: '优先核对', medium: '值得关注', normal: '普通消息'};
  container.innerHTML = `<div class="piazza-workspace">
    <p>关注 Piazza 课程，按需采集帖子及回复。重要程度来自本地关键词规则，请结合原文核实。每次采集最多 20 帖。</p>
    <details><summary>管理关注课程</summary><p>从 Piazza 课程地址复制课程 ID，每行填写「课程 ID 课程名称」。账号登录在统一设置中完成。</p>
    <form data-config><label>课程列表<textarea data-courses rows="4" placeholder="课程ID 课程名称"></textarea></label><button class="button" type="submit">保存关注课程</button></form></details>
    <div class="piazza-toolbar"><label>课程<select data-course><option value="">请先添加课程</option></select></label>
    <button class="button button-primary" type="button" data-sync>采集最新帖子</button><button class="button" type="button" data-more-sync disabled>继续采集下一页</button><button class="button button-secondary" type="button" data-settings>账号设置</button></div>
    <p role="status" data-status>正在读取本地帖子…</p>
    <form data-filter class="piazza-toolbar"><label>重要程度<select data-level><option value="all">全部</option><option value="high">优先核对</option><option value="medium">值得关注</option><option value="normal">普通消息</option></select></label><label>查找帖子<input data-query maxlength="200" placeholder="标题或正文关键词"></label><button class="button" type="submit">筛选</button></form>
    <div data-posts></div><div class="piazza-toolbar"><button class="button" type="button" data-prev disabled>上一页缓存</button><span data-count></span><button class="button" type="button" data-next disabled>下一页缓存</button></div>
  </div>`;
  const find = selector => container.querySelector(selector);
  let reports = {}, offset = 0, nextOffset = null, revision = 0;
  const selected = () => find('[data-course]').value;
  const status = text => { if (!context.signal.aborted) find('[data-status]').textContent = text; };
  const formatDate = stamp => stamp == null ? '时间待确认' : new Date(stamp * 1000).toLocaleString('zh-CN');

  function updateSyncButton() {
    const report = reports[selected()];
    find('[data-more-sync]').disabled = !selected() || report?.next_offset == null;
    find('[data-more-sync]').textContent = report?.status === 'partial' || report?.status === 'error' ? '重试未完成页' : '继续采集下一页';
    find('[data-sync]').disabled = !selected();
  }

  async function loadCourses() {
    const value = await context.api('/courses');
    if (context.signal.aborted) return;
    reports = value.status;
    const old = selected();
    find('[data-course]').innerHTML = value.courses.map(course => `<option value="${e(course.id)}">${e(course.name)}</option>`).join('') || '<option value="">请先添加课程</option>';
    if (value.courses.some(course => course.id === old)) find('[data-course]').value = old;
    find('[data-courses]').value = value.courses.map(course => course.id + ' ' + course.name).join('\n');
    updateSyncButton();
    await loadPosts(0);
  }

  async function loadPosts(start = 0) {
    offset = start;
    const version = ++revision, course = selected();
    if (!course) {
      find('[data-posts]').innerHTML = context.ui.empty('还没有关注课程', '展开“管理关注课程”，填写课程 ID 与名称。');
      find('[data-count]').textContent = '';
      find('[data-next]').disabled = true; find('[data-prev]').disabled = true;
      status('请先在设置中连接 Piazza，并添加需要关注的课程。');
      return;
    }
    const query = new URLSearchParams({course_id: course, offset: start, level: find('[data-level]').value, q: find('[data-query]').value});
    const value = await context.api('/posts?' + query);
    if (version !== revision || context.signal.aborted) return;
    nextOffset = value.next_offset;
    find('[data-posts]').innerHTML = value.items.map(post => `<article class="panel piazza-post">
      <div class="piazza-meta"><strong>${e(levels[post.level])}</strong><span>${post.read ? '已读' : '未读'} · ${e(formatDate(post.updated_at ?? post.created_at))}</span></div>
      <h3>${e(post.title)}</h3><p>${e(post.reason)}</p><details><summary>展开正文与回复</summary><p class="piazza-text">${e(post.body)}</p></details>
      ${post.attachments.length ? '<ul>' + post.attachments.map(file => `<li><a href="${e(file.url)}" target="_blank" rel="noopener noreferrer">${e(file.name)}</a>（${file.kind === 'image' ? '原始图片' : '原始附件'}）</li>`).join('') + '</ul>' : ''}
      <div class="piazza-toolbar"><a href="${e(post.url)}" target="_blank" rel="noopener noreferrer">在 Piazza 查看</a><button type="button" class="button" data-read="${e(post.id)}" data-value="${!post.read}">${post.read ? '标为未读' : '标为已读'}</button></div></article>`).join('') || context.ui.empty('暂无匹配帖子', '采集最新帖子或调整筛选条件。已缓存的帖子可以离线查看。');
    find('[data-prev]').disabled = start === 0;
    find('[data-next]').disabled = nextOffset == null;
    find('[data-count]').textContent = `${value.total ? start + 1 : 0}–${start + value.items.length} / ${value.total} 条缓存`;
    status(reports[course]?.message || '当前显示本地缓存，点击采集后更新。');
  }

  find('[data-config]').addEventListener('submit', context.ui.safeAction(find('[data-config] button'), async () => {
    const courses = find('[data-courses]').value.split('\n').map(line => line.trim()).filter(Boolean).map(line => {
      const [id, ...name] = line.split(/\s+/);
      return {id, name: name.join(' ') || id};
    });
    await context.api('/courses', {method: 'PUT', body: {courses}});
    await loadCourses();
  }), options);
  find('[data-filter]').addEventListener('submit', context.ui.safeAction(find('[data-filter] button'), () => loadPosts(0)), options);
  find('[data-course]').addEventListener('change', async () => {
    updateSyncButton();
    try { await loadPosts(0); } catch (error) { if (!context.signal.aborted) status(error.message); }
  }, options);
  container.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || button.closest('form')) return;
    await context.ui.safeAction(button, async () => {
      if (button.hasAttribute('data-settings')) context.navigate('settings');
      if (button.hasAttribute('data-sync') || button.hasAttribute('data-more-sync')) {
        const course = selected();
        const start = button.hasAttribute('data-more-sync') ? reports[course].next_offset : 0;
        status('正在采集本页帖子与回复…');
        try {
          reports[course] = await context.api('/courses/' + encodeURIComponent(course) + '/sync', {method: 'POST', body: {offset: start}});
          await loadPosts(0);
        } catch (error) {
          reports[course] = {status: 'error', next_offset: start};
          status(error.message); throw error;
        }
        finally { if (!context.signal.aborted) updateSyncButton(); }
      }
      if (button.dataset.read) {
        await context.api(`/courses/${encodeURIComponent(selected())}/posts/${encodeURIComponent(button.dataset.read)}/read`, {method: 'PUT', body: {read: button.dataset.value === 'true'}});
        await loadPosts(offset);
      }
      if (button.hasAttribute('data-next')) await loadPosts(nextOffset);
      if (button.hasAttribute('data-prev')) await loadPosts(Math.max(0, offset - 20));
    })();
    if (!context.signal.aborted) updateSyncButton();
  }, options);
  try { await loadCourses(); } catch (error) { if (!context.signal.aborted) status(error.message); }
  return cleanup;
}
