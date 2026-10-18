import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {copyFile,readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const video=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export async function archive(){
  const file=resolve(video,'output/校园工作台.mp4'),folder=resolve(video,'versions');
  await mkdir(folder,{recursive:true});
  let versions=[];
  try{versions=JSON.parse(await readFile(resolve(folder,'index.json'),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
  const bytes=await readFile(file),hash=createHash('sha256').update(bytes).digest('hex');
  let item=versions.find(v=>v.sha256===hash);
  if(!item){
    const number=versions.length+1,name=String(number).padStart(2,'0')+'-校园工作台.mp4';
    await copyFile(file,resolve(folder,name),1);
    assert.equal(createHash('sha256').update(await readFile(resolve(folder,name))).digest('hex'),hash);
    item={number,file:name,sha256:hash,bytes:bytes.length,created_at:(await stat(file)).mtime.toISOString()};
    versions.push(item);await writeFile(resolve(folder,'index.json'),JSON.stringify(versions,null,2)+'\n');
  }
  const player=resolve(video,'player.html'),html=await readFile(player,'utf8');
  const options='<option value="output/校园工作台.mp4">最新成片</option>'+versions.map(v=>`<option value="versions/${v.file}">第 ${v.number} 版</option>`).join('');
  await writeFile(player,html.replace(/<select id="version"[^>]*>[\s\S]*?<\/select>/,`<select id="version" aria-label="选择视频版本">${options}</select>`));
  console.log(`Archived version ${item.number} / ${item.file}`);
  return item;
}
if(process.argv[1]===fileURLToPath(import.meta.url))await archive();
