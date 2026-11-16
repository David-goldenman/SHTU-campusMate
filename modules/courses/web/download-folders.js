import {safeName} from './downloads.js';
import {termLabel} from './summary.js';

/** Serialize folder allocation and complete writes across courses and browser tabs. */
export async function withDownloadLock(signal, work) {
  if (!globalThis.navigator?.locks) throw new Error('此浏览器不支持安全的多窗口下载，请使用新版 Edge 或 Chrome。');
  return navigator.locks.request('campusmate-course-downloads',{signal},work);
}

/** Keep the allocated folder stable across course renames and migrate old manifests. */
export async function courseFolder(binding, course, storage, signal, root) {
  const layout = root ? 'semester-v2' : 'course-v1';
  if (binding.layout === layout && (!root || binding.rootToken === root.token && binding.semester === (course.term || ''))) return binding;
  const semesterName = safeName(termLabel(course.term));
  const parent = root ? await root.directory.getDirectoryHandle(semesterName,{create:true}) : binding.directory;
  const label = safeName([course.code,course.title,...(root?[]:[course.term])].filter(Boolean).join(' · ') || course.id);
  const occupied = new Set();
  for await (const [name] of parent.entries()) occupied.add(name.toLowerCase());
  let name = label, suffix = 2;
  while (occupied.has(name.toLowerCase())) name = `${label} (${suffix++})`;
  signal.throwIfAborted();
  const directory = await parent.getDirectoryHandle(name,{create:true});
  // Old flat folders can contain a filename claimed by two courses. Its owner is
  // ambiguous, so preserve it rather than moving somebody else's material.
  const sharedNames = new Set();
  const ownNames = new Set(Object.values(binding.files || {}).map(record=>record.name.toLowerCase()));
  for (const other of await storage.all()) {
    if (other.key === binding.key) continue;
    for (const record of Object.values(other.files || {})) {
      if (!ownNames.has(record.name.toLowerCase())) continue;
      const original = record.directory || (record.legacy ? other.legacyDirectory : other.directory);
      if (original && await original.isSameEntry(binding.directory)) sharedNames.add(record.name.toLowerCase());
    }
  }
  signal.throwIfAborted();
  await storage.update(binding.key,latest=>{
    if (latest?.token !== binding.token) return null;
    const files = Object.fromEntries(Object.entries(latest.files || {}).map(([id,record])=>[id,{
      ...record,legacy:true,directory:record.directory || (record.legacy?latest.legacyDirectory:latest.directory),
      managed:!!record.managed && !sharedNames.has(record.name.toLowerCase()),
    }]));
    const previousParent = latest.layout === 'semester-v2' ? latest.semesterDirectory : latest.layout === 'course-v1' ? latest.parentDirectory : null;
    const cleanupDirectories = [...(latest.cleanupDirectories || []),...(previousParent?[{parent:previousParent,directory:latest.directory}]:[])];
    return {...latest,directory,parentDirectory:root?.directory || parent,semesterDirectory:root?parent:undefined,
      legacyDirectory:latest.legacyDirectory || latest.directory,layout,rootToken:root?.token,semester:course.term || '',
      relativePath:root?`${semesterName} / ${name}`:name,cleanupDirectories,files};
  });
  const saved = await storage.get(binding.key);
  if (saved?.token !== binding.token || saved.layout !== layout || root && saved.rootToken !== root.token) throw new Error('文件夹设置已变化，请重新检查。');
  return saved;
}

/** Promote one unambiguous legacy root; several different choices need an explicit selection. */
export async function savedRoot(revision, storage, signal) {
  const root = await storage.getRoot(revision);
  if (typeof root?.auto === 'boolean') return root;
  const candidates = (await storage.all()).filter(record=>record.revision === revision);
  // Preserve old per-course choices when introducing the master switch.
  const auto = candidates.some(record=>record.auto === true);
  if (root) {
    signal.throwIfAborted();
    await storage.updateRoot(revision,latest=>latest && {...latest,auto:typeof latest.auto === 'boolean'?latest.auto:auto});
    return storage.getRoot(revision);
  }
  if (!candidates.length) return;
  const directory = candidates[0].parentDirectory || candidates[0].directory;
  for (const record of candidates.slice(1)) {
    if (!await directory.isSameEntry(record.parentDirectory || record.directory)) return;
  }
  signal.throwIfAborted();
  const promoted = {revision,directory,token:crypto.randomUUID(),auto};
  await storage.putRoot(promoted);
  return promoted;
}

export async function removeEmptyCourseFolders(binding) {
  for (const {parent,directory} of binding.cleanupDirectories || []) {
    try {
      const current = await parent.getDirectoryHandle(directory.name);
      if (await current.isSameEntry(directory)) await parent.removeEntry(directory.name);
    }
    catch { /* Nonempty folders, including local notes, always stay in place. */ }
  }
}
