import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {sourceVersion,affectedInterfacePaths} from './source-version.mjs';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const json=async path=>JSON.parse(await readFile(resolve(video,path),'utf8'));
const [film,operations,captures,sources,dialogues,chats]=await Promise.all(['src/film.json','src/operations.json','production/captures.json','production/source-data.json','production/dialogues.json','production/group-chats.json'].map(json));
const duration=film.scenes.reduce((n,s)=>n+s.seconds,0);
const version=await sourceVersion();
assert(duration>0&&duration<=480);assert.equal(film.fps,60);
assert.equal(new Set(film.scenes.map(s=>s.id)).size,film.scenes.length);
assert.equal((await readFile(resolve(video,'public',film.music))).subarray(0,4).toString(),'OggS');
const score=spawnSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',resolve(video,'public',film.music)],{encoding:'utf8',windowsHide:true});
assert.equal(score.status,0,score.stderr);assert(Number(score.stdout)>=duration-.02,'运行 npm run music 更新配乐时长。');
assert.equal(captures.length,operations.length);
for(const operation of operations){
  const capture=captures.find(c=>c.id===operation.id);assert(capture,operation.id);
  assert.deepEqual(capture.unexpected,[]);assert.deepEqual(capture.errors,[]);
  assert(capture.pointer.maxStep<=48,operation.id+': 鼠标帧间连续');
  assert(capture.pointer.maxClickError<=5,operation.id+': 鼠标到达后操作');
  if(['preferences','timetable','groups'].includes(operation.id))assert(capture.pointer.modalFrames>0,operation.id+': 弹窗中的鼠标可见');
  const width=operation.mobile?860:2760,height=operation.mobile?1720:1350;
  assert.equal(capture.width,width);assert.equal(capture.height,height);assert.equal(capture.seconds,operation.seconds);
  assert(Array.isArray(operation.modules),'声明实际使用的页面模块：'+operation.id);
  if(capture.version?.sha256!==version.sha256)assert.deepEqual(affectedInterfacePaths(capture,operation),[],'需要更新界面素材：'+operation.id);
  assert.equal(capture.framing.length,operation.steps.filter(s=>s.type==='focus').length);
  for(const shot of capture.framing){if(shot.rect){assert(shot.rect.y>=-2&&shot.rect.y<900,operation.id+': 聚焦位置');assert(shot.rect.x>=-2&&shot.rect.x<1840,operation.id+': 聚焦位置');}}
  const probe=spawnSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',resolve(video,'public/recordings',operation.id+'.mp4')],{encoding:'utf8',windowsHide:true});assert.equal(probe.status,0,probe.stderr);
  const media=JSON.parse(probe.stdout),stream=media.streams.find(s=>s.codec_type==='video');
  assert.equal(stream.width,width);assert.equal(stream.height,height);assert.equal(Number(stream.nb_frames),operation.seconds*film.fps);assert(Math.abs(Number(media.format.duration)-operation.seconds)<.025);
  let previous=0;
  for(const step of operation.steps){assert(step.at>=previous&&step.at<operation.seconds);previous=step.at;if(step.duration)assert(step.at+step.duration<=operation.seconds);}
  if(operation.steps.length){
    const end=Math.max(...operation.steps.map(s=>s.at+(s.duration||0)));
    assert(operation.seconds-film.transitionSeconds-end>=2.8,operation.id+': 转场前保留阅读时间');
  }
  if(operation.id==='timetable'){
    const agenda=operation.steps.find(s=>s.type==='capture'&&s.name==='agenda');
    assert(operation.seconds-film.transitionSeconds-agenda.at-1.25>=3,'日程局部展开后的阅读时间');
  }
  if(!operation.mobile)for(const step of operation.steps.filter(s=>['click','close','select','type'].includes(s.type))){
    const move=operation.steps.findLast(s=>s.type==='move'&&s.at<step.at);
    assert(move?.selector===step.selector,operation.id+': 操作前移动到目标');
    assert(move.duration>=1&&step.at-move.at-move.duration>=0&&step.at-move.at-move.duration<.12);
  }
  if(['schedule','study','advising'].includes(operation.id)){for(const event of ['activity','delta','complete'])assert(capture.stream.includes(event),operation.id+': '+event);}
}
for(const scene of film.scenes){assert(scene.title&&scene.subtitle&&scene.seconds>0);if(scene.clip){const op=operations.find(o=>o.id===scene.clip);assert(op);assert.equal(scene.seconds,op.seconds);}for(const cue of scene.cues)assert(cue.at>=0&&cue.at<scene.seconds);}
assert(sources.notices.some(n=>n.title.includes('当前宏观经济')));assert(sources.assignments.some(a=>a.title==='HW2_p1'));
assert(sources.scheduleConversation.find(m=>m.role==='assistant').changes[0].applied);
assert.equal(film.team,'AAA罗德岛工程部');
assert.equal(film.scenes.find(s=>s.id==='themes').seconds,operations.filter(o=>o.theme).reduce((n,o)=>n+o.seconds,0));
assert.deepEqual(film.members.map(m=>m.github),film.members.map(m=>m.github).toSorted((a,b)=>a.localeCompare(b,'en',{sensitivity:'base'})));
const agenda=await readFile(resolve(video,'public/screens/agenda.png'));assert(agenda.readUInt32BE(16)>1000);assert(agenda.readUInt32BE(20)>250);
let cursor=0;
const stamp=n=>{const seconds=Math.round(n*100)/100;return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${(seconds%60).toFixed(2).padStart(5,'0')}`;};
const rows=film.scenes.map(scene=>{const start=cursor;cursor+=scene.seconds;return `| ${stamp(start)}–${stamp(cursor)} | ${scene.title} | ${scene.subtitle} | ${scene.clip?'recordings/'+scene.clip+'.mp4':scene.id==='themes'?'PRTS / 观星台 / 星夜手记':scene.id==='group-sources'?'微信 / QQ 课程群聊天还原':'Remotion 图文动画'} |`;});
await writeFile(resolve(video,'production/storyboard.md'),'# campusMate · 视频大纲与分镜\n\n'+duration+' 秒，1920×1080，60 fps。默认 Nord 主线；功能介绍后集中展示 AI 协作，随后介绍手机网页、设置与个性主题，以团队制作名单收束。时间轴来自 `src/film.json`，操作来自 `src/operations.json`，局部取景来自 `src/framing.json`。\n\n| 时间 | 标题 | 信息 | 素材 |\n| --- | --- | --- | --- |\n'+rows.join('\n')+'\n');
const labels={move:'移动指针',click:'点击',navigate:'切换页面',close:'关闭弹窗',type:'逐字输入',scroll:'滚动至内容',scrollModal:'滚动弹窗',scrollInside:'滚动阅读区',scrollChat:'滚动回答',activity:'显示原生工具进度',stream:'重放流式回答',complete:'完成回答与回执',capture:'截取真实界面区域',notify:'更新资料并由后台组件弹出通知',focus:'镜头聚焦 / 回到全景',select:'选择选项'};
let script='# campusMate · 完整屏幕脚本\n\n声音：指定 OGG 背景音乐，按分镜时长衔接并首尾淡入淡出。真实前端、代码操作、原生 NDJSON 对话重放；章节以 2.4 秒的线条、下一功能标题与界面展开衔接；关键结果保留约 3 秒以上阅读时间。鼠标按 1 秒曲线移动，阅读时使用有明确目标的推近、高亮与回到全景。微信与 QQ 来源窗口为代码还原，课程群对话见 `group-chats.json`；学生档案、群聊身份和完成状态为演示数据。素材出处见 `sources.md`、`source-data.json`。\n';
cursor=0;
for(const scene of film.scenes){
  script+=`\n## ${stamp(cursor)} ${scene.title}\n\n${scene.subtitle}\n\n`;
  const op=operations.find(o=>o.id===scene.clip);
  script+=scene.cues.map(c=>`${stamp(cursor+c.at)}：${c.text}`).join('\n\n')+'\n';
  if(scene.id==='group-sources')script+='\n'+chats.map(chat=>chat.name+' · '+chat.title+'\n\n'+chat.messages.map(m=>m.time+' '+m.sender+'：'+m.text).join('\n\n')).join('\n\n')+'\n';
  if(op)script+='\n| 场内秒数 | 操作 | 目标 / 内容 |\n| --- | --- | --- |\n'+op.steps.map(s=>`| ${s.at.toFixed(2)} | ${labels[s.type]} | ${s.selector||s.route||s.name||(s.steps?s.steps.map(t=>t.label).join(' → '):'原生对话')} ${s.duration?'· '+s.duration.toFixed(2)+' 秒':''} |`).join('\n')+'\n';
  const answer=scene.id==='schedule'?sources.scheduleConversation.find(m=>m.role==='assistant'):dialogues[scene.id];
  if(answer){script+='\n对话输入：'+(scene.id==='schedule'?sources.scheduleConversation.find(m=>m.role==='user').text:answer.prompt)+'\n\n回答：\n\n'+answer.text+'\n';}
  cursor+=scene.seconds;
}
script+='\n制作：'+film.team+'\n\n'+film.members.map(m=>'@'+m.github+' '+m.name).join('\n\n')+'\n';
await writeFile(resolve(video,'production/screenplay.md'),script);
console.log(`PASS: ${film.scenes.length} scenes, ${duration}s, ${captures.length} native UI recordings, exact 60fps source clips, clean business API boundary, streaming events; scripts generated`);
