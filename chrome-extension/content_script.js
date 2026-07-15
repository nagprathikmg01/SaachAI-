// content_script.js — Runs on the SachhAI website page
// Reads auth from the website's localStorage and forwards to the extension.

(function () {
  function trySendAuth() {
    // Primary: sai_auth JSON object (written by login.html)
    let auth = null;
    const raw = localStorage.getItem('sai_auth');
    if (raw) {
      try { auth = JSON.parse(raw); } catch (_) {}
    }

    // Fallback: legacy iap_* keys
    if (!auth || !auth.token) {
      const token    = localStorage.getItem('iap_token');
      const username = localStorage.getItem('iap_username');
      if (token && username) {
        auth = {
          token,
          username,
          role:         localStorage.getItem('iap_role') || 'hr',
          display_name: localStorage.getItem('iap_display') || username,
        };
      }
    }

    if (auth && auth.token) {
      chrome.storage.local.set({ sai_auth: auth });
      chrome.runtime.sendMessage({ type: 'SAI_AUTH', ...auth }).catch(() => {});
    }
  }

  trySendAuth();

  window.addEventListener('storage', e => {
    if (e.key === 'sai_auth' || e.key === 'iap_token') trySendAuth();
  });

  let tries = 0;
  const poll = setInterval(() => {
    trySendAuth();
    if (++tries >= 30) clearInterval(poll);
  }, 2000);
})();
