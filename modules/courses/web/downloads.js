const extensions = {'application/pdf':'.pdf','application/zip':'.zip','text/plain':'.txt',
  'application/vnd.ms-powerpoint':'.ppt','application/vnd.openxmlformats-officedocument.presentationml.presentation':'.pptx',
  'application/msword':'.doc','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx',
  'image/png':'.png','image/jpeg':'.jpg'};

export function safeName(value) {
  let name = (value || '课程资料').normalize('NFC').replace(/[<>:"/\\|?*\u0000-\u001f\u007f]/g,'_').replace(/[. ]+$/g,'').trim();
  if (!name || /^\.+$/.test(name)) name = '课程资料';
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) name = '_' + name;
  const dot = name.lastIndexOf('.');
  return dot > 0 ? name.slice(0,dot).slice(0,140) + name.slice(dot, dot+12) : name.slice(0,140);
}

export function fileName(response, title) {
  const disposition = response.headers.get('content-disposition') || '';
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  const plain = /filename="([^"]+)"|filename=([^;]+)/i.exec(disposition);
  let name = title || '课程资料';
  try { name = encoded ? decodeURIComponent(encoded[1]) : plain ? plain[1] || plain[2] : name; } catch { /* Use the catalog title. */ }
  name = safeName(name);
  if (!/\.[a-z0-9]{1,10}$/i.test(name)) name += extensions[response.headers.get('content-type')?.split(';')[0]] || '.bin';
  return name;
}

export const resourceVersion = item => JSON.stringify([item.updated_at || item.created_at || '',item.title]);

export function courseFiles(snapshot, course) {
  const members = new Set(course.course_ids || course.sources.map(item=>item.id));
  return (snapshot.data?.materials || []).filter(item=>item.source === 'piazza' && members.has(item.course_id)
    && item.resource_type === 'file' && item.download_url);
}

export async function readResponse(response) {
  if (response.ok) return response;
  let message = '文件下载失败（HTTP ' + response.status + '）';
  try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch { /* Ignore non-JSON error pages. */ }
  const error = new Error(message); error.status = response.status; throw error;
}

async function localFile(directory,name) {
  try { const handle = await directory.getFileHandle(name); return {handle,file:await handle.getFile()}; }
  catch(error) { if (error.name === 'NotFoundError' || error.name === 'TypeMismatchError') return null; throw error; }
}

async function unusedName(directory, wanted, id) {
  const occupied = new Set();
  for await (const [name] of directory.entries()) occupied.add(name.toLowerCase());
  const dot = wanted.lastIndexOf('.'), stem = wanted.slice(0,dot), extension = wanted.slice(dot);
  const distinct = `${stem.slice(0,110)} · ${safeName(id).slice(-16)}`;
  let name = wanted, number = 2;
  if (occupied.has(name.toLowerCase())) name = distinct + extension;
  while (occupied.has(name.toLowerCase())) name = `${distinct} (${number++})${extension}`;
  return name;
}

const contentDigest = async blob => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),byte=>byte.toString(16).padStart(2,'0')).join('');
async function unchanged(local,record) {
  return local && record?.managed && local.file.size === record.size && local.file.lastModified === record.lastModified
    && (!record.digest || await contentDigest(local.file) === record.digest);
}
const sameFile = (first, second) => first && second && first.file.size === second.file.size && first.file.lastModified === second.file.lastModified;
const preserveError = () => Object.assign(new Error('检测到本地修改，已保留原文件并暂停此资料的自动更新。'),{preserve:true});

