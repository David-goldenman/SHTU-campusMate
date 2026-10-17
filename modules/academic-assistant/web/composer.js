export function sendOnEnter(event, form) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!event.repeat) form.requestSubmit();
}

export function fitComposer(input) {
  input.style.height = 'auto';
  input.style.height = Math.min(200, Math.max(52, input.scrollHeight)) + 'px';
}
