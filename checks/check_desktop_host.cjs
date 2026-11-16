const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),path=require('node:path'),net=require('node:net');
const {Backend}=require('../desktop/host.cjs');
const {assertSeparateStorage}=require('../desktop/storage.cjs');
assert.throws(()=>assertSeparateStorage('C:\\Example\\Program','C:\\Example\\Program\\data'),/分开/);
assert.throws(()=>assertSeparateStorage('C:\\Example\\Program','C:\\Example'),/分开/);
assertSeparateStorage('C:\\Example\\Program','C:\\Example\\User data');
(async()=>{
 const root=await fs.mkdtemp(path.join(__dirname,'../.codex/tmp/desktop 中文 '));
 const fake=path.join(root,'fake.cjs');
 await fs.writeFile(fake,`const http=require('node:http');
const args=process.argv;const id=args[args.indexOf('--launch-id')+1];
const server=http.createServer((req,res)=>{res.setHeader('content-type','application/json');res.end(JSON.stringify({application:'campus-framework',launch_id:process.env.WRONG_ID?'wrong':id}));});
server.on('error',error=>{if(error.code==='EADDRINUSE')server.listen(0,'127.0.0.1');else throw error;});
server.listen(Number(args[args.indexOf('--port')+1]),'127.0.0.1',()=>console.log('CAMPUS_DESKTOP_READY '+JSON.stringify({port:server.address().port,launch_id:id})));
process.stdin.on('data',()=>server.close(()=>process.exit(0)));process.stdin.on('end',()=>server.close(()=>process.exit(0)));`);
 const occupied=net.createServer();await new Promise(resolve=>occupied.listen(0,'127.0.0.1',resolve));
 const options={command:[process.execPath,fake],cwd:root,dataDir:root,preferredPort:occupied.address().port,timeout:3000};
 try{
  if(process.platform==='win32') {
   const program=path.join(root,'program'),data=path.join(root,'user data'),alias=path.join(root,'alias');
   await fs.mkdir(program);await fs.mkdir(data);
   assertSeparateStorage(program,path.join(data,'not yet created','profile'));
   await fs.symlink(program,alias,'junction');
   try {
    assert.throws(()=>assertSeparateStorage(program,path.join(alias,'user data','profile')),/链接|分开/,'An ancestor junction must not hide data inside the program tree');
    assert.throws(()=>assertSeparateStorage(alias,data),/链接|分开/,'Program ancestry must be validated too');
    assert.equal(await fs.stat(path.join(program,'user data')).then(()=>true,()=>false),false,'Rejected paths cannot create profile directories');
   } finally {await fs.unlink(alias);}
  }
  const backend=new Backend(options);
  const [first,second]=await Promise.all([backend.start(),backend.start()]);
  assert.equal(first.pid,second.pid,'Repeated starts share one owned process');
  assert.notEqual(new URL(first.origin).port,String(occupied.address().port));
  assert.equal((await(await fetch(first.origin+'/api/v1/health')).json()).launch_id,first.launchId);
  await backend.stop();await backend.stop();
  await assert.rejects(fetch(first.origin+'/api/v1/health'));
  const wrong=new Backend({...options,env:{...process.env,WRONG_ID:'1'},timeout:400});
  await assert.rejects(wrong.start(),/就绪/);await wrong.stop();
  const missing=new Backend({...options,command:[path.join(root,'missing.exe')]});
  await assert.rejects(missing.start());await missing.stop();
  console.log('desktop host: one owned backend, occupied port fallback, readiness identity, graceful exit and startup failure cleanup passed');
 }finally{await new Promise(resolve=>occupied.close(resolve));await fs.rm(root,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1});
