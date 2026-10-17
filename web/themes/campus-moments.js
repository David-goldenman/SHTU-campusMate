import {getCampusPreferences} from './appearance.js';

export const campusImages = Object.freeze(['campus-water','campus-windows','campus-courtyard','campus-tower','campus-canopy']);
const starts = {dashboard:1,timetable:0};
const icons = {
  previous:'<path d="m14 6-6 6 6 6"/>',next:'<path d="m10 6 6 6-6 6"/>',
  pause:'<path d="M9 5v14M15 5v14"/>',play:'<path d="m9 5 10 7-10 7Z"/>'
};
const icon = name => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'+icons[name]+'</svg>';

// Each module chooses its own footer; this component only displays local artwork.
export function mountCampusMoment(host,location,signal) {
  if (signal.aborted || !Object.hasOwn(starts,location)) return () => {};
  const figure=document.createElement('figure');
  figure.className='campus-moment';figure.dataset.moment=location;
  figure.setAttribute('aria-label','校园图片');figure.setAttribute('aria-roledescription','轮播图');figure.setAttribute('aria-live','off');
  const picture=document.createElement('div');picture.className='campus-moment-picture';
  const frames=[0,1].map(()=>{const image=document.createElement('img');image.alt='';image.width=720;image.height=480;image.decoding='async';image.loading='lazy';picture.append(image);return image;});
  const controls=document.createElement('div');controls.className='campus-moment-controls';
  function button(name,title) {const node=document.createElement('button');node.type='button';node.className='campus-moment-control';node.innerHTML=icon(name);node.setAttribute('aria-label',title);node.title=title;controls.append(node);return node;}
  const previous=button('previous','上一张图片'),pause=button('pause','暂停图片轮播'),next=button('next','下一张图片');
  picture.append(controls);figure.append(picture);host.append(figure);
  const media=window.matchMedia('(prefers-reduced-motion: reduce)'),listeners=[];
  let observer,timer,index=starts[location],active=0,ready=false,loading=false,failures=0,revision=0,disposed=false;
  let inView=typeof IntersectionObserver==='undefined',paused=false,hovered=false,focused=false;
  function listen(target,type,fn) {target.addEventListener(type,fn);listeners.push(()=>target.removeEventListener(type,fn));}
  function sync() {
    clearTimeout(timer);timer=undefined;
    const prefs=getCampusPreferences(),reduced=prefs.reduceMotion||media.matches;
    pause.hidden=!prefs.rotation.autoplay||reduced;
    const title=paused?'继续图片轮播':'暂停图片轮播';pause.setAttribute('aria-label',title);pause.title=title;pause.innerHTML=icon(paused?'play':'pause');
    if (!disposed && inView && !figure.hidden && !document.hidden && !reduced && !paused && !hovered && !focused && prefs.rotation.autoplay && ready && !loading) timer=setTimeout(()=>show((index+1)%campusImages.length),prefs.rotation.seconds*1000);
  }
  function show(nextIndex) {
    if (disposed||figure.hidden) return;
    const token=++revision,target=frames[ready?1-active:0];loading=true;sync();
    target.onload=()=>{
      if (disposed||token!==revision) return;
      frames.forEach(frame=>frame.classList.toggle('is-active',frame===target));
      active=frames.indexOf(target);index=nextIndex;ready=true;loading=false;failures=0;figure.dataset.slide=String(index);sync();
    };
    target.onerror=()=>{if (!disposed&&token===revision) {loading=false;if(++failures<campusImages.length) show((nextIndex+1)%campusImages.length);else sync();}};
    target.src='/assets/themes/assets/'+campusImages[nextIndex]+'.webp';
  }
  function draw() {
    figure.hidden=!getCampusPreferences().moments[location];
    if (figure.hidden && loading) {++revision;loading=false;frames.forEach(frame=>{frame.onload=null;frame.onerror=null;});}
    if (!figure.hidden && inView && !ready && !loading) show(index);
    sync();
  }
  function step(offset) {paused=true;show((index+offset+campusImages.length)%campusImages.length);}
  listen(previous,'click',()=>step(-1));listen(next,'click',()=>step(1));
  listen(pause,'click',()=>{paused=!paused;sync();});
  listen(figure,'mouseenter',()=>{hovered=true;sync();});listen(figure,'mouseleave',()=>{hovered=false;sync();});
  listen(figure,'focusin',()=>{focused=true;sync();});listen(figure,'focusout',event=>{focused=figure.contains(event.relatedTarget);sync();});
  listen(window,'campus:appearance',draw);listen(document,'visibilitychange',sync);listen(media,'change',sync);
  if (typeof IntersectionObserver!=='undefined') {
    observer=new IntersectionObserver(entries=>{
      if (disposed) return;
      for (const entry of entries) if (entry.target===figure) {inView=entry.isIntersecting;if(inView&&!figure.hidden) figure.dataset.revealed='true';}
      draw();
    },{threshold:.12});observer.observe(figure);
  }
  function cleanup() {
    if (disposed) return;disposed=true;++revision;clearTimeout(timer);observer?.disconnect();
    frames.forEach(frame=>{frame.onload=null;frame.onerror=null;});listeners.forEach(remove=>remove());figure.remove();signal.removeEventListener('abort',cleanup);
  }
  signal.addEventListener('abort',cleanup,{once:true});draw();
  return cleanup;
}
