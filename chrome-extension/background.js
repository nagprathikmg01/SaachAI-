/**
 * background.js — SachhAI service worker
 *
 * Handles cross-context messages between the popup and content scripts.
 */

let currentAudioSource = 'tab';

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // ── Audio source sync ────────────────────────────────────────────────────
  if (msg.type === 'SAI_SET_SRC') {
    currentAudioSource = msg.src || 'tab';
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === 'SAI_GET_SRC') {
    sendResponse({ src: currentAudioSource });
    return true;
  }
  if (msg.type === 'SAI_SWITCH_SRC') {
    currentAudioSource = 'tab';
    chrome.runtime.sendMessage({ type: 'SAI_SRC_CHANGED', src: 'tab' }).catch(() => {});
    sendResponse({ ok: true });
    return true;
  }

  // ── Auth passthrough ─────────────────────────────────────────────────────
  if (msg.type === 'SAI_AUTH' && msg.token) {
    chrome.storage.local.set({ sai_auth: msg });
    sendResponse({ ok: true });
    return true;
  }

  // ── Relay personal baseline → active Meet tab ─────────────────────────
  if (msg.type === 'SAI_PERSONAL_BASELINE' && msg.text) {
    chrome.tabs.query({ url: 'https://meet.google.com/*' }, (tabs) => {
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, {
          type: 'SAI_PERSONAL_BASELINE',
          text: msg.text,
        }).catch(() => {});
      });
    });
    sendResponse({ ok: true });
    return true;
  }

  // ── Relay live analysis from CC guard → popup ─────────────────────────
  if (msg.type === 'SAI_LIVE_ANALYSIS' || msg.type === 'SAI_LIVE_STATUS') {
    // Forward to all extension views (popup if open)
    chrome.runtime.sendMessage(msg).catch(() => {});
    sendResponse({ ok: true });
    return true;
  }

  // ── Session end signal → Meet tab ────────────────────────────────────
  if (msg.type === 'SAI_SESSION_END') {
    chrome.tabs.query({ url: 'https://meet.google.com/*' }, (tabs) => {
      tabs.forEach(tab => {
        chrome.tabs.sendMessage(tab.id, { type: 'SAI_SESSION_END' }).catch(() => {});
      });
    });
    sendResponse({ ok: true });
    return true;
  }
});

// ── Health check on extension load ──────────────────────────────────────────
(async () => {
  try {
    const res = await fetch('http://127.0.0.1:8000/health');
    if (!res.ok) throw new Error('Health check failed');
    const data = await res.json();
    if (data.status !== 'ok') throw new Error('Backend not ok');
    console.log('[SachhAI] Backend health check passed');
  } catch (e) {
    console.warn('[SachhAI] Backend health check error:', e);
    chrome.runtime.sendMessage({
      type: 'SAI_ALERT',
      message: 'Backend not running – start the Python server with: uvicorn server:app --port 8000',
    }).catch(() => {});
  }
})();
