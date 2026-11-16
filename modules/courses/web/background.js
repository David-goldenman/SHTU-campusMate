import {api} from '/assets/shared.js';
import {acquireDownloader} from './download-service.js';
import {downloadSchedule} from './download-schedule.js';

export function mount(container,context) {
  const {downloads,release}=acquireDownloader(context);
  const background=downloadSchedule(context,downloads,{
    source:signal=>api('/modules/piazza/snapshot',{signal,priority:'low'}),
    syncSource:signal=>api('/modules/piazza/sync',{method:'POST',signal,priority:'low'}),
  });
  return ()=>{background.dispose();release();};
}
