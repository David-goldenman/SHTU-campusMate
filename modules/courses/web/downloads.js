const extensions = {'application/pdf':'.pdf','application/zip':'.zip','text/plain':'.txt',
  'application/vnd.ms-powerpoint':'.ppt','application/vnd.openxmlformats-officedocument.presentationml.presentation':'.pptx',
  'application/msword':'.doc','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx',
  'image/png':'.png','image/jpeg':'.jpg'};

function safeName(value) {
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

async function unusedName(directory, wanted) {
  const occupied = new Set();
  for await (const [name] of directory.entries()) occupied.add(name.toLowerCase());
  const dot = wanted.lastIndexOf('.'), stem = wanted.slice(0,dot), extension = wanted.slice(dot);
  let name = wanted, number = 2;
  while (occupied.has(name.toLowerCase())) name = `${stem} (${number++})${extension}`;
  return name;
}

async function existingName(directory,item,files) {
  const wanted = safeName(item.title).toLowerCase(), candidates = [];
  const claimed = new Set(Object.values(files).map(record=>record.name.toLowerCase()));
  for await (const [name,handle] of directory.entries()) {
    const lower = name.toLowerCase();
    if (handle.kind !== 'file' || claimed.has(lower)) continue;
    if (lower === wanted || (!/\.[a-z0-9]{1,10}$/i.test(wanted) && lower.replace(/\.[^.]+$/,'') === wanted)) candidates.push(name);
  }
  return candidates.length === 1 ? candidates[0] : null;
}

/** Skip known versions before HTTP; replace only files we saved that remain unedited. */
export async function downloadFiles({items, directory, revision, files = {}, signal, onRecord = async()=>{}, onProgress = ()=>{}, request = fetch}) {
  const manifest = {...files};
  const result = {saved:[], skipped:[], failed:[], remaining:[], cancelled:false};
  for (let index = 0; index < items.length; index++) {
    const item = items[index], version = resourceVersion(item);
    if (signal.aborted) { result.cancelled = true; result.remaining = items.slice(index); break; }
    onProgress({...result, current:item.title, done:index, total:items.length});
    let writer, name, created = false, committed = false;
    try {
      const path = '/api/v1/modules/piazza/file?';
      if (!item.download_url.startsWith(path)) throw new Error('课件下载地址无效，请重新同步。');
      const params = new URLSearchParams(item.download_url.slice(path.length));
      if (params.get('material_id') !== item.id) throw new Error('课件标识不匹配，请重新同步。');
      let record = manifest[item.id], local = record ? await localFile(directory,record.name) : null;
      if (!record) {
        const adopted = await existingName(directory,item,manifest);
        local = adopted ? await localFile(directory,adopted) : null;
        if (local?.file.size) {
          record = {name:adopted,version,size:local.file.size,lastModified:local.file.lastModified,managed:false};
          signal.throwIfAborted(); await onRecord(item.id,record); manifest[item.id] = record;
        }
      }
      if (record?.version === version && local?.file.size) {
        result.skipped.push({id:item.id,name:record.name}); continue;
      }
      params.set('account_revision',revision);
      const response = await readResponse(await request(path+params,{signal:AbortSignal.any([signal,AbortSignal.timeout(120000)]),credentials:'same-origin',redirect:'error'}));
      if (/^(text\/html|application\/(json|xhtml\+xml))\b/i.test(response.headers.get('content-type') || '')) throw new Error('来源返回了登录页或错误内容，请重新连接 Piazza。');
      const blob = await response.blob();
      if (!blob.size) throw new Error('来源返回了空文件。');
      signal.throwIfAborted();
      // Recheck after the network wait so edits made during downloading are preserved.
      local = record ? await localFile(directory,record.name) : null;
      const replace = record?.managed && local && local.file.size === record.size && local.file.lastModified === record.lastModified;
      name = replace ? record.name : await unusedName(directory,fileName(response,item.title));
      signal.throwIfAborted();
      const handle = replace ? local.handle : await directory.getFileHandle(name,{create:true});
      created = !replace;
      writer = await handle.createWritable();
      await writer.write(blob);
      signal.throwIfAborted();
      await writer.close(); writer = null; committed = true;
      const saved = await handle.getFile();
      const next = {name,version,size:saved.size,lastModified:saved.lastModified,managed:true};
      await onRecord(item.id,next); manifest[item.id] = next;
      result.saved.push({id:item.id,name});
    } catch (error) {
      if (writer) { try { await writer.abort(); } catch { /* Already closed. */ } }
      if (created && !committed) { try { await directory.removeEntry(name); } catch { /* Report the original failure. */ } }
      if (signal.aborted) { result.cancelled = true; result.remaining = items.slice(index); break; }
      result.failed.push({item,message:error.message});
      if ([401,403,409].includes(error.status) || error.name === 'NotAllowedError') {
        result.remaining = items.slice(index+1); break;
      }
    }
  }
  onProgress({...result,current:'',done:result.saved.length+result.skipped.length+result.failed.length,total:items.length});
  return result;
}
