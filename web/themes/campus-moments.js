import {getAppearance} from './appearance.js';

const scenes = Object.freeze({
  dashboard:{image:'campus-windows',title:'今天的进度条，先停在这里。',caption:'校园切片 · 夜窗',alt:'校园夜晚亮灯的窗格，蓝白网点版画'},
  timetable:{image:'campus-water',title:'课表排满了，天空还空着。',caption:'校园切片 · 湖畔',alt:'水边的玻璃建筑、树木与步道，蓝白网点版画'}
});

// Modules opt in at their own page footer; no global route or business-ID branching.
export function mountCampusMoment(host,location,signal) {
  if (signal.aborted || !Object.hasOwn(scenes,location)) return () => {};
  const scene=scenes[location],figure=document.createElement('figure');
  figure.className='campus-moment';
  figure.dataset.moment=location;
  figure.setAttribute('aria-label','校园切片');
  const caption=document.createElement('figcaption'),label=document.createElement('span'),title=document.createElement('p'),link=document.createElement('a');
  label.className='campus-moment-label';label.textContent=scene.caption;
  title.textContent=scene.title;
  link.href='#settings?tab=appearance';link.textContent='调整彩蛋';link.className='campus-moment-link';
  caption.append(label,title,link);
  const picture=document.createElement('div');picture.className='campus-moment-picture';
  const image=document.createElement('img');image.alt=scene.alt;image.width=720;image.height=location==='timetable'?540:480;image.loading='lazy';image.decoding='async';
  picture.append(image);figure.append(caption,picture);host.append(figure);
  let observer;
  function draw() {
    figure.hidden=!getAppearance().moments[location];
    if (!figure.hidden && !image.getAttribute('src')) image.src='/assets/themes/assets/'+scene.image+'.webp';
    if (!figure.hidden && observer && !figure.dataset.revealed) observer.observe(figure);
  }
  if (typeof IntersectionObserver !== 'undefined') {
    observer=new IntersectionObserver(entries=>{
      for (const entry of entries) if (entry.isIntersecting && !figure.hidden) {
        figure.dataset.revealed='true';observer.unobserve(figure);
      }
    },{threshold:.12});
  }
  function cleanup() {
    observer?.disconnect();figure.remove();
    window.removeEventListener('campus:appearance',draw);
    signal.removeEventListener('abort',cleanup);
  }
  window.addEventListener('campus:appearance',draw);
  signal.addEventListener('abort',cleanup,{once:true});
  draw();
  return cleanup;
}
