const {spawn}=require('node:child_process');
const {EventEmitter}=require('node:events');
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

class Backend extends EventEmitter {
  constructor({command,cwd,dataDir,preferredPort=16666,env=process.env,timeout=60000}){
    super();Object.assign(this,{command,cwd,dataDir,preferredPort,env,timeout});
    this.launchId=crypto.randomUUID().replaceAll('-','');this.stopping=false;
  }
  start(){return this.started??=this.launch().catch(async error=>{await this.stop();throw error;});}
  async launch(){
    const logs=path.join(this.dataDir,'runtime','logs');await fs.promises.mkdir(logs,{recursive:true});
    if(this.stopping)throw new Error('启动已取消。');
    const log=fs.createWriteStream(path.join(logs,'desktop-'+this.launchId+'.log'));
    const child=this.child=spawn(this.command[0],[...this.command.slice(1),'--port',String(this.preferredPort),'--launch-id',this.launchId],
      {cwd:this.cwd,env:{...this.env,CAMPUS_DATA_DIR:this.dataDir},windowsHide:true,stdio:['pipe','pipe','pipe']});
    this.closed=new Promise(resolve=>child.once('close',(code,signal)=>{this.hasClosed=true;log.end();resolve();this.emit('exit',{code,signal,expected:this.stopping});}));
    let buffered='',announcement,spawnError;
    child.on('error',error=>{spawnError=error;});
    child.stdin.on('error',()=>{});log.on('error',()=>{});
    child.stderr.on('data',part=>log.write(part));
    child.stdout.on('data',part=>{
      log.write(part);buffered+=part.toString('utf8');
      const lines=buffered.split('\n');buffered=lines.pop().slice(-8192);
      for(const line of lines)if(line.startsWith('CAMPUS_DESKTOP_READY ')){
        try{const value=JSON.parse(line.slice(21));if(value.launch_id===this.launchId&&Number.isInteger(value.port)&&value.port>0&&value.port<65536)announcement=value;}catch{}
      }
    });
    const deadline=Date.now()+this.timeout;
    while(Date.now()<deadline&&!this.stopping){
      if(spawnError)throw spawnError;
      if(this.hasClosed)throw new Error('本地服务启动失败，请查看运行日志。');
      if(announcement){
        const origin='http://127.0.0.1:'+announcement.port;
        try{
          const response=await fetch(origin+'/api/v1/health',{signal:AbortSignal.timeout(500),redirect:'error'});
          const health=await response.json();
          if(response.ok&&health.application==='campus-framework'&&health.launch_id===this.launchId){
            return this.info={origin,pid:child.pid,launchId:this.launchId};
          }
        }catch{}
      }
      await wait(40);
    }
    throw new Error(this.stopping?'启动已取消。':'本地服务未在限定时间内就绪。');
  }
  stop(){return this.stopped??=this.shutdown();}
  async shutdown(){
    this.stopping=true;
    if(!this.child||this.hasClosed)return;
    this.child.stdin.end('stop\n');
    // The Python worker owns a Windows job: forced exit also releases its descendants.
    let timer;
    await Promise.race([this.closed,new Promise(resolve=>{timer=setTimeout(resolve,15000);})]);clearTimeout(timer);
    if(!this.hasClosed){this.child.kill();await this.closed;}
  }
}
module.exports={Backend};
