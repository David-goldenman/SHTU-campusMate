// QJQ's enrollment guide: enter account security and ask the school for recheck.
// Passwords, verification fields and WebAuthn dialogs remain under user control.
(() => {
  if (location.origin !== 'https://ids.shanghaitech.edu.cn' || location.pathname !== '/personalInfo/personCenter/index.html') return;
  const started = Date.now();
  const timer = setInterval(() => {
    if (Date.now() - started > 600000 || sessionStorage.getItem('campus-device-recheck-opened')) {
      clearInterval(timer);
      return;
    }
    const visible = node => node.getClientRects().length && !node.disabled;
    const bind = [...document.querySelectorAll('button')].filter(node => visible(node) && node.textContent.trim() === '绑定当前设备');
    if (bind.length === 1) {
      sessionStorage.setItem('campus-device-recheck-opened', '1');
      bind[0].click();
      clearInterval(timer);
      return;
    }
    if (location.hash !== '#/accountsecurity') {
      const security = [...document.querySelectorAll('li')].filter(node => visible(node) && node.textContent.trim() === '账号安全');
      if (security.length === 1) security[0].click();
    }
  }, 500);
})();
