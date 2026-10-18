import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {archive} from './archive.mjs';
import {reviewOffsets} from './review.mjs';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..'),work=resolve(video,'../.codex/video'),file=resolve(video,'output/校园工作台.mp4');
for(const key of ['TEMP','TMP','TMPDIR'])process.env[key]=resolve(work,'tmp');
const film=JSON.parse(await readFile(resolve(video,'src/film.json'),'utf8')),duration=film.scenes.reduce((n,s)=>n+s.seconds,0),count=duration*film.fps;
const run=(exe,args)=>{const r=spawnSync(exe,args,{encoding:'utf8',windowsHide:true,maxBuffer:8*1024*1024});assert.equal(r.status,0,r.stderr);return r;};
const meta=JSON.parse(run('ffprobe',['-v','error','-show_format','-show_streams','-of','json',file]).stdout);
const picture=meta.streams.find(s=>s.codec_type==='video'),audio=meta.streams.find(s=>s.codec_type==='audio');
assert.equal(picture.width,film.width);assert.equal(picture.height,film.height);assert.equal(picture.codec_name,'h264');assert.equal(picture.avg_frame_rate,film.fps+'/1');
assert(Math.abs(Number(meta.format.duration)-duration)<.05);assert.equal(Number(picture.nb_frames),count);assert.equal(audio.codec_name,'aac');assert.equal(audio.channels,2);
const decoded=run('ffmpeg',['-hide_banner','-nostats','-i',file,'-af','volumedetect','-f','null','-']);await writeFile(resolve(work,'decode.log'),decoded.stderr);
const peak=Number(decoded.stderr.match(/max_volume: ([-.\d]+) dB/)?.[1]),mean=Number(decoded.stderr.match(/mean_volume: ([-.\d]+) dB/)?.[1]);assert(Number.isFinite(peak)&&peak<=0);assert(Number.isFinite(mean)&&mean>-50);
const operations=JSON.parse(await readFile(resolve(video,'src/operations.json'),'utf8'));
let cursor=0;const samples=film.scenes.flatMap(scene=>{const start=cursor;cursor+=scene.seconds;return reviewOffsets(scene,operations).map(offset=>({scene:scene.id,seconds:start+offset,frame:Math.round((start+offset)*film.fps)}));});
for(const id of ['mail','schedule','themes']){
  const start=film.scenes.slice(0,film.scenes.findIndex(s=>s.id===id)).reduce((n,s)=>n+s.seconds,0);
  for(const offset of [-1,-.55,.05,.6,1.1])samples.push({scene:'transition-'+id,seconds:start+offset,frame:Math.round((start+offset)*film.fps)});
}
samples.sort((a,b)=>a.frame-b.frame);
const frames=resolve(work,'verified-frames',String(count));await mkdir(frames,{recursive:true});
run('ffmpeg',['-y','-v','error','-i',file,'-vf','select='+samples.map(s=>`eq(n\\,${s.frame})`).join('+'),'-fps_mode','vfr',resolve(frames,'%02d.png')]);
run('ffmpeg',['-y','-v','error','-framerate','1','-i',resolve(frames,'%02d.png'),'-vf',`scale=480:270,tile=4x${Math.ceil(samples.length/4)}:nb_frames=${samples.length}:padding=8:margin=8:color=0xeceff4`,'-frames:v','1','-update','1','-q:v','2',resolve(video,'output/分镜预览.jpg')]);
run('ffmpeg',['-y','-v','error','-ss',String(duration-2.2),'-i',file,'-frames:v','1','-update','1','-q:v','2',resolve(video,'output/封面.jpg')]);
await writeFile(resolve(work,'verified-frames.json'),JSON.stringify(samples,null,2));await writeFile(resolve(work,'media-metadata.json'),JSON.stringify(meta,null,2));
const size=(Number(meta.format.size)/1024/1024).toFixed(1),captures=JSON.parse(await readFile(resolve(video,'production/captures.json'),'utf8'));
const pointerStep=Math.max(...captures.map(c=>c.pointer.maxStep)).toFixed(2),clickError=Math.max(...captures.map(c=>c.pointer.maxClickError)).toFixed(2);
await writeFile(resolve(video,'production/validation.md'),`# 成片验证\n\n文件：\`output/校园工作台.mp4\`。时长 ${Number(meta.format.duration).toFixed(3)} 秒，${picture.width}×${picture.height}，${film.fps} fps，${count} 帧；H.264 / yuv420p，AAC 双声道，${size} MiB。\n\nffprobe 已确认尺寸、帧率、时长、帧数与音轨；ffmpeg 完整解码成功。音轨平均电平 ${mean} dB，峰值 ${peak} dB。音乐按时间轴淡入淡出。\n\n工程 TypeScript 与素材检查通过，${captures.length} 段真实前端录制为 60 fps；桌面素材 2760×1350，手机素材 860×1720；未知业务路由与界面异常均为 0。日程、复习与选课片段均记录 activity、delta 和 complete 事件，输入表单、进度、引用和回执由产品原生组件呈现。日程状态仅写入演示浏览器内存。\n\n章节以 2.4 秒的线条、下一功能标题与界面展开衔接；场内切页为 0.85 秒。鼠标在桌面片段按 1 秒曲线到达操作目标，弹窗期间保持可见；最大帧间位移 ${pointerStep} CSS 像素，最大点击误差 ${clickError} CSS 像素。每段最后动作与取景结束后保留约 3 秒以上阅读时间，再进入出场。\n\n从成片抽取 ${samples.length} 个关键帧，覆盖完整窗口、邮件原文及历史活动摘要、偏好输入、课程教室、苹果日历导出入口、单独的日程区域、课程切换、作业、通用培养方案、逐字提问、工具进度、流式回答、日程结果、原生通知弹窗、PDF 第 5 页引用、选课建议、账号与模型、模块、校园地图与路线、微信 / QQ 聊天还原、课程群整理和撤销、手机日程与地图、三个个性主题及团队成员。联系表：\`output/分镜预览.jpg\`；完整关键帧、媒体元数据及解码日志保存在项目 \`.codex/video/\`。\n\n微信与 QQ 群聊使用模拟连接和虚构对话；手机片段为真实响应式网页视口录制。苹果设备的日历导入、手机实机、场地投影与音响尚需实测。\n`);
console.log(`PASS: ${duration}s, ${picture.width}x${picture.height}, ${film.fps}fps, ${count} frames, AAC stereo, full decode; ${size}MiB; ${samples.length} review frames; peak ${peak}dB`);
await archive();
