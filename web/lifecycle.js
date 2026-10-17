export async function withTimeout(promise, milliseconds, onTimeout = () => {}) {
  let timer;
  try {
    return await Promise.race([promise,new Promise((resolve,reject) => {
      timer=setTimeout(()=>{onTimeout();reject(new Error('模块操作超时，请稍后重试。'));},milliseconds);
    })]);
  } finally {clearTimeout(timer);}
}

export function cleanupAll(cleanups, milliseconds = 3000) {
  return Promise.allSettled(cleanups.map(cleanup => withTimeout(Promise.resolve().then(cleanup),milliseconds)));
}
