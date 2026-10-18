import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

// Only synthetic WebAudio nodes are instantiated: this check never plays real audio.
const source=await readFile(new URL('../web/sounds.js',import.meta.url),'utf8');
let loads=0;
const load=()=>import('data:text/javascript;base64,'+Buffer.from(source+'\n// scenario '+loads++).toString('base64'));
const contexts=[];
class Node {
  constructor(){this.connections=[];this.disconnected=false;this.gain={value:0,setValueAtTime(){},linearRampToValueAtTime(){},exponentialRampToValueAtTime(){}};this.frequency={value:0};}
  connect(node){this.connections.push(node);}
  disconnect(){this.disconnected=true;this.connections=[];}
  start(at){this.startAt=at;}
  stop(at){this.stopAt=at;}
  finish(){this.onended?.();}
}
class Audio {
  constructor(){this.state='suspended';this.currentTime=0;this.destination={};this.nodes=[];this.oscillators=[];this.resumes=0;contexts.push(this);}
  createGain(){const node=new Node();this.nodes.push(node);return node;}
  createOscillator(){const node=new Node();this.nodes.push(node);this.oscillators.push(node);return node;}
  async resume(){this.resumes++;this.state='running';}
  async close(){this.state='closed';}
}
globalThis.localStorage={getItem(){throw new Error('Synthetic storage denial');},setItem(){throw new Error('Synthetic storage denial');}};
globalThis.window={AudioContext:Audio};
const ui=await load();
assert.equal(ui.isEnabled(),true,'blocked storage must not break application import');
ui.playSound('mail');assert.equal(contexts.length,0,'background cues must not create or unlock audio');
ui.setEnabled(false);assert.equal(await ui.unlock(),false);assert.equal(contexts.length,0,'disabled sounds need no audio context');
ui.setEnabled(true);assert.equal(await ui.unlock(),true);
const audio=contexts.at(-1);
ui.playSound('mail');assert.equal(audio.oscillators.length,2);
for(const voice of audio.oscillators){const gain=voice.connections[0];voice.finish();assert.equal(voice.disconnected,true);assert.equal(gain.disconnected,true,'completed note gains must disconnect');}
ui.playSound('assistant');const active=audio.oscillators.slice(-2);ui.setEnabled(false);
assert.ok(active.every(node=>node.disconnected),'turning sounds off must stop and disconnect scheduled notes');
const count=audio.oscillators.length;ui.playSound('mail');assert.equal(audio.oscillators.length,count);
ui.setEnabled(true);audio.state='suspended';const resumes=audio.resumes;
ui.playSound('mail');assert.equal(audio.oscillators.length,count);assert.equal(audio.resumes,resumes,'background events must not resume a suspended context');
audio.resume=async()=>{throw new Error('Synthetic policy denial');};
assert.equal(await ui.unlock(),false);ui.playSound('mail');assert.equal(audio.oscillators.length,count);
audio.resume=async()=>{audio.state='running';};assert.equal(await ui.unlock(),true);
ui.playSound('constructor');assert.equal(audio.oscillators.length,count+1,'unknown names use the default cue without inherited-property errors');
ui.setEnabled(false);
window.AudioContext=undefined;const unsupported=await load();assert.equal(await unsupported.unlock(),false);assert.doesNotThrow(()=>unsupported.playSound('mail'));
window.AudioContext=class{constructor(){throw new Error('Synthetic unsupported audio');}};const denied=await load();assert.equal(await denied.unlock(),false);assert.doesNotThrow(()=>denied.playSound());

// Cancel during the deferred optional import: no detached UI, API calls or timers may start.
for(const filename of ['modules/assistant/web/index.js','modules/campus-agent/web/background.js']){
  let text=await readFile(new URL('../'+filename,import.meta.url),'utf8');
  assert.match(text,/import\('\/assets\/sounds\.js'\)/);
  text=text.replace(/^import .*;$/gm,'').replaceAll("new URL('./styles.css',import.meta.url)","'synthetic-style'").replace("import('/assets/sounds.js')",'globalThis.__pendingSoundImport');
  let resolve;globalThis.__pendingSoundImport=new Promise(done=>{resolve=done;});
  const module=await import('data:text/javascript;base64,'+Buffer.from(text+'\n// '+loads++).toString('base64'));
  let styleRemovals=0,writes=0,calls=0;
  const container={classList:{add(){writes++;}},replaceChildren(){},set innerHTML(value){writes++;}};
  const controller=new AbortController();
  const mounting=module.mount(container,{signal:controller.signal,ui:{escape:String,useStyle:()=>()=>{styleRemovals++;}},api:()=>{calls++;throw new Error('No API after abort');}});
  controller.abort();resolve(null);const cleanup=await mounting;
  assert.ok(styleRemovals>0,'cleanup must already be registered during import');assert.equal(writes,0,'aborted imports must not mount UI');assert.equal(calls,0);assert.equal(typeof cleanup,'function');cleanup();
}
console.log('Sounds: denied storage, user-gesture gating, opt-out, unsupported audio, node cleanup and aborted module imports passed');
