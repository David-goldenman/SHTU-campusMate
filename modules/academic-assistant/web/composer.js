export function sendOnEnter(event, form) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!event.repeat) form.requestSubmit();
}
