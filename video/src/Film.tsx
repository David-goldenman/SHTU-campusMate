import React from 'react';
import {AbsoluteFill,Audio,Sequence,Img,OffthreadVideo,Easing,interpolate,spring,staticFile,useCurrentFrame,useVideoConfig} from 'remotion';
import film from './film.json';
import framing from './framing.json';
import operations from './operations.json';
import {ChatSources} from './ChatSources';
import './film.css';

type SceneData=typeof film.scenes[number];
type Rect={x:number;y:number;width:number;height:number};
type Shot={at:number;duration:number;label:string;rect:Rect|null};
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'} as const;
const ease=Easing.bezier(.22,.8,.2,1);
const progress=(f:number,a:number,b:number)=>interpolate(f,[a,b],[0,1],{...clamp,easing:ease});
const bounded=(value:number,min:number,max:number)=>Math.max(min,Math.min(max,value));
const agendaAt=operations.find(o=>o.id==='timetable')!.steps.find(s=>s.type==='capture'&&'name' in s&&s.name==='agenda')!.at+.25;
const mobileMapAt=operations.find(o=>o.id==='mobile')!.steps.find(s=>s.type==='navigate')!.at;
const themeClips=['prts','observatory','star-notes'].map(id=>operations.find(o=>o.id===id)!);

