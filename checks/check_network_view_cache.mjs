import assert from 'node:assert/strict';
import {sourcePanel} from '../web/campus.js';
import {api,moduleApi,setToken} from '../web/shared.js';
import {invalidateViews,readView} from '../web/view-cache.js';

class Element extends EventTarget {
  constructor(){super();this.dataset={};this.innerHTML='';this.textContent='';this.disabled=false;}
  querySelector(){return null;}
  replaceChildren(){this.innerHTML='';this.textContent='';}
}
function container() {
  const elements=Object.fromEntries(['[data-sync]','[data-network]','[data-connect]','.source-state','[data-status]','[data-updated]','[data-issues]','[data-content]'].map(key=>[key,new Element()]));
  const root=new Element();root.querySelector=key=>elements[key];return {root,elements};
}
const deferred=()=>{let resolve;const promise=new Promise(yes=>{resolve=yes;});return {promise,resolve};};
const turn=()=>new Promise(resolve=>setImmediate(resolve));
const snapshot={account_revision:'same-account',status:'partial',updated_at:'2026-10-29T00:00:00Z',network_failure:{id:'network-failure',target:'elrc',kind:'timeout',at:'2026-10-29T00:00:00Z'},data:{issues:['Synthetic source unavailable'],text:'Existing course material'}};
const original={fetch:globalThis.fetch,location:globalThis.location};
globalThis.location={origin:'http://fixture.invalid'};
try {
  for (const [status,diagnosisFirst] of [[200,true],[503,true],[200,false],[503,false]]) {
    invalidateViews();
    const life=new AbortController(),view=container(),diagnosis=deferred(),fresh=deferred();
    let seeded=false,diagnosticPosts=0;
    globalThis.fetch=async(url,options)=>{
      const pathname=new URL(url).pathname;
      if(pathname.endsWith('/view-state'))return Response.json({account_revision:'same-account'});
      if(pathname==='/api/v1/auth/network/explain') {
        assert.equal(options.method,'POST');diagnosticPosts++;await diagnosis.promise;
        return Response.json(status===200?{reports:[]}:{detail:'Synthetic diagnostic unavailable'},{status});
      }
      if(pathname.endsWith('/snapshot')) {if(seeded)await fresh.promise;return Response.json(snapshot);}
      throw new Error('Unexpected fixture request '+pathname);
    };
    const context={module:{id:'synthetic-network-panel',frontend_url:'/synthetic'},signal:life.signal,ui:{toast(){}},
      api:moduleApi('synthetic-network-panel',life.signal),services:{auth:{explainNetwork:failures=>api('/auth/network/explain',{method:'POST',body:{failures},signal:life.signal})}}};
    try {
      await readView(context,'/snapshot');seeded=true;
      let failure,dispose;
      const mounting=sourcePanel(view.root,context,(body,value)=>{body.textContent=value.data.text;},{cache:true})
        .then(value=>{dispose=value;},error=>{failure=error;});
      await turn();
      assert.equal(view.elements['[data-content]'].textContent,'Existing course material','The verified preview paints while diagnostics and refresh are pending');
      assert.equal(diagnosticPosts,1);
      if(diagnosisFirst){diagnosis.resolve();await turn();}
      fresh.resolve();await mounting;
      if(!diagnosisFirst){diagnosis.resolve();await turn();}
      assert.equal(failure,undefined,'Read-only diagnostics must not turn a successful same-account refresh into a conflict');
      assert.equal(view.elements['[data-content]'].textContent,'Existing course material');
      assert.equal(view.elements['[data-status]'].textContent,'部分数据可用');
      let previewed=false;
      await readView(context,'/snapshot',()=>{previewed=true;});
      assert.equal(previewed,true,'Diagnostic completion, including failure, must leave the valid view cache available');
      if(status===503)assert.match(view.elements['[data-network]'].innerHTML,/Synthetic diagnostic unavailable/);
      dispose();
    } finally {diagnosis.resolve();fresh.resolve();life.abort();}
  }

  // The exception must not weaken write or account-change invalidation.
  for(const change of [()=>api('/modules/synthetic/sync',{method:'POST'}),
    ()=>api('/auth/network/explain',{method:'DELETE'}),()=>setToken('changed-framework-token')]) {
    invalidateViews();
    const fresh=deferred(),life=new AbortController();
    globalThis.fetch=async url=>new URL(url).pathname.endsWith('/snapshot') ? (await fresh.promise,Response.json(snapshot)) : Response.json({ok:true});
    const pending=readView({module:{id:'synthetic'},signal:life.signal,api:moduleApi('synthetic',life.signal)},'/snapshot');
    const rejected=assert.rejects(pending,error=>error.status===409,'A write or changed token must still reject an old in-flight read');
    await change();fresh.resolve();await rejected;life.abort();
  }
} finally {
  setToken('');invalidateViews();
  for(const [key,value] of Object.entries(original)) {if(value===undefined)delete globalThis[key];else globalThis[key]=value;}
}
console.log('network/cache integration: diagnostic success/failure before/after refresh, retained content/cache, real mutations and token changes passed');
