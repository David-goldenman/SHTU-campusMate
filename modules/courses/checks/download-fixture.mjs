import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const writers = new Set();

// Match browser handles: create:true also opens existing names, and writes commit on close.
export function directoryAt(folder, {onWrite = async()=>{}} = {}) {
  const directory = {
    kind:'directory',name:path.basename(folder),path:folder,
    async queryPermission(){return 'granted';},
    async requestPermission(){return 'granted';},
    async isSameEntry(other){return other?.path === folder;},
    async *entries(){for(const entry of await fs.readdir(folder,{withFileTypes:true}))yield [entry.name,{kind:entry.isDirectory()?'directory':'file'}];},
    async getDirectoryHandle(name,options={}){
      assert.equal(path.basename(name),name);
      const target=path.join(folder,name);
      if(options.create)await fs.mkdir(target,{recursive:true});
      if(!(await fs.stat(target)).isDirectory())throw new DOMException('Not a directory','TypeMismatchError');
      return directoryAt(target,{onWrite});
    },
    async getFileHandle(name,options={}){
      assert.equal(path.basename(name),name);
      const target=path.join(folder,name);
      try{if((await fs.stat(target)).isDirectory())throw new DOMException('Directory','TypeMismatchError');}
      catch(error){
        if(error.code!=='ENOENT')throw error;
        if(!options.create)throw new DOMException('Missing','NotFoundError');
        try{await fs.writeFile(target,'',{flag:'wx'});}catch(error){if(error.code!=='EEXIST')throw error;}
      }
      return {
        async getFile(){const stat=await fs.stat(target);return Object.assign(new Blob([await fs.readFile(target)]),{name,lastModified:stat.mtimeMs});},
        async createWritable(options={}){
          if(options.mode==='exclusive'&&writers.has(target))throw new DOMException('Busy','NoModificationAllowedError');
          writers.add(target);let content;
          return {
            async write(blob){content=Buffer.from(await blob.arrayBuffer());await onWrite(target);},
            async close(){try{await fs.writeFile(target,content);}finally{writers.delete(target);}},
            async abort(){writers.delete(target);},
          };
        },
      };
    },
    async removeEntry(name){
      assert.equal(path.basename(name),name);const target=path.join(folder,name);
      if((await fs.stat(target)).isDirectory())await fs.rmdir(target);else await fs.unlink(target);
    },
  };
  return directory;
}

export function installLocks() {
  const tails=new Map();
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{locks:{
    async request(name,{signal,ifAvailable}={},callback){
      if(ifAvailable && signal)throw new DOMException('ifAvailable cannot be combined with signal','NotSupportedError');
      if(ifAvailable && tails.has(name))return callback(null);
      const previous=tails.get(name)||Promise.resolve();
      let release;
      const gate=new Promise(resolve=>{release=resolve;}),tail=previous.then(()=>gate);
      tails.set(name,tail);
      let abort;
      const aborted=new Promise((_,reject)=>{abort=()=>reject(signal.reason);signal?.addEventListener('abort',abort,{once:true});});
      try{
        signal?.throwIfAborted();await Promise.race([previous,aborted]);signal?.throwIfAborted();
        return await callback({name});
      }finally{
        signal?.removeEventListener('abort',abort);release();
        void tail.then(()=>{if(tails.get(name)===tail)tails.delete(name);});
      }
    },
  }}});
}

export function memoryStore(records, roots = new Map()) {
  return {
    roots:async()=>[...roots.values()],getRoot:async revision=>roots.get(revision),
    putRoot:async root=>roots.set(root.revision,root),removeRoot:async revision=>roots.delete(revision),
    updateRoot:async(revision,change)=>{const next=change(roots.get(revision));if(next)roots.set(revision,next);},
    all:async()=>[...records.values()],get:async key=>records.get(key),put:async record=>records.set(record.key,record),
    remove:async key=>records.delete(key),
    update:async(key,change)=>{const next=change(records.get(key));if(next)records.set(key,next);},
  };
}
