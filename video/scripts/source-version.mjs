import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../..');
const isInterface=path=>/^(web\/|modules\/[^/]+\/web\/|modules\/campus-map\/data\/)/.test(path);
export function changedInterfacePaths(commit){
  return execFileSync('git',['diff','--name-only',commit,'--','web','modules'],{cwd:root,encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/).filter(isInterface);
}
export function affectedInterfacePaths(capture,operation){
  const backgrounds=execFileSync('git',['ls-files','modules/*/web/background.js'],{cwd:root,encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/).filter(Boolean).map(path=>path.split('/')[1]);
  const modules=new Set([...operation.modules,...backgrounds]);
  return changedInterfacePaths(capture.version.commit).filter(path=>path.startsWith('web/')||modules.has(path.split('/')[1]));
}
export async function sourceVersion(){
  const files=execFileSync('git',['ls-files','web','modules'],{cwd:root,encoding:'utf8',windowsHide:true}).trim().split(/\r?\n/).filter(isInterface);
  const hash=createHash('sha256');
  for(const file of files){hash.update(file);hash.update(await readFile(resolve(root,file)));}
  return {commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',windowsHide:true}).trim(),sha256:hash.digest('hex')};
}
