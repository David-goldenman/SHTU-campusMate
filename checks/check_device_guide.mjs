import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../scripts/ids-device-guide.js', import.meta.url), 'utf8');
let tick, clicked = 0;
const storage = new Map();
const button = {textContent:'绑定当前设备', disabled:false, getClientRects:()=>[{}], click:()=>clicked++};
const context = {
  location:{origin:'https://ids.shanghaitech.edu.cn',pathname:'/personalInfo/personCenter/index.html',hash:'#/accountsecurity'},
  Date, setInterval:callback=>(tick=callback,1),clearInterval:()=>{},
  sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
  document:{querySelectorAll:selector=>selector === 'button' ? [button] : []},
};
vm.runInNewContext(source, context);
tick(); tick();
assert.equal(clicked,1,'Guide must open school recheck at most once');
storage.clear(); tick=undefined;
vm.runInNewContext(source,{...context,location:{...context.location,origin:'https://unrelated.example'}});
assert.equal(tick,undefined,'Guide must not run outside school IDS');
console.log('device guide: exact school origin, account-security route and a single recheck action passed');
