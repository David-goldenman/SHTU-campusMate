// The background mount owns transport; page mounts only observe the current turn.
export function createChatSession() {
  let context, owner, turn;
  const listeners = new Set(), drafts = new Map();
  const notify = () => {for (const listener of listeners) listener(turn);};
  function reset() {
    turn?.controller.abort();turn = undefined;drafts.clear();
  }
  function attach(next) {
    reset();context = next;owner = undefined;
    const cleanup = () => {
      if (context !== next) return;
      reset();context = undefined;owner = undefined;listeners.clear();
    };
    next.signal.addEventListener('abort',cleanup,{once:true});
    if (next.signal.aborted) cleanup();
    return cleanup;
  }
  function bindOwner(next) {
    if (owner !== next) {reset();owner = next;}
  }
  function subscribe(listener, signal) {
    if (signal.aborted) return;
    listeners.add(listener);
    signal.addEventListener('abort',() => listeners.delete(listener),{once:true});
  }
  async function run(current, transport) {
    try {
      if (!current.conversationId) {
        current.conversationId = (await transport.api('/conversations',{method:'POST',signal:current.controller.signal})).id;
        if (turn !== current) return;
        notify();
      }
      await transport.api('/chat/stream',{method:'POST',body:{message:current.message,conversation_id:current.conversationId},signal:current.controller.signal,onEvent(value) {
        if (turn !== current || current.controller.signal.aborted) return;
        if (value.type === 'error') throw new Error(value.detail);
        if (value.type === 'activity') current.steps = value.steps;
        if (value.type === 'change') current.changes.push(value.change);
        if (value.type === 'reset') current.text = '';
        if (value.type === 'delta') current.text += value.text;
        if (value.type === 'complete') current.answer = value.message;
        notify();
      }});
      if (!current.answer) throw new Error('回复连接中断，请重试。');
      current.status = 'complete';
      drafts.delete(current.conversationId);
    } catch (error) {
      current.status = current.controller.signal.aborted ? 'stopped' : 'error';
      current.error = (current.status === 'stopped' ? '已停止生成，问题保留在输入框中。' : error.message) + (current.changes.length ? ' 已保存的本地修改见回执，请勿重复执行。' : '');
      if (turn === current) drafts.set(current.conversationId || '',current.message);
    } finally {
      if (turn === current) notify();
    }
  }
  function start(identity, message, messages) {
    if (!context || context.signal.aborted) throw new Error('对话服务尚未就绪，请刷新页面后重试。');
    if (turn?.status === 'running') return;
    drafts.delete(identity || '');
    turn = {conversationId:identity,message,messages:[...messages],text:'',steps:[],changes:[],status:'running',controller:new AbortController()};
    const current = turn;
    notify();
    current.finished = run(current,context);
    return current;
  }
  return {attach,bindOwner,subscribe,start,drafts,
    get current() {return turn;},
    stop() {turn?.controller.abort();},
    forget(identity) {if (turn?.conversationId === identity && turn.status !== 'running') turn = undefined;},
  };
}

export const chatSession = createChatSession();
