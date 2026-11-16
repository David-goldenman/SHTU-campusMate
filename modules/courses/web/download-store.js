// Directory handles stay in this browser's IndexedDB; no local paths leave the device.
export const downloadKey = (revision, courseId) => JSON.stringify([revision,courseId]);

export function folderStore() {
  async function transact(mode, operation, storeName = 'folders') {
    const db = await new Promise((resolve,reject) => {
      const request = indexedDB.open('campusmate-course-downloads',2);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains('folders')) request.result.createObjectStore('folders',{keyPath:'key'});
        if (!request.result.objectStoreNames.contains('roots')) request.result.createObjectStore('roots',{keyPath:'revision'});
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error('浏览器无法保存文件夹设置，请检查站点存储权限。'));
    });
    try {
      return await new Promise((resolve,reject) => {
        const transaction = db.transaction(storeName,mode);
        let request;
        try { request = operation(transaction.objectStore(storeName)); }
        catch(error) { transaction.abort(); reject(error); return; }
        transaction.oncomplete = () => resolve(request.result);
        transaction.onabort = transaction.onerror = () => reject(transaction.error || new Error('文件夹设置未能保存。'));
      });
    } finally { db.close(); }
  }
  return {
    roots: () => transact('readonly',store=>store.getAll(),'roots'),
    getRoot: revision => transact('readonly',store=>store.get(revision),'roots'),
    putRoot: record => transact('readwrite',store=>store.put(record),'roots'),
    updateRoot: (revision, change) => transact('readwrite',store=>{
      const request = store.get(revision);
      request.onsuccess = () => { const next = change(request.result); if (next) store.put(next); };
      return request;
    },'roots'),
    removeRoot: revision => transact('readwrite',store=>store.delete(revision),'roots'),
    all: () => transact('readonly',store=>store.getAll()),
    get: key => transact('readonly',store=>store.get(key)),
    put: record => transact('readwrite',store=>store.put(record)),
    update: (key, change) => transact('readwrite',store=>{
      const request = store.get(key);
      request.onsuccess = () => { const next = change(request.result); if (next) store.put(next); };
      return request;
    }),
    remove: key => transact('readwrite',store=>store.delete(key)),
  };
}