/** Skip known versions before HTTP; replace only files we saved that remain unedited. */
export async function downloadFiles({items, directory, legacyDirectory, revision, files = {}, signal, checkActive = async()=>{}, onRecord = async()=>{}, onProgress = ()=>{}, request = fetch}) {
  const manifest = {...files};
  const result = {saved:[], skipped:[], preserved:[], failed:[], remaining:[], cancelled:false};
  for (let index = 0; index < items.length; index++) {
    const item = items[index], version = resourceVersion(item);
    if (signal.aborted) { result.cancelled = true; result.remaining = items.slice(index); break; }
    onProgress({...result, current:item.title, done:index, total:items.length});
    let writer, name, createdFile, committed = false;
    try {
      await checkActive();
      const path = '/api/v1/modules/piazza/file?';
      if (!item.download_url.startsWith(path)) throw new Error('课件下载地址无效，请重新同步。');
      const params = new URLSearchParams(item.download_url.slice(path.length));
      if (params.get('material_id') !== item.id) throw new Error('课件标识不匹配，请重新同步。');
      const record = manifest[item.id], originalDirectory = record?.directory || (record?.legacy ? legacyDirectory : directory);
      let local = record ? await localFile(originalDirectory,record.name) : null;
      if (local && !await unchanged(local,record)) throw preserveError();
      if (record?.version === version && local && !record.legacy) {
        result.skipped.push({id:item.id,name:record.name}); continue;
      }
      let blob, wanted = record?.name;
      if (record?.legacy && local && record.version === version) blob = local.file;
      else {
        await checkActive();
        params.set('account_revision',revision);
        const response = await readResponse(await request(path+params,{signal:AbortSignal.any([signal,AbortSignal.timeout(120000)]),credentials:'same-origin',redirect:'error'}));
        if (/^(text\/html|application\/(json|xhtml\+xml))\b/i.test(response.headers.get('content-type') || '')) throw new Error('来源返回了登录页或错误内容，请重新连接 Piazza。');
        blob = await response.blob(); wanted ||= fileName(response,item.title);
      }
      if (!blob.size) throw new Error('来源返回了空文件。');
      await checkActive();
      signal.throwIfAborted();
      const digest = await contentDigest(blob);
      local = record ? await localFile(originalDirectory,record.name) : null;
      if (local && !await unchanged(local,record)) throw preserveError();
      const replace = local && !record.legacy;
      name = replace ? record.name : await unusedName(directory,wanted,item.id);
      signal.throwIfAborted();
      const handle = replace ? local.handle : await directory.getFileHandle(name,{create:true});
      const before = await handle.getFile();
      if (!replace && before.size) throw new Error('同名文件刚被创建，已保留，请再次检查。');
      writer = await handle.createWritable({mode:'exclusive'});
      if (!replace) createdFile = before;
      await writer.write(blob);
      signal.throwIfAborted();
      if (record && local && !await unchanged(await localFile(originalDirectory,record.name),record)) throw preserveError();
      if (!sameFile({file:before},{file:await handle.getFile()})) throw preserveError();
      await checkActive();
      signal.throwIfAborted();
      await writer.close(); writer = null; committed = true;
      const saved = await handle.getFile();
      const next = {name,version,size:saved.size,lastModified:saved.lastModified,managed:true,digest};
      await onRecord(item.id,next); manifest[item.id] = next;
      // Move only our unchanged legacy file, after the new file and manifest are safe.
      if (record?.legacy && local) {
        const latest = await localFile(originalDirectory,record.name);
        if (sameFile(local,latest) && await unchanged(latest,record)) await originalDirectory.removeEntry(record.name);
        else result.preserved.push({id:item.id,name:record.name,message:'旧目录中的文件刚被修改，已保留。'});
      }
      result.saved.push({id:item.id,name});
    } catch (error) {
      if (writer) { try { await writer.abort(); } catch { /* Already closed. */ } }
      if (createdFile && !committed) {
        try { const current = await localFile(directory,name); if (current?.file.size === 0 && current.file.lastModified === createdFile.lastModified) await directory.removeEntry(name); }
        catch { /* Leave externally changed files in place. */ }
      }
      if (signal.aborted) { result.cancelled = true; result.remaining = items.slice(index); break; }
      if (error.preserve) { result.preserved.push({id:item.id,name:manifest[item.id]?.name,message:error.message}); continue; }
      result.failed.push({item,message:error.message});
      if ([401,403,409].includes(error.status) || error.name === 'NotAllowedError') {
        result.remaining = items.slice(index+1); break;
      }
    }
  }
  onProgress({...result,current:'',done:items.length-result.remaining.length,total:items.length});
  return result;
}
