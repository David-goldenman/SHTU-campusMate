// Short-lived presentation copies. The backend remains the source of truth.
const entries = new Map();
const maxAge = 60000, maxEntries = 12;
let generation = 0;
const channel = typeof window !== 'undefined' && typeof window.BroadcastChannel === 'function'
  ? new window.BroadcastChannel('campus.view-cache') : null;

export function invalidateViews(broadcast = true) {
  generation++;
  entries.clear();
  if (broadcast) channel?.postMessage('invalidate');
}
if (channel) channel.onmessage = () => invalidateViews(false);

/** Preview a recently visited view only after its server confirms the current account. */
export async function readView(context, path, preview) {
  const module = context.module;
  if (!module?.id) return {value:await context.api(path), unchanged:false};
  const key = [module.id, module.frontend_url, path].join('\n');
  const version = generation;
  let previous = entries.get(key), shown = false, checkedOwner;
  if (previous && Date.now() - previous.savedAt >= maxAge) {entries.delete(key);previous=undefined;}
  // Verify and paint the small preview before starting expensive aggregation.
  if (previous && preview) {
    try {checkedOwner=(await context.api('/view-state')).account_revision;} catch { /* Fresh data still supplies the normal error path. */ }
    if (!context.signal.aborted && version === generation && checkedOwner && checkedOwner === previous.owner) {
      await preview(structuredClone(previous.value));
      shown = true;
    } else entries.delete(key);
  }
  context.signal.throwIfAborted();
  let value;
  const changed = () => Object.assign(new Error('账号或页面数据已更新，请重新打开页面。'),{status:409});
  try {value = await context.api(path);}
  catch (error) {
    context.signal.throwIfAborted();
    if (version !== generation) throw changed();
    if (!previous || Date.now()-previous.savedAt>=maxAge || [401,403,409].includes(error.status) || error.name==='AbortError') throw error;
    // A failed source request is not proof the account still owns this cache.
    let owner;
    try {owner=(await context.api('/view-state')).account_revision;} catch {throw error;}
    context.signal.throwIfAborted();
    if (!owner || owner!==previous.owner || version!==generation) {entries.delete(key);throw changed();}
    return {value:structuredClone(previous.value),unchanged:shown,cached:true,error};
  }
  context.signal.throwIfAborted();
  if (version !== generation) throw changed();
  const owner = value?.account_revision;
  if (checkedOwner && owner && owner !== checkedOwner) {
    entries.delete(key);
    throw Object.assign(new Error('账号已切换，请重新打开页面。'),{status:409});
  }
  if (typeof owner !== 'string' || !owner) return {value, unchanged:false};
  const content = JSON.stringify(value);
  entries.delete(key);
  entries.set(key,{owner,value:structuredClone(value),content,savedAt:Date.now()});
  while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
  return {value, unchanged:shown && previous.owner === owner && previous.content === content};
}
