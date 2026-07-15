/**
 * meet_cc_guard.js — SachhAI Real-Time CC Engine v3
 *
 * NEW APPROACH: Watch ALL text node mutations across the entire document.
 * No selector guessing needed — any text added to the DOM gets checked.
 * Filters for natural speech patterns and deduplicates aggressively.
 */

(function () {
  'use strict';

  // Prevent double-inject
  if (window.__saiCCv3) return;
  window.__saiCCv3 = true;

  const API_WS   = 'ws://127.0.0.1:8000/voice/meet-analyze';
  const PING_MS  = 20000;
  const OL_ID    = 'sai-ol-v3';

  // ── State ────────────────────────────────────────────────────────────────────
  let ws           = null;
  let pingTimer    = null;
  let overlayEl    = null;
  let liveScore    = null;
  let liveVerdict  = 'CALIBRATING';
  let liveWords    = 0;
  let phaseLabel   = 'Listening for captions…';
  let personalText = '';

  // Seen-text dedup — avoid sending same sentence twice
  const seenTexts  = new Set();
  let   sentBuffer = [];   // [{t, text}] full session log
  let   wordCount  = 0;

  // ── SPEECH FILTER ─────────────────────────────────────────────────────────────
  // Detect text that looks like a spoken sentence
  const IGNORE_PREFIXES = [
    'http', 'www.', 'meet.google', 'Join', 'Copy link', 'More options',
    'Mute', 'Camera', 'Present', 'Raise hand', 'Emoji', 'React',
    'Leave call', 'Turn', 'Settings', 'End call', 'Share screen',
    'Add', 'Chat', 'People', 'Activities', 'Host', 'You are',
    'Closed captions', 'Caption', '0:', '1:', '2:', '3:', '4:',
    'AM', 'PM', 'SachhAI',
  ];

  function looksLikeSpeech(text) {
    if (!text || text.length < 6 || text.length > 800) return false;
    // Must contain multiple words
    const words = text.trim().split(/\s+/);
    if (words.length < 2) return false;
    // Must have actual letters
    if (!/[a-zA-Z]{3,}/.test(text)) return false;
    // Ignore UI strings
    for (const p of IGNORE_PREFIXES) {
      if (text.startsWith(p)) return false;
    }
    // Ignore all-caps (buttons/labels)
    if (text === text.toUpperCase() && text.length > 4) return false;
    // Ignore strings with too many special chars
    const specialRatio = (text.match(/[^a-zA-Z0-9\s'.,?!-]/g) || []).length / text.length;
    if (specialRatio > 0.3) return false;
    return true;
  }

  // ── DEDUP KEY ─────────────────────────────────────────────────────────────────
  function dedupKey(text) {
    // Normalize: lowercase, strip punctuation, trim whitespace
    return text.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim().slice(0, 80);
  }

  // ── PROCESS incoming text ─────────────────────────────────────────────────────
  function processText(rawText) {
    const text = rawText.trim();
    if (!looksLikeSpeech(text)) return;

    const key = dedupKey(text);
    if (seenTexts.has(key)) return;
    seenTexts.add(key);

    // Log
    sentBuffer.push({ t: Date.now(), text });
    wordCount += text.split(/\s+/).length;
    liveWords  = wordCount;

    // Save to storage
    chrome.storage.local.set({
      sai_cc_log:         sentBuffer.slice(-500),
      sai_cc_words:       wordCount,
      sai_cc_last:        text,
      sai_cc_updated_at:  Date.now(),
    }).catch(() => {});

    // Send to backend
    sendWS({ type: 'transcript', text, speaker: 'Candidate', t: Date.now() });

    // Update overlay CC preview
    const previewEl = document.getElementById('sai-cc-prev');
    if (previewEl) previewEl.textContent = '📝 ' + text.slice(-70);

    // Update word counter
    const wordsEl = document.getElementById('sai-words');
    if (wordsEl) wordsEl.textContent = wordCount + ' words captured';

    console.log('[SachhAI ✓]', wordCount + 'w |', text.slice(0, 50));
  }

  // ── TEXT NODE OBSERVER ────────────────────────────────────────────────────────
  // Watches ALL mutations — catches any CC implementation Meet uses
  const observer = new MutationObserver((mutations) => {
    for (const mut of mutations) {
      // Check new text nodes
      for (const node of mut.addedNodes) {
        if (node.nodeType === Node.TEXT_NODE) {
          processText(node.textContent);
        } else if (node.nodeType === Node.ELEMENT_NODE) {
          // Also check text content of added elements
          const t = node.innerText || node.textContent || '';
          processText(t);
          // And all their text descendants
          node.querySelectorAll && node.querySelectorAll('span, div, p').forEach(el => {
            processText(el.innerText || el.textContent || '');
          });
        }
      }
      // Check character data changes
      if (mut.type === 'characterData' && mut.target) {
        processText(mut.target.textContent);
      }
    }
  });

  observer.observe(document.documentElement, {
    childList:     true,
    subtree:       true,
    characterData: true,
  });

  // ── POLLING BACKUP — scan visible text every 1s ───────────────────────────────
  // Scans ALL visible elements' text — catches cases where Meet
  // doesn't add new nodes but updates existing ones in-place
  let lastPollSnapshot = '';
  setInterval(() => {
    // Grab all spans and divs with short-ish text that looks like CC
    const candidates = [];
    document.querySelectorAll('span, p').forEach(el => {
      const t = (el.innerText || el.textContent || '').trim();
      if (looksLikeSpeech(t) && t.length > 8) {
        candidates.push(t);
      }
    });
    if (!candidates.length) return;

    // Find the longest fresh-looking text
    const longest = candidates.reduce((a, b) => a.length >= b.length ? a : b, '');
    if (longest && longest !== lastPollSnapshot && longest.length > 8) {
      lastPollSnapshot = longest;
      processText(longest);
    }
  }, 1000);

  // ── WEBSOCKET ────────────────────────────────────────────────────────────────
  function connectWS() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    try {
      ws = new WebSocket(API_WS);
    } catch (e) {
      console.warn('[SachhAI] WS failed:', e.message);
      setTimeout(connectWS, 4000);
      return;
    }

    ws.onopen = () => {
      console.log('[SachhAI] WS connected');
      phaseLabel = 'Connected — capturing live captions';
      updateStatus();
      clearInterval(pingTimer);
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, PING_MS);
      if (personalText) {
        ws.send(JSON.stringify({ type: 'baseline', text: personalText }));
      }
      // Replay buffered text if any
      if (sentBuffer.length) {
        const bufferedText = sentBuffer.map(s => s.text).join(' ');
        if (bufferedText.length > 20) {
          ws.send(JSON.stringify({ type: 'transcript', text: bufferedText, speaker: 'Candidate' }));
        }
      }
    };

    ws.onmessage = (e) => {
      try { handleMsg(JSON.parse(e.data)); } catch (_) {}
    };
    ws.onclose = () => {
      clearInterval(pingTimer);
      if (overlayEl) setTimeout(connectWS, 3000);
    };
    ws.onerror = () => {
      if (overlayEl) setTimeout(connectWS, 3000);
    };
  }

  function sendWS(payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try { ws.send(JSON.stringify(payload)); } catch (e) {}
  }

  // ── HANDLE SERVER MESSAGES ────────────────────────────────────────────────────
  function handleMsg(msg) {
    if (msg.type === 'pong') return;

    if (msg.type === 'status') {
      phaseLabel = msg.message || phaseLabel;
      if (msg.total_words) liveWords = msg.total_words;
      updateStatus();
      broadcast({ type: 'SAI_LIVE_STATUS', message: phaseLabel, words: liveWords });
      return;
    }

    if (msg.type === 'analysis') {
      liveScore   = msg.score;
      liveVerdict = msg.verdict || 'GENUINE';
      if (msg.total_words) liveWords = msg.total_words;
      phaseLabel  = `LIVE · ${msg.style_shift || 'LOW'} shift`;
      updateOverlayFull(msg);
      broadcast({
        type:    'SAI_LIVE_ANALYSIS',
        score:   liveScore,
        lsdi:    msg.lsdi || 0,
        verdict: liveVerdict,
        shift:   msg.style_shift || 'LOW',
        words:   liveWords,
        flags:   msg.flags || [],
        plag:    msg.plagiarism_risk || 0,
        formality:  msg.formality || 0,
        vocabulary: msg.vocabulary || 0,
        fillers:    msg.filler_ratio || 0,
        timeline:   msg.timeline || [],
      });
    }
  }

  function broadcast(data) {
    try { chrome.runtime.sendMessage(data).catch(() => {}); } catch (_) {}
  }

  // ── OVERLAY ───────────────────────────────────────────────────────────────────
  function scoreColor(s) {
    if (s == null) return '#64748b';
    if (s >= 80)   return '#10b981';
    if (s >= 60)   return '#f59e0b';
    if (s >= 40)   return '#f97316';
    return '#ef4444';
  }
  function verdictColor(v) {
    const u = (v || '').toUpperCase();
    if (u.includes('HIGHLY'))    return '#ef4444';
    if (u.includes('SUSPICIOUS'))return '#f97316';
    if (u.includes('REVIEW'))    return '#f59e0b';
    if (u.includes('GENUINE'))   return '#10b981';
    return '#64748b';
  }

  function injectOverlay() {
    if (document.getElementById(OL_ID)) return;
    const el = document.createElement('div');
    el.id = OL_ID;
    el.innerHTML = `
<style>
#${OL_ID}{position:fixed;bottom:76px;right:16px;z-index:2147483647;width:248px;
background:rgba(4,6,15,.96);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
border:1px solid rgba(0,245,255,.2);border-radius:15px;padding:12px 14px;
font-family:'Inter',-apple-system,sans-serif;font-size:12px;
box-shadow:0 18px 55px rgba(0,0,0,.8),0 0 28px rgba(0,245,255,.06);
color:#e2e8f0;animation:saiIn .3s cubic-bezier(.16,1,.3,1)}
@keyframes saiIn{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
#${OL_ID} *{box-sizing:border-box;margin:0;padding:0;font-family:inherit}
#${OL_ID} .hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px}
#${OL_ID} .brand{font-size:9.5px;font-weight:800;letter-spacing:1px;color:#3b82f6;text-transform:uppercase}
#${OL_ID} .dot{display:inline-block;width:6px;height:6px;border-radius:50%;
background:#10b981;margin-left:5px;animation:dp 1.4s ease-in-out infinite;vertical-align:middle}
@keyframes dp{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(1.5)}}
#${OL_ID} .cls{background:none;border:none;color:#475569;cursor:pointer;font-size:12px;padding:2px 5px;
transition:color .2s;border-radius:4px}
#${OL_ID} .cls:hover{color:#e2e8f0;background:rgba(255,255,255,.08)}
#${OL_ID} .srow{display:flex;align-items:center;gap:10px;margin-bottom:9px}
#${OL_ID} .ring{width:50px;height:50px;border-radius:50%;border:3px solid;
display:flex;align-items:center;justify-content:center;
font-size:18px;font-weight:800;flex-shrink:0;transition:color .5s,border-color .5s}
#${OL_ID} .meta{flex:1;min-width:0}
#${OL_ID} .verd{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;transition:color .5s}
#${OL_ID} .lsdi{font-size:8.5px;color:#475569;margin-top:2px}
#${OL_ID} .stat{font-size:9px;color:#94a3b8;background:rgba(255,255,255,.04);
border-radius:6px;padding:4px 8px;margin-bottom:7px;min-height:22px;line-height:1.5}
#${OL_ID} .brow{display:flex;align-items:center;gap:5px;margin-bottom:3px}
#${OL_ID} .blbl{font-size:8px;color:#475569;width:52px;flex-shrink:0;text-transform:uppercase;letter-spacing:.3px}
#${OL_ID} .btrk{flex:1;height:4px;background:rgba(255,255,255,.07);border-radius:2px;overflow:hidden}
#${OL_ID} .bfill{height:100%;border-radius:2px;transition:width .6s ease,background .4s}
#${OL_ID} .bval{font-size:8px;color:#475569;width:26px;text-align:right;flex-shrink:0}
#${OL_ID} .flag{font-size:8.5px;color:#fbbf24;background:rgba(251,191,36,.08);
border-left:2px solid #fbbf24;padding:3px 6px;border-radius:0 4px 4px 0;
margin-top:5px;line-height:1.4;display:none}
#${OL_ID} .foot{display:flex;justify-content:space-between;margin-top:6px;
font-size:8px;color:#334155}
#${OL_ID} .cc-prev{font-size:8px;color:#1e40af;margin-top:3px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
background:rgba(59,130,246,.06);padding:2px 5px;border-radius:4px}
</style>
<div class="hdr">
  <span class="brand">SachhAI<span class="dot"></span></span>
  <button class="cls" id="sai-cls">✕</button>
</div>
<div class="srow">
  <div class="ring" id="sai-ring" style="color:#64748b;border-color:#1e293b">—</div>
  <div class="meta">
    <div class="verd" id="sai-verd" style="color:#475569">CALIBRATING</div>
    <div class="lsdi" id="sai-lsdi">LSDI: —</div>
  </div>
</div>
<div class="stat" id="sai-stat">Listening for speech…</div>
<div class="brow"><span class="blbl">Formality</span><div class="btrk"><div class="bfill" id="b-form" style="width:0%;background:#3b82f6"></div></div><span class="bval" id="v-form">—</span></div>
<div class="brow"><span class="blbl">Vocab</span><div class="btrk"><div class="bfill" id="b-voc" style="width:0%;background:#2563eb"></div></div><span class="bval" id="v-voc">—</span></div>
<div class="brow"><span class="blbl">Fillers</span><div class="btrk"><div class="bfill" id="b-fill" style="width:0%;background:#10b981"></div></div><span class="bval" id="v-fill">—</span></div>
<div class="brow"><span class="blbl">Plag Risk</span><div class="btrk"><div class="bfill" id="b-plag" style="width:0%;background:#f43f5e"></div></div><span class="bval" id="v-plag">—</span></div>
<div class="flag" id="sai-flag"></div>
<div class="foot">
  <span id="sai-words">0 words</span>
  <span id="sai-phase">baseline</span>
</div>
<div class="cc-prev" id="sai-cc-prev">waiting for speech…</div>
`;
    document.body.appendChild(el);
    overlayEl = el;
    document.getElementById('sai-cls').onclick = () => {
      el.remove(); overlayEl = null;
      cleanup();
    };
  }

  function updateStatus() {
    const s = document.getElementById('sai-stat');
    const w = document.getElementById('sai-words');
    if (s) s.textContent = phaseLabel;
    if (w) w.textContent = liveWords + ' words';
  }

  function updateOverlayFull(msg) {
    if (!overlayEl) return;
    const s   = msg.score;
    const col = scoreColor(s);

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const setStyle = (id, prop, val) => { const el = document.getElementById(id); if (el) el.style[prop] = val; };

    set('sai-ring', s != null ? Math.round(s) : '—');
    setStyle('sai-ring', 'color', col);
    setStyle('sai-ring', 'borderColor', col);

    set('sai-verd', liveVerdict);
    setStyle('sai-verd', 'color', verdictColor(liveVerdict));

    set('sai-lsdi', 'LSDI: ' + (msg.lsdi || 0).toFixed(1) + '/100');
    set('sai-stat', phaseLabel);
    set('sai-words', liveWords + ' words');
    set('sai-phase', msg.style_shift || 'LOW');

    const bar = (bid, vid, pct, good_col, bad_col, bad_thresh) => {
      const bel = document.getElementById(bid);
      const vel = document.getElementById(vid);
      const p   = Math.min(100, Math.max(0, pct));
      if (bel) { bel.style.width = p + '%'; bel.style.background = p > bad_thresh ? bad_col : good_col; }
      if (vel) vel.textContent = Math.round(p);
    };

    bar('b-form', 'v-form', msg.formality  || 0,  '#3b82f6', '#f43f5e', 70);
    bar('b-voc',  'v-voc',  msg.vocabulary || 0,  '#2563eb', '#f43f5e', 70);
    bar('b-fill', 'v-fill', Math.min(100, (msg.filler_ratio || 0) * 2000), '#10b981', '#f43f5e', 0); // inverted
    bar('b-plag', 'v-plag', msg.plagiarism_risk || 0, '#10b981', '#ef4444', 40);

    // Fix filler bar — high fillers = natural = green
    const fillEl = document.getElementById('b-fill');
    const fillPct = Math.min(100, (msg.filler_ratio || 0) * 2000);
    if (fillEl) fillEl.style.background = fillPct > 30 ? '#10b981' : fillPct > 10 ? '#f59e0b' : '#ef4444';

    const flagEl = document.getElementById('sai-flag');
    const topFlag = (msg.flags || [])[0];
    if (flagEl) {
      if (topFlag) { flagEl.textContent = '⚡ ' + topFlag.slice(0, 80); flagEl.style.display = 'block'; }
      else flagEl.style.display = 'none';
    }
  }

  // ── CLEANUP ───────────────────────────────────────────────────────────────────
  function cleanup() {
    clearInterval(pingTimer);
    observer.disconnect();
    if (ws) { try { ws.close(); } catch (_) {} ws = null; }
  }

  function saveSession() {
    chrome.storage.local.get('sai_session_history', r => {
      const h = r.sai_session_history || [];
      h.unshift({
        session_id:    'meet_' + Date.now(),
        ended_at:      new Date().toISOString(),
        meet_url:      window.location.href,
        words_total:   wordCount,
        final_score:   liveScore,
        final_verdict: liveVerdict,
        transcript:    sentBuffer,
      });
      chrome.storage.local.set({ sai_session_history: h.slice(0, 20) });
    });
  }

  // ── MESSAGE LISTENER ──────────────────────────────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'SAI_PERSONAL_BASELINE' && msg.text) {
      personalText = msg.text;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'baseline', text: personalText }));
        phaseLabel = 'Baseline set — live analysis active';
        updateStatus();
      }
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === 'SAI_GET_CC_LOG') {
      sendResponse({ log: sentBuffer, words: wordCount });
      return true;
    }
    if (msg.type === 'SAI_SESSION_END') {
      saveSession(); cleanup();
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === 'SAI_GET_LIVE_STATUS') {
      sendResponse({ active: !!ws, score: liveScore, verdict: liveVerdict, words: wordCount });
      return true;
    }
  });

  // ── BOOT ─────────────────────────────────────────────────────────────────────
  injectOverlay();
  connectWS();
  window.addEventListener('beforeunload', () => { saveSession(); cleanup(); });

  console.log('[SachhAI v3] CC engine started — watching ALL text mutations');
})();
