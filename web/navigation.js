// Request counters and worker activity do not change the views being mounted.
export function navigationChanged(previous, next) {
  if (previous.csrf_token !== next.csrf_token) return true;
  const catalog = value => ({
    categories:value.categories,
    modules:value.modules.map(({runtime, ...info}) => info),
  });
  return JSON.stringify(catalog(previous)) !== JSON.stringify(catalog(next));
}
