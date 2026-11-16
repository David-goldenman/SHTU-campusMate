const path=require('node:path').win32;
const fs=require('node:fs');

function physicalPath(value){
  if(process.platform!=='win32')return value;
  let current=path.resolve(value),resolved;
  const missing=[];
  while(true){
    try{
      if(fs.lstatSync(current).isSymbolicLink())throw new Error('程序和资料路径不能包含链接或联接目录，请选择独立的普通目录。');
      resolved ||= path.join(fs.realpathSync.native(current),...missing);
    }catch(error){if(error.code!=='ENOENT')throw error;}
    const parent=path.dirname(current);
    if(parent===current)break;
    missing.unshift(path.basename(current));current=parent;
  }
  return resolved || path.resolve(value);
}

function assertSeparateStorage(program,data){
  const inside=(parent,child)=>{const relative=path.relative(parent,child);return !relative||(!relative.startsWith('..\\')&&relative!=='..'&&!path.isAbsolute(relative));};
  if(!path.isAbsolute(program)||!path.isAbsolute(data))throw new Error('资料目录必须与程序目录分开，请选择独立的绝对路径。');
  program=physicalPath(program);data=physicalPath(data);
  if(inside(program,data)||inside(data,program))throw new Error('资料目录必须与程序目录分开，请选择独立的绝对路径。');
}
module.exports={assertSeparateStorage};
