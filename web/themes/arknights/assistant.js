export async function mount(container, context) {
  let frame;
  context.signal.addEventListener('abort', () => {cancelAnimationFrame(frame);container.classList.remove('ark-assistant');}, {once:true});
  container.classList.add('ark-assistant');
  const cleanup = await context.defaultView(container);
  if (!context.signal.aborted && new URLSearchParams(location.hash.split('?')[1]).get('view') === 'assistant') {
    container.querySelector('[data-home]').click();
    history.replaceState(null, '', '#dashboard');
    frame = requestAnimationFrame(() => container.querySelector('[name=message]').focus({preventScroll:true}));
  }
  return cleanup;
}
