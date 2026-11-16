export function sendOnEnter(event, form) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!event.repeat) form.requestSubmit();
}

export function fitComposer(input) {
  input.style.height = 'auto';
  input.style.height = Math.min(200, Math.max(52, input.scrollHeight)) + 'px';
}

export function promptModes(items) {
  return items.filter(item=>typeof item.label==='string' && typeof item.prompt==='string' && item.prompt.trim()).map((item,index)=>({
    ...item,id:item.id || 'preset-'+index,description:item.description || '按此方式处理你的问题。',
  }));
}

// Keep the user's draft separate; generated instructions are composed only for sending.
export function composeMessage(text, mode) {
  const body = text.trim();
  if (!mode) return body;
  if (!body) return mode.prompt;
  return `${body}\n\n【学习方式：${mode.label}】\n以下是辅助说明；若与上面我写的具体要求冲突，以我的具体要求为准。\n${mode.prompt}`;
}