function Rise({children,delay=0}:{children:React.ReactNode;delay?:number}){
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  const p=spring({frame:frame-delay,fps,config:{damping:24,stiffness:140}});
  return <div style={{opacity:progress(frame,delay,delay+22),transform:`translateY(${Math.round((1-p)*24)}px)`}}>{children}</div>;
}
function Intro(){
  const frame=useCurrentFrame();
  const cards=[['学校邮箱','那封重要的通知',1120,205],['Blackboard','课件与课程公告',1430,400],['Gradescope','下一份作业的截止',1090,600],['教务与课程群','课室、日程与群通知',1430,790]] as const;
  return <>
    <div className="intro-copy"><Rise><span className="kicker">CAMPUS / EVERYDAY</span></Rise><Rise delay={8}><h1>信息越多，<br/>越需要<br/><em>一个工作台。</em></h1></Rise><Rise delay={45}><p>邮件、课件、作业、教务与课程群。<br/>彼此关联，却散在不同的平台。</p></Rise></div>
    <svg className="intro-network" width="840" height="900" viewBox="0 0 840 900"><path d="M120 180 C520 180 160 440 560 440 S180 610 130 700" fill="none" stroke="#88c0d0" strokeWidth="3" pathLength="1" strokeDasharray="1" strokeDashoffset={1-progress(frame,30,240)}/></svg>
    {cards.map(([name,caption,x,y],i)=><div className="platform" key={name} style={{left:x,top:y,opacity:progress(frame,24+i*24,48+i*24),transform:`translateY(${Math.round((1-progress(frame,24+i*24,70+i*24))*30)}px)`}}><span>0{i+1} / SOURCE</span><h2>{name}</h2><p>{caption}</p><i/></div>)}
    <div className="intro-foot">把信息连起来，给下一步留出空间。</div>
  </>;
}
function AgentIntro(){
  const frame=useCurrentFrame();
  return <><div className="agent-copy"><Rise><span className="kicker">CONTEXT → ACTION</span></Rise><Rise delay={8}><h1>让信息，<br/>走向<em>下一步。</em></h1></Rise><Rise delay={30}><p>理解上下文，调用工具，与你协作。</p></Rise></div><div className="agent-orbit"><svg width="600" height="600" viewBox="0 0 600 600"><circle cx="300" cy="300" r="220" stroke="#4c566a" strokeWidth="1" fill="none"/><circle cx="300" cy="300" r="160" stroke="#88c0d0" strokeWidth="2" fill="none" pathLength="1" strokeDasharray=".7 .3" transform={`rotate(${frame*.25} 300 300)`}/><path d="M80 300H165M435 300H520M300 80V165M300 435V520" stroke="#88c0d0" strokeWidth="3"/></svg><div><span>AI</span><small>AGENT</small></div></div></>;
}
function Closing(){
  return <><div className="closing-brand"><Rise><Img className="closing-logo" src={staticFile(film.logo)}/></Rise><Rise delay={10}><span className="kicker">{film.tagline}</span><h1>{film.brand}</h1><h2>{film.english}</h2></Rise><Rise delay={26}><p>把信息连起来，<br/>把下一步想清楚。</p></Rise></div><div className="closing-team"><Rise delay={32}><span className="kicker">MADE BY</span><h2>{film.team}<small>制作</small></h2></Rise><div className="team-members">{film.members.map((member,i)=><Rise key={member.github} delay={42+i*8}><div><span>@{member.github}</span>{' '}<strong>{member.name}</strong></div></Rise>)}</div></div><div className="closing-repo"><Rise delay={74}><span>代码与项目</span><p>{film.repository}</p></Rise></div></>;
}
function Agenda(){
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),p=interpolate(frame,[agendaAt*fps,(agendaAt+1)*fps],[0,1],{...clamp,easing:Easing.inOut(Easing.cubic)});
  return <div className="agenda-focus" style={{clipPath:`inset(0 0 ${(1-p)*100}% 0)`}}><span className="kicker">TIMETABLE / 日程与截止事项</span><h2>课程之外，安排也要接得上。</h2><p>作业、活动和自己的复习计划，在同一处核对。</p><div className="agenda-image"><Img src={staticFile('screens/agenda.png')}/></div><div className="agenda-notes"><div><i style={{background:'#d08770'}}/><strong>先看截止</strong><span>周二 HW2 · 周四 HW2_p1 / HW2_p2</span></div><div><i style={{background:'#a3be8c'}}/><strong>再留时间</strong><span>让复习安排落到具体的一天</span></div><div><i style={{background:'#88c0d0'}}/><strong>跟随校历</strong><span>教学周与来源同步</span></div></div></div>;
}
function camera(rect:Rect|null){
  if(!rect)return {scale:1,x:0,y:0};
  const scale=bounded(Math.min(1740/(rect.width+60),800/(rect.height+60)),1,1.5);
  return {scale,x:bounded(920-(rect.x+rect.width/2)*scale,1840-1840*scale,0),y:bounded(450-(rect.y+rect.height/2)*scale,900-900*scale,0)};
}
function FramedClip({id}:{id:string}){
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),shots=(framing as Record<string,Shot[]>)[id]||[];
  let view=camera(null),highlight:Rect|null=null,visibility=0;
  for(const shot of shots){
    if(frame<shot.at*fps)break;
    const to=camera(shot.rect),p=progress(frame,shot.at*fps,(shot.at+shot.duration)*fps);
    view={scale:view.scale+(to.scale-view.scale)*p,x:view.x+(to.x-view.x)*p,y:view.y+(to.y-view.y)*p};
    highlight=shot.rect||(p<1?highlight:null);visibility=shot.rect?p:1-p;
  }
  const box=highlight?{x:highlight.x*view.scale+view.x-10,y:highlight.y*view.scale+view.y-10,width:highlight.width*view.scale+20,height:highlight.height*view.scale+20}:null;
  return <><div style={{position:'absolute',inset:0,transformOrigin:'0 0',transform:`translate(${Math.round(view.x)}px,${Math.round(view.y)}px) scale(${view.scale})`}}><OffthreadVideo src={staticFile('recordings/'+id+'.mp4')} muted style={{width:1840,height:900,display:'block'}}/></div>{box&&visibility>0?<svg className="focus-guide" width="1840" height="900" style={{opacity:visibility*.9}}><path d={`M0 0H1840V900H0Z M${box.x} ${box.y}v${box.height}h${box.width}v-${box.height}Z`} fill="#eceff4b8" fillRule="evenodd"/><rect x={box.x} y={box.y} width={box.width} height={box.height} rx="10" fill="none" stroke="#88c0d0" strokeWidth="3"/></svg>:null}</>;
}
function Product({scene}:{scene:SceneData}){
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  return <div className="product-stage"><FramedClip id={scene.clip}/>{scene.id==='timetable'&&frame>=agendaAt*fps?<Agenda/>:null}</div>;
}
function Themes(){
  const frame=useCurrentFrame(),{fps}=useVideoConfig();
  let cursor=0;const clips=themeClips.map(clip=>{const at=cursor;cursor+=clip.seconds;return [clip.id,at,clip.seconds] as const;});
  const active=Math.max(0,clips.findLastIndex(([,at])=>frame>=at*fps)),reveal=interpolate(frame-clips[active][1]*fps,[0,fps],[0,1],{...clamp,easing:Easing.inOut(Easing.cubic)});
  return <div className="product-stage">{active>0&&reveal<1?<Img src={staticFile('screens/'+clips[active-1][0]+'.png')} style={{position:'absolute',width:1840,height:900}}/>:null}{clips.map(([id,at,seconds],i)=><Sequence key={id} from={at*fps} durationInFrames={seconds*fps}><div style={{position:'absolute',inset:0,clipPath:i===active&&i>0?`inset(0 ${Math.round((1-reveal)*1840)}px 0 0)`:undefined}}><OffthreadVideo src={staticFile('recordings/'+id+'.mp4')} muted style={{width:1840,height:900,display:'block'}}/></div></Sequence>)}</div>;
}
function Mobile(){
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),p=progress(frame,0,60),map=frame>mobileMapAt*fps;
  return <><div className="mobile-copy"><Rise><span className="kicker">CAMPUS / ON THE MOVE</span></Rise><Rise delay={10}><h2>今天要做的事，<br/>带在手边。</h2></Rise><Rise delay={32}><p>从电脑上的全局规划，<br/>到手机上的下一步行动。</p></Rise><div className="mobile-points">{['逐日查看课程与教室','集中核对安排与截止','在地图中找到下一站'].map((text,i)=><Rise key={text} delay={50+i*22}><div className={(map?i===2:i<2)?'active':''}><i>{String(i+1).padStart(2,'0')}</i><span>{text}</span></div></Rise>)}</div><span className="mobile-tag">{map?'MAP / 下一站':'TIMETABLE / 今天与明天'}</span></div><svg className="mobile-path" viewBox="0 0 1920 1080"><path d="M890 850 C1190 850 1000 420 1250 420" fill="none" stroke="#b9cedc" strokeWidth="2" pathLength="1" strokeDasharray="1" strokeDashoffset={1-progress(frame,35,140)}/><circle cx="890" cy="850" r="6" fill="#88c0d0"/></svg><div className="phone" style={{opacity:p,transform:`translateX(${Math.round((1-p)*100)}px)`}}><OffthreadVideo src={staticFile('recordings/mobile.mp4')} muted style={{width:430,height:860,display:'block'}}/></div></>;
}
function Veil({scene,index}:{scene:SceneData;index:number}){
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),length=Math.round(film.transitionSeconds*fps),entry=index>0&&frame<length,exit=index<film.scenes.length-1&&frame>=scene.seconds*fps-length;
  if(!entry&&!exit)return null;
  const phase=(entry?length+frame:frame-(scene.seconds*fps-length))/(length*2-1),target=entry?scene:film.scenes[index+1];
  const cover=interpolate(phase,[0,.25,.65,1],[0,1,1,0],{...clamp,easing:Easing.inOut(Easing.cubic)});
  const text=interpolate(phase,[.14,.3,.65,.88],[0,1,1,0],{...clamp,easing:Easing.inOut(Easing.cubic)});
  const p=phase<.5?phase*2:phase*2-1,points=phase<.5?[[-100,830],[440,830],[540,750],[960,750]]:[[960,750],[1380,750],[1480,830],[2020,830]];
  const dot=[0,1].map(axis=>(1-p)**3*points[0][axis]+3*(1-p)**2*p*points[1][axis]+3*(1-p)*p*p*points[2][axis]+p**3*points[3][axis]);
  const control1=[0,1].map(axis=>points[0][axis]+(points[1][axis]-points[0][axis])*p),control2=[0,1].map(axis=>(1-p)**2*points[0][axis]+2*(1-p)*p*points[1][axis]+p*p*points[2][axis]);
  const line=(phase<.5?'M-100 830':'M-100 830 C440 830 540 750 960 750')+` C${control1.join(' ')} ${control2.join(' ')} ${dot.join(' ')}`;
  return <div className="transition-veil" style={{clipPath:entry?`inset(0 0 0 ${(1-cover)*100}%)`:`inset(0 ${(1-cover)*100}% 0 0)`}}><div className="transition-label" style={{opacity:text,transform:`translateY(${Math.round((phase<.5?1-text:text-1)*18)}px)`}}><span>接下来 / {target.chapter}</span><h2>{target.title}</h2><i/></div><svg width="1920" height="1080" viewBox="0 0 1920 1080"><path d={line} fill="none" stroke="#88c0d0" strokeWidth="3"/><path d="M-100 850 C440 850 540 770 960 770 S1480 850 2020 850" fill="none" stroke="#d8e2ec" strokeWidth="1"/><circle cx={dot[0]} cy={dot[1]} r="7" fill="#5e81ac"/></svg></div>;
}
function Scene({scene,index}:{scene:SceneData;index:number}){
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),dark=scene.id==='agent-intro';
  const cue=scene.cues.findLast(c=>frame>=c.at*fps)?.text,product=!!scene.clip||scene.id==='themes'||scene.id==='group-sources';
  return <AbsoluteFill className={dark?'film-scene dark':'film-scene'}>
    {product?<><header className="scene-heading" style={{transform:`translateY(${Math.round((1-progress(frame,0,34))*12)}px)`}}><div className="chapter">{scene.chapter}</div><h1>{scene.title}</h1><p>{scene.subtitle}</p></header>{scene.id==='themes'?<Themes/>:scene.id==='group-sources'?<ChatSources/>:scene.id==='mobile'?<Mobile/>:<Product scene={scene}/>}<footer className="product-footer"><span>{cue}</span><small>{scene.id==='map'||(scene.id==='mobile'&&frame>=mobileMapAt*fps)?'地图 © OpenStreetMap contributors · 真实界面':scene.id==='mobile'?'真实响应式网页 · 演示数据':scene.id==='group-sources'?'聊天界面还原 · 演示消息':scene.id==='groups'?'真实界面 · 演示群消息':['schedule','study','advising'].includes(scene.id)?'真实界面 · 对话重放':'真实界面 · 脱敏演示'}</small></footer></>:scene.id==='fragmented'?<Intro/>:scene.id==='agent-intro'?<AgentIntro/>:<Closing/>}
    {!product?<div className="brand-footer">campusMate <span>/ PERSONAL LEARNING TERMINAL</span></div>:null}
    <Veil scene={scene} index={index}/>
  </AbsoluteFill>;
}
export const Film:React.FC=()=>{
  const frame=useCurrentFrame(),{durationInFrames}=useVideoConfig();let cursor=0;
  return <AbsoluteFill className="film-root"><Audio src={staticFile(film.music)} volume={f=>interpolate(f,[0,72,durationInFrames-150,durationInFrames],[0,.82,.82,0],clamp)}/>{film.scenes.map((scene,index)=>{const from=cursor;cursor+=scene.seconds*film.fps;return <Sequence key={scene.id} from={from} durationInFrames={scene.seconds*film.fps}><Scene scene={scene} index={index}/></Sequence>;})}<div className="film-progress"><i style={{width:1920*frame/(durationInFrames-1)}}/></div><div className="film-fade" style={{opacity:1-progress(frame,0,36)+progress(frame,durationInFrames-45,durationInFrames-1)}}/></AbsoluteFill>;
};

