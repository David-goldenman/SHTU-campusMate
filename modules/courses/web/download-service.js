import {courseDownloader} from './download-panel.js';

let session;

/** Share one downloader between the course page and the persistent background. */
export function acquireDownloader(context,options) {
  if(!session) {
    const life=new AbortController();
    session={life,refs:0,downloads:courseDownloader({...context,signal:life.signal},options)};
  }
  const held=session;held.refs++;
  let released=false;
  function release() {
    if(released)return;released=true;
    context.signal.removeEventListener('abort',release);
    if(--held.refs===0) {held.life.abort();if(session===held)session=undefined;}
  }
  context.signal.addEventListener('abort',release,{once:true});if(context.signal.aborted)release();
  return {downloads:held.downloads,release};
}
