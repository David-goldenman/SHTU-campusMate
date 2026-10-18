import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';

export async function encode(folder,output,seconds,fps=60){
  const samples=JSON.parse(await readFile(resolve(folder,'samples.json'),'utf8'));
  const encoder=spawn('ffmpeg',['-y','-v','error','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','pipe:0','-frames:v',String(Math.round(seconds*fps)),'-an','-c:v','libx264','-crf','10','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',output],{windowsHide:true,stdio:['pipe','ignore','pipe']});
  let errors='';encoder.stderr.on('data',d=>errors+=d);
  const finished=new Promise((ok,no)=>{encoder.on('error',no);encoder.on('close',code=>code===0?ok():no(new Error(errors)));});
  async function* frames(){for(const [i,sample] of samples.entries()){const png=await readFile(resolve(folder,sample.name)),end=samples[i+1]?.frame??Math.round(seconds*fps);assert(end>sample.frame);for(let n=sample.frame;n<end;n++)yield png;}}
  await Promise.all([pipeline(Readable.from(frames()),encoder.stdin),finished]);
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
  const video=resolve(dirname(fileURLToPath(import.meta.url)),'..'),work=resolve(video,'../.codex/video');
  for(const key of ['TEMP','TMP','TMPDIR'])process.env[key]=resolve(work,'tmp');
  const definitions=JSON.parse(await readFile(resolve(video,'src/operations.json'),'utf8')),selected=process.argv.slice(2);
  for(const d of definitions.filter(d=>!selected.length||selected.includes(d.id))){await encode(resolve(work,'recordings',d.id),resolve(video,'public/recordings',d.id+'.mp4'),d.seconds);console.log('Encoded '+d.id+' / '+Math.round(d.seconds*60)+' frames');}
}
