import {watchAutoSync} from './auto-sync.js';

export function mount(container,context) {
  return watchAutoSync(context.api,context.signal,(value,changed)=>{
    window.dispatchEvent(new CustomEvent('campus:mail-status',{detail:value}));
    if (changed) window.dispatchEvent(new CustomEvent('campus:mail-updated'));
  });
}
