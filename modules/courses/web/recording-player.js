const prefix = '/api/v1/modules/elrc/playback';

export function openRecording(context, item) {
  const lifetime = new AbortController();
  const removeStyle = context.ui.useStyle(new URL('./recording-player.css', import.meta.url), lifetime.signal);
  const body = document.createElement('div'); body.className = 'recording-player';
  body.innerHTML = '<div class="recording-controls"><label>课次<select data-lesson disabled></select></label><label>播放速度<select data-speed><option value="0.75">0.75 倍</option><option value="1" selected>正常速度</option><option value="1.25">1.25 倍</option><option value="1.5">1.5 倍</option><option value="2">2 倍</option></select></label></div><div class="recording-angles" role="group" aria-label="切换录播画面"></div><div class="recording-screen"></div><div class="recording-feedback"><p role="status" aria-live="polite">正在读取录播课次…</p><button type="button" class="button button-secondary" data-retry hidden>重新加载</button></div><p class="field-hint">可拖动进度条定位；切换画面会保留当前进度。</p><a data-original target="_blank" rel="noopener noreferrer">在教学社区打开 ↗</a>';
  const original = body.querySelector('[data-original]');
  try { const url = new URL(item.url); if (!['https:', 'http:'].includes(url.protocol)) throw new Error(); original.href = url.href; }
  catch { original.remove(); }
  const dialog = context.ui.dialog(item.title || '课堂录播', body); dialog.classList.add('recording-dialog');
  const lessonSelect = body.querySelector('[data-lesson]'), speed = body.querySelector('[data-speed]'), screen = body.querySelector('.recording-screen');
  const feedback = body.querySelector('[role=status]'), retry = body.querySelector('[data-retry]'), angles = body.querySelector('.recording-angles');
  let session, media, mediaEvents, pending, generation = 0, timer, lessonId, sourceIndex = 0;
  let remembered = {seconds:0, playing:false};
  const alive = version => !lifetime.signal.aborted && version === generation;
  const remember = () => { if (media?.readyState >= 1) remembered = {seconds:Number.isFinite(media.currentTime) ? media.currentTime : 0, playing:!media.paused && !media.ended}; };
  function releaseMedia() {
    clearTimeout(timer);
    mediaEvents?.abort();
    if (media) { media.pause(); media.removeAttribute('src'); media.load(); media.remove(); media = null; }
  }
  function close() {
    if (lifetime.signal.aborted) return;
    lifetime.abort(); pending?.abort(); generation++; releaseMedia(); removeStyle();
    context.signal.removeEventListener('abort', close);
    if (dialog.open) dialog.close();
  }
  context.signal.addEventListener('abort', close, {once:true});
  dialog.addEventListener('close', close, {once:true});
  if (context.signal.aborted) { close(); return close; }
  function message(text, failed = false) { feedback.textContent = text; retry.hidden = !failed; }
  async function request(path, signal) {
    const response = await fetch(prefix + path, {credentials:'same-origin', cache:'no-store', signal:AbortSignal.any([lifetime.signal, signal, AbortSignal.timeout(30000)])});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : value.detail?.message || '录播暂时无法读取，请检查教学社区连接。');
    return value;
  }
  function showSource(sources, index, version, preserve) {
    if (!alive(version)) return;
    if (preserve) remember();
    releaseMedia(); sourceIndex = index;
    const video = document.createElement('video'); media = video;
    mediaEvents = new AbortController();
    const mediaSignal = AbortSignal.any([lifetime.signal, mediaEvents.signal]);
    video.controls = true; video.playsInline = true; video.preload = 'metadata';
    video.setAttribute('aria-label', sources[index].label + '录播播放器');
    screen.replaceChildren(video);
    const current = () => alive(version) && media === video;
    angles.replaceChildren(...sources.map((source, i) => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'button button-secondary';
      button.textContent = source.label; button.setAttribute('aria-pressed', String(i === index));
      button.onclick = () => showSource(sources, i, version, true);
      return button;
    }));
    message('正在加载视频…');
    timer = setTimeout(() => { if (current()) message('视频加载超时，可以重试或在教学社区打开。', true); }, 30000);
    video.addEventListener('loadedmetadata', () => {
      if (!current()) return;
      const end = Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.25) : remembered.seconds;
      if (remembered.seconds > 0) video.currentTime = Math.min(remembered.seconds, end);
      video.playbackRate = Number(speed.value);
      clearTimeout(timer); message('已就绪，点击播放即可观看。');
      if (remembered.playing) video.play().catch(() => { if (current()) message('画面已切换，点击播放继续。'); });
    }, {once:true, signal:mediaSignal});
    video.addEventListener('playing', () => { if (current()) message('正在播放 · ' + sources[index].label); }, {signal:mediaSignal});
    video.addEventListener('error', () => { if (current()) { clearTimeout(timer); message('视频加载失败，请重新加载；登录过期时可到设置重新连接教学社区。', true); } }, {signal:mediaSignal});
    const target = new URL(sources[index].url, location.origin);
    if (target.origin !== location.origin || !target.pathname.startsWith(prefix + '/')) { message('播放地址不正确。', true); return; }
    video.src = target.href;
  }
  async function load(reopen = false, preserve = false) {
    if (preserve) remember(); else remembered = {seconds:0, playing:false};
    releaseMedia(); pending?.abort(); pending = new AbortController();
    const signal = pending.signal, version = ++generation;
    lessonSelect.disabled = true; angles.replaceChildren(); message(reopen ? '正在读取录播课次…' : '正在读取这节课的画面…');
    try {
      if (reopen) {
        session = await request('?lesson_id=' + encodeURIComponent(item.id), signal);
        if (!alive(version)) return;
        if (!session.lessons.some(lesson => lesson.id === lessonId)) lessonId = session.selected;
        lessonSelect.replaceChildren(...session.lessons.map(lesson => { const option = document.createElement('option'); option.value = lesson.id; option.textContent = lesson.title; return option; }));
      }
      lessonSelect.value = lessonId;
      const result = await request('/' + encodeURIComponent(session.token) + '/sources?lesson=' + encodeURIComponent(lessonId), signal);
      if (!alive(version)) return;
      if (!Array.isArray(result.sources) || !result.sources.length) throw new Error('这节课暂无可播放的画面。');
      showSource(result.sources, Math.min(sourceIndex, result.sources.length - 1), version, false);
    } catch (error) {
      if (alive(version) && !signal.aborted) message(error.name === 'TimeoutError' ? '录播读取超时，请重试。' : error.message, true);
    } finally { if (alive(version)) lessonSelect.disabled = !session; }
  }
  lessonSelect.onchange = () => { lessonId = lessonSelect.value; sourceIndex = 0; void load(); };
  speed.onchange = () => { if (media) media.playbackRate = Number(speed.value); };
  retry.onclick = () => { void load(true, true); };
  void load(true);
  return close;
}
