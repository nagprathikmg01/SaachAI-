document.addEventListener('DOMContentLoaded', function () {
  // $ shorthand for getElementById — used throughout popup.js
  const $ = id => document.getElementById(id);

  const BASE_URL      = 'http://127.0.0.1:8000';
  const API           = `${BASE_URL}/voice`;
  const PORTAL_URL    = `${BASE_URL}/login`;
  const DASHBOARD_URL = `${BASE_URL}/dashboard`;

  // ── Auth ──────────────────────────────────────────────────────────────────
  let auth = { token:'', username:'', role:'', display:'' };
  function saveAuth(d) {
    auth = { token:d.token||'', username:d.username||'', role:d.role||'', display:d.display_name||d.username||'' };
    chrome.storage.local.set({ sai_auth: auth });
  }

  // Helper: generate auth headers for API requests
  function authHeaders() {
    const headers = {
      'Content-Type': 'application/json',
    };
    if (auth && auth.token) {
      headers['Authorization'] = `Bearer ${auth.token}`;
    }
    // Include username as a custom header for backend tracking
    if (auth && auth.username) {
      headers['X-Username'] = auth.username;
    }
    return headers;
  }
  function clearAuth() { auth={token:'',username:'',role:'',display:''}; chrome.storage.local.remove('sai_auth'); }
    // Helper: fetch with retry (max 2 attempts, 1s delay)
  async function fetchWithRetry(url, options, retries = 2) {
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const resp = await fetch(url, options);
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || resp.statusText);
        }
        return resp;
      } catch (e) {
        if (attempt < retries) {
          console.warn(`Fetch attempt ${attempt + 1} failed, retrying...`, e);
          await new Promise(r => setTimeout(r, 1000));
        } else {
          throw e;
        }
      }
    }
  }

  // Listen for alerts from background (e.g., health check failure)
  chrome.runtime.onMessage.addListener(msg => {
    if (msg.type === 'SAI_ALERT' && msg.message) {
      toast(msg.message, 'error');
    }
  });

  let _tt;
  function toast(msg, type='error') {
    const el=$('toast');
    el.textContent = msg;
    el.className = 'toast ' + type;
    el.style.display = 'block';
    clearTimeout(_tt);
    _tt = setTimeout(() => el.style.display = 'none', 5000);
  }

  // ── Screens ───────────────────────────────────────────────────────────────
  function showLogin() {
    $('loginScreen').style.display = 'flex';
    $('appScreen').style.display   = 'none';
  }
  function showApp() {
    $('loginScreen').style.display = 'none';
    $('appScreen').style.display   = 'flex';
    $('userDisplay').textContent   = auth.display || auth.username;
    $('userAvatar').textContent    = (auth.display || auth.username || '?')[0].toUpperCase();
    checkMicPermission();
    switchPhase('IDLE');
  }

  // ── Audio source: 'tab' (system/candidate) or 'mic' (fallback) ──────────
  let audioSource = 'tab'; // default: capture tab audio = candidate's voice only

  function checkMicPermission() {
    // Only show mic warning if user explicitly switched to mic mode
    if (audioSource !== 'mic') { $('micWarn').style.display = 'none'; return; }
    if (!navigator.permissions) return;
    navigator.permissions.query({ name: 'microphone' })
      .then(r => { $('micWarn').style.display = r.state === 'granted' ? 'none' : 'flex'; })
      .catch(() => {});
  }
  $('btnGrantMic').addEventListener('click', async () => {
    if (window.innerWidth < 700) { chrome.tabs.create({ url: chrome.runtime.getURL('popup.html?mic=1') }); return; }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach(t => t.stop());
      $('micWarn').style.display = 'none';
      toast('Microphone granted!', 'success');
    } catch(e) { toast('Mic denied: ' + e.message); }
  });

  // Audio source toggle
  $('btnSrcTab').addEventListener('click', () => setAudioSource('tab'));
  $('btnSrcMic').addEventListener('click', () => setAudioSource('mic'));
  function setAudioSource(src) {
    audioSource = src;
    $('btnSrcTab').classList.toggle('src-active', src === 'tab');
    $('btnSrcMic').classList.toggle('src-active', src === 'mic');
    $('srcHint').textContent = src === 'tab'
      ? '🎯 Capturing candidate audio only (tab/system audio)'
      : 'Capturing microphone — both voices will be mixed';
    if (src === 'mic') checkMicPermission();
    else $('micWarn').style.display = 'none';
    // Keep background + Meet guard in sync with popup selection.
    chrome.runtime.sendMessage({ type: 'SAI_SET_SRC', src }).catch(() => {});
  }

  // ── Login ─────────────────────────────────────────────────────────────────
  $('btnOpenPortal').addEventListener('click', () => {
    chrome.tabs.create({ url: PORTAL_URL });
    $('loginStatus').textContent = 'Waiting for sign-in on the tab that opened…';
    $('loginStatus').style.display = 'block';
    let tries = 0, poll = setInterval(() => {
      tries++;
      chrome.storage.local.get('sai_auth', r => {
        if (r.sai_auth && r.sai_auth.token) { clearInterval(poll); auth = r.sai_auth; showApp(); }
      });
      if (tries > 120) clearInterval(poll);
    }, 1000);
  });
  $('btnCheckAuth').addEventListener('click', () => {
    chrome.storage.local.get('sai_auth', r => {
      if (r.sai_auth && r.sai_auth.token) { auth = r.sai_auth; showApp(); }
      else { $('loginStatus').textContent = 'Not logged in yet.'; $('loginStatus').style.display = 'block'; }
    });
  });
  $('btnLogout').addEventListener('click', () => { clearAuth(); showLogin(); });
  $('btnOpenDash').addEventListener('click', () => {
    let url = DASHBOARD_URL;
    if (auth.token) url += `?token=${encodeURIComponent(auth.token)}&username=${encodeURIComponent(auth.username)}&role=${encodeURIComponent(auth.role)}&display_name=${encodeURIComponent(auth.display)}`;
    chrome.tabs.create({ url });
  });

  // ── State ─────────────────────────────────────────────────────────────────
  let phase = 'IDLE';
  let candidateId = '';
  let personalText = '';
  let technicalText = '';
  let personalSignals = null;
  let technicalSignals = null;
  let mediaRec = null;
  let audioChunks = [];
  let recTimer = null, recElapsed = 0;
  let liveCheckTimer = null;
  let baselineUpdateTimer = null;
  let liveAlerts = [];
  let analysisResult = null;
  let currentRound = null; // 'personal' | 'technical'

  // ── Phase switcher ────────────────────────────────────────────────────────
  const PHASE_PANELS = ['phaseIdle','phasePersonal','phaseTechnical','phaseAnalyzing','phaseComplete'];
  const PHASE_MAP = {
    IDLE: 'phaseIdle', PERSONAL_REC: 'phasePersonal', PERSONAL_DONE: 'phasePersonal',
    TECHNICAL_REC: 'phaseTechnical', ANALYZING: 'phaseAnalyzing', COMPLETE: 'phaseComplete'
  };

  function switchPhase(p) {
    phase = p;
    PHASE_PANELS.forEach(id => {
      const el = $(id);
      if (el) el.style.display = 'none';
    });
    const target = PHASE_MAP[p];
    if (target) { const el = $(target); if (el) el.style.display = 'flex'; }
    updatePhaseIndicator();
  }

  function updatePhaseIndicator() {
    const order = ['IDLE','PERSONAL_REC','PERSONAL_DONE','TECHNICAL_REC','ANALYZING','COMPLETE'];
    const idx = order.indexOf(phase);
    // dot 1=Setup, 2=Personal, 3=Technical, 4=Report
    const dotPhase = [0, 1, 1, 2, 3, 4]; // phase index → dot number - 1
    [1,2,3,4].forEach(n => {
      const dot = $('pDot' + n);
      if (!dot) return;
      dot.className = 'phase-dot' + (n - 1 < dotPhase[idx] ? ' done' : n - 1 === dotPhase[idx] ? ' active' : '');
    });
  }

  // ── Setup / Candidate ID ──────────────────────────────────────────────────
  $('btnGenId').addEventListener('click', () => {
    $('candidateIdInput').value = 'cand_' + Math.random().toString(36).slice(2, 8).toUpperCase();
  });
  $('btnStartSession').addEventListener('click', () => {
    const val = $('candidateIdInput').value.trim();
    if (!val) { toast('Enter or generate a candidate ID first'); return; }
    candidateId = val;
    $('sessionLabel').textContent = `Session: ${val}`;
    $('sessionLabel').style.display = 'block';
    toast(`Session started: ${val}`, 'success');
    switchPhase('PERSONAL_REC');
  });

  // ── Personal round ────────────────────────────────────────────────────────
  $('btnStartPersonal').addEventListener('click', () => startRecording('personal'));
  $('btnStopPersonal').addEventListener('click',  () => stopRecording());
  $('btnConfirmPersonal').addEventListener('click', () => confirmPersonal());

  // Manual text input (fallback when no mic / transcription fails)
  $('btnManualPersonal').addEventListener('click', () => {
    const txt = $('manualPersonalText').value.trim();
    if (!txt) { toast('Please enter the personal round text'); return; }
    personalText = txt;
    $('personalPreview').textContent = txt.slice(0, 180) + (txt.length > 180 ? '…' : '');
    $('personalPreview').style.display = 'block';
    $('btnConfirmPersonal').style.display = 'flex';
    $('recStatusP').textContent = `Text entered — ${txt.split(' ').length} words`;
    $('recStatusP').className = 'rec-status done';
  });

  // ── Recording helpers ─────────────────────────────────────────────────────
  async function startRecording(round) {
    if (!candidateId) { toast('Set candidate ID first'); return; }
    let stream;

    if (audioSource === 'tab') {
      // ── Tab audio: captures system/speaker output = candidate's voice only ──
      try {
        // getDisplayMedia with audio:true + video:false captures tab/system audio
        // The user picks the tab (e.g. Google Meet) in the browser prompt
        stream = await navigator.mediaDevices.getDisplayMedia({
          video: false,       // no screen capture needed
          audio: {
            echoCancellation: false,
            noiseSuppression: false,
            sampleRate: 16000
          }
        });
        // If browser forces a video track alongside audio, discard it immediately
        stream.getVideoTracks().forEach(t => t.stop());
        if (!stream.getAudioTracks().length) throw new Error('No audio track — pick a tab that has audio');
        toast('Tab audio captured — recording candidate voice only', 'success');
      } catch(e) {
        // User cancelled or browser doesn't support video:false — fallback to mic
        if (e.name === 'NotAllowedError' || e.message.includes('cancelled')) {
          toast('Capture cancelled — switched to mic fallback');
        } else {
          toast('Tab audio failed: ' + e.message + ' — switched to mic');
        }
        // Gracefully fall back to mic
        try {
          stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch(e2) {
          $('micWarn').style.display = 'flex';
          toast('Mic also denied — use text input below');
          return;
        }
      }
    } else {
      // ── Mic mode: traditional — captures both interviewer + candidate ──────
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        $('micWarn').style.display = 'none';
      } catch(e) {
        $('micWarn').style.display = 'flex';
        toast('Mic denied — use text input below instead');
        return;
      }
    }

    currentRound = round;
    audioChunks = [];
    const mime = ['audio/webm;codecs=opus','audio/webm','audio/ogg;codecs=opus','audio/mp4']
      .find(m => MediaRecorder.isTypeSupported(m)) || '';
    mediaRec = new MediaRecorder(stream, { mimeType: mime });
    mediaRec.ondataavailable = e => { if (e.data.size) audioChunks.push(e.data); };
    mediaRec.onstop = () => { stream.getTracks().forEach(t => t.stop()); handleRecordingStop(round); };
    mediaRec.start(1000); // Trigger ondataavailable every 1 second to support live check and baseline updates
    recElapsed = 0;
    clearInterval(recTimer);
    recTimer = setInterval(() => {
      recElapsed++;
      const el = $(round === 'personal' ? 'timerP' : 'timerT');
      if (el) el.textContent = Math.floor(recElapsed / 60) + ':' + String(recElapsed % 60).padStart(2, '0');
    }, 1000);

    if (round === 'personal') {
      $('btnStartPersonal').style.display = 'none';
      $('btnStopPersonal').style.display  = 'flex';
      $('recStatusP').textContent = audioSource === 'tab' ? 'Recording candidate (tab audio)…' : 'Recording (mic — both voices)…';
      $('recStatusP').className   = 'rec-status recording';
      clearInterval(baselineUpdateTimer);
      baselineUpdateTimer = setInterval(doBaselineUpdate, 30000);
    } else {
      $('btnStartTech').style.display = 'none';
      $('btnStopTech').style.display  = 'flex';
      $('recStatusT').textContent = audioSource === 'tab' ? 'Recording candidate (tab audio) — live monitoring active…' : 'Recording (mic) — live monitoring active…';
      $('recStatusT').className   = 'rec-status recording';
      startLiveStyleCheck();
    }
  }

  function stopRecording() {
    clearInterval(recTimer);
    clearInterval(baselineUpdateTimer);
    if (currentRound === 'technical') clearInterval(liveCheckTimer);
    if (mediaRec && mediaRec.state !== 'inactive') { mediaRec.requestData(); mediaRec.stop(); }
  }

  async function handleRecordingStop(round) {
    const blob = new Blob(audioChunks, { type: mediaRec ? mediaRec.mimeType : 'audio/webm' });

    if (round === 'personal') {
      $('btnStopPersonal').style.display = 'none';
      $('recStatusP').textContent = 'Transcribing audio…';
      $('recStatusP').className   = 'rec-status processing';
      const result = await transcribeBlob(blob, 'personal');
      if (result && result.text) {
        personalText = result.text;
        personalSignals = result.signals;
        $('personalPreview').textContent = personalText.slice(0, 180) + (personalText.length > 180 ? '…' : '');
        $('personalPreview').style.display  = 'block';
        $('btnConfirmPersonal').style.display = 'flex';
        $('recStatusP').textContent = `Transcribed — ${personalText.split(' ').length} words`;
        $('recStatusP').className   = 'rec-status done';
      } else {
        $('btnStartPersonal').style.display = 'flex';
        $('recStatusP').textContent = 'Transcription failed — use text input below';
        $('recStatusP').className   = 'rec-status error';
        $('manualPersonalWrap').style.display = 'block';
      }
    } else {
      clearInterval(liveCheckTimer);
      $('btnStopTech').style.display = 'none';
      $('recStatusT').textContent = 'Transcribing audio…';
      $('recStatusT').className   = 'rec-status processing';
      const result = await transcribeBlob(blob, 'technical');
      if (result && result.text) {
        technicalText = result.text;
        technicalSignals = result.signals;
        $('recStatusT').textContent = `Transcribed — ${technicalText.split(' ').length} words`;
        $('recStatusT').className   = 'rec-status done';
        await runFullAnalysis();
      } else {
        $('btnStartTech').style.display = 'flex';
        $('recStatusT').textContent = 'Transcription failed — use text input below';
        $('recStatusT').className   = 'rec-status error';
        $('manualTechWrap').style.display = 'block';
      }
    }
  }

  async function transcribeBlob(blob, type) {
    const form = new FormData();
    form.append('audio', blob, `${type}_${candidateId}.webm`);
    form.append('type', type);
    try {
      const h = authHeaders(); delete h['Content-Type'];
      const r = await fetch(`${API}/transcribe-chunk`, { method: 'POST', headers: h, body: form });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || r.statusText);
      return { text: j.text || '', signals: j.audio_signals || null };
    } catch(e) {
      console.warn('Transcription error:', e.message);
      return { text: '', signals: null };
    }
  }

  async function doBaselineUpdate() {
    if (currentRound !== 'personal' || !audioChunks.length) return;
    const snap = audioChunks.slice();
    const blob = new Blob(snap, { type: mediaRec ? mediaRec.mimeType : 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, `baseline_${Date.now()}.webm`);
    form.append('type', 'personal');
    try {
      const h = authHeaders(); delete h['Content-Type'];
      const r = await fetch(`${API}/transcribe-chunk`, { method: 'POST', headers: h, body: form });
      const j = await r.json();
      if (!r.ok || !j.text) return;
      personalText = j.text;
      personalSignals = j.audio_signals || null;
      $('personalPreview').textContent = personalText.slice(0, 180) + (personalText.length > 180 ? '…' : '');
      $('personalPreview').style.display  = 'block';
      $('recStatusP').textContent = `Recording & updating baseline — ${personalText.split(' ').length} words`;
    } catch(e) { console.warn('Baseline update error:', e.message); }
  }

  // ── Confirm personal baseline ─────────────────────────────────────────────
  function confirmPersonal() {
    if (!personalText) { toast('No personal text captured yet'); return; }

    $('btnConfirmPersonal').style.display = 'none';
    toast('Personal baseline locked!', 'success');

    // Broadcast personal baseline to Meet CC guard for real-time analysis
    chrome.runtime.sendMessage({
      type: 'SAI_PERSONAL_BASELINE',
      text: personalText,
    }).catch(() => {});

    // Show technical phase
    switchPhase('TECHNICAL_REC');

    // Show baseline confirmed info in tech panel
    $('baselineInfo').textContent = `Baseline: ${personalText.split(' ').length} words captured`;
    $('baselineInfo').style.display = 'block';
  }

  // ── Technical round ───────────────────────────────────────────────────────
  $('btnStartTech').addEventListener('click', () => startRecording('technical'));
  $('btnStopTech').addEventListener('click', () => stopRecording());

  // Manual text fallback for technical
  $('btnManualTech').addEventListener('click', async () => {
    const txt = $('manualTechText').value.trim();
    if (!txt) { toast('Enter the technical round text first'); return; }
    technicalText = txt;
    $('recStatusT').textContent = `Text entered — ${txt.split(' ').length} words`;
    $('recStatusT').className = 'rec-status done';
    $('manualTechWrap').style.display = 'none';
    await runFullAnalysis();
  });

  // ── Live style check during technical ────────────────────────────────────
  function startLiveStyleCheck() {
    clearInterval(liveCheckTimer);
    liveCheckTimer = setInterval(doLiveCheck, 20000);
  }

  const SOFT_FLAGS = [
    'Noticeable communication style elevation detected.',
    'Response sophistication increased temporarily.',
    'Mid-session linguistic complexity spike observed.',
    'Candidate shifted toward more structured phrasing.',
    'Possible assisted-response indicators observed.',
    'Abrupt vocabulary enrichment detected.',
    'Response formulation became unusually optimized.',
    'Behavioral consistency variance detected.',
    'Semantic compression became unusually efficient.',
    'Formality level increased beyond established baseline.',
  ];

  async function doLiveCheck() {
    if (!personalText || !audioChunks.length) return;
    const snap = audioChunks.slice();
    if (!snap.length) return;
    const blob = new Blob(snap, { type: mediaRec ? mediaRec.mimeType : 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, `livecheck_${Date.now()}.webm`);
    form.append('type', 'technical');
    try {
      const h = authHeaders(); delete h['Content-Type'];
      const r = await fetch(`${API}/transcribe-chunk`, { method: 'POST', headers: h, body: form });
      const j = await r.json();
      if (!r.ok || !j.text) return;
      const wordCount = j.text.trim().split(/\s+/).filter(Boolean).length;
      if (wordCount < 50) {
        console.log(`[Live Check] Not enough words: ${wordCount}/50`);
        return;
      }
        const cr = await fetchWithRetry(`${API}/text-compare`, {
          method: 'POST', headers: authHeaders(),
          body: JSON.stringify({
            candidate_id: candidateId,
            personal: personalText,
            technical: j.text,
            personal_signals: personalSignals,
            technical_signals: j.audio_signals || null
          })
        });
      const cd = await cr.json();
      const a = cd.analysis || {};
      if ((a.shift_score || 0) > 35) addLiveAlert(a.style_shift || 'MODERATE', a.shift_score || 0, a.flags || []);
    } catch(e) { console.warn('Live check:', e.message); }
  }

  const PROBE_QUESTIONS = [
    "Could you walk me through the specific logic you used there in your own words?",
    "Can you explain that concept using a different example?",
    "What alternative approaches did you consider before settling on this one?",
    "How would you explain this to a non-technical stakeholder?",
    "Can you break down the hardest part of that implementation?"
  ];

  function addLiveAlert(shift, score, flags) {
    const msg = SOFT_FLAGS[liveAlerts.length % SOFT_FLAGS.length];
    const probe = PROBE_QUESTIONS[liveAlerts.length % PROBE_QUESTIONS.length];
    const div = document.createElement('div');
    div.className = 'live-alert ' + (score > 60 ? 'high' : score > 35 ? 'med' : 'low');
    
    const confPct = Math.min(100, Math.round(score));
    
    div.innerHTML = `
      <div class="alert-top" style="display:flex; justify-content:space-between; align-items:center;">
        <div><span class="alert-icon">${score > 60 ? '🔺' : '⚡'}</span><span style="font-weight:500;">${msg}</span></div>
        <span class="alert-time" style="font-size:0.75em; opacity:0.8;">${new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>
      </div>
      <div class="alert-probe" style="font-size:0.85em; margin-top:6px; color:#facc15; padding:4px; background:rgba(250, 204, 21, 0.1); border-radius:4px; border-left:2px solid #facc15;">
        💡 <b>Probe Suggestion:</b> "${probe}"
      </div>
      <div class="alert-conf-wrap" style="margin-top:8px; display:flex; align-items:center; gap:8px;">
        <span style="font-size:0.7em; opacity:0.8; white-space:nowrap;">Confidence: ${confPct}%</span>
        <div class="alert-conf-bar" style="flex-grow:1; height:4px; background:rgba(255,255,255,0.2); border-radius:2px; overflow:hidden;">
          <div style="width:${confPct}%; height:100%; background:${score > 60 ? '#ef4444' : '#f59e0b'}; transition: width 0.3s ease;"></div>
        </div>
      </div>
    `;
    const el = $('liveAlerts');
    el.insertBefore(div, el.firstChild);
    el.style.display = 'block';
    liveAlerts.push({ shift, score, msg });
    const badge = $('alertCount');
    badge.textContent = liveAlerts.length;
    badge.style.display = 'inline';
  }

  // ── Full post-interview analysis ──────────────────────────────────────────
  async function runFullAnalysis() {
    if (!personalText) { toast('Personal baseline missing — go back and record personal round'); return; }
    if (!technicalText) { toast('Technical response missing'); return; }
    switchPhase('ANALYZING');
    try {
        const r = await fetchWithRetry(`${API}/text-compare`, {
          method: 'POST', headers: authHeaders(),
          body: JSON.stringify({
            candidate_id: candidateId,
            personal: personalText,
            technical: technicalText,
            personal_signals: personalSignals,
            technical_signals: technicalSignals
          })
        });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || r.statusText);
      analysisResult = data.analysis || {};
      renderFinalResults(analysisResult);
      switchPhase('COMPLETE');
    } catch(e) {
      toast('Analysis failed: ' + e.message);
      // Go back to technical phase so user can retry
      switchPhase('TECHNICAL_REC');
      $('manualTechWrap').style.display = 'block';
      $('recStatusT').textContent = 'Analysis failed — try again or check backend connection';
      $('recStatusT').className = 'rec-status error';
    }
  }

  // ── Authenticity tier label ───────────────────────────────────────────────
  function getTier(score) {
    if (score >= 90) return { label: 'Highly Authentic',                color: '#10b981' };
    if (score >= 75) return { label: 'Mostly Natural',                  color: '#34d399' };
    if (score >= 60) return { label: 'Mild Assistance Indicators',      color: '#f59e0b' };
    if (score >= 40) return { label: 'Moderate Authenticity Concerns',  color: '#f97316' };
    if (score >= 20) return { label: 'Strong Assistance Indicators',    color: '#f43f5e' };
    return              { label: 'Heavy External Assistance Likely',    color: '#dc2626' };
  }

  // ── Render final results ──────────────────────────────────────────────────
  function renderFinalResults(a) {
    const score = a.authenticity_score != null ? a.authenticity_score : 0;
    const tier  = getTier(score);
    const shift = a.style_shift || 'LOW';
    const td    = a.temporal_drift || {};
    const flags = a.flags || [];

    $('finalScore').textContent = score;
    $('finalScore').style.color = tier.color;
    $('tierLabel').textContent  = a.tier_label || tier.label;
    $('tierLabel').style.color  = tier.color;

    const shiftCls = { LOW:'badge-g', MODERATE:'badge-a', HIGH:'badge-r', 'VERY HIGH':'badge-r' }[shift] || 'badge-g';
    $('shiftBadge').textContent  = `Style Shift: ${shift}`;
    $('shiftBadge').className    = 'shift-badge ' + shiftCls;

    $('finalSummary').textContent = a.summary || buildSummary(score, tier.label, liveAlerts.length);

    // Confidence interpretation panel
    $('confIdentity').textContent   = score >= 70 ? 'High' : score >= 50 ? 'Moderate' : 'Low';
    $('confSemantic').textContent   = td.has_spike ? 'Mild Drift' : 'Stable';
    $('confDrift').textContent      = { LOW:'Minimal', MODERATE:'Mild', HIGH:'Elevated', 'VERY HIGH':'Significant' }[shift] || 'Minimal';
    $('confAssistance').textContent = score >= 75 ? 'Low' : score >= 50 ? 'Moderate' : 'High';
    $('confReliability').textContent = score >= 70 ? 'Strong' : 'Requires Review';

    // Flags — deduplicated and softened
    const fw = $('finalFlags');
    fw.innerHTML = '';
    const shown = new Set();
    const softened = flags.filter(f => {
      const key = f.slice(0, 50);
      if (shown.has(key)) return false;
      shown.add(key); return true;
    }).slice(0, 5);

    if (!softened.length) {
      fw.innerHTML = '<div class="flag-chip safe">No behavioral anomalies detected.</div>';
    } else {
      softened.forEach(f => {
        const d = document.createElement('div');
        d.className = 'flag-chip warn';
        d.textContent = f;
        fw.appendChild(d);
      });
    }

    // Temporal drift
    const di = $('driftInfo');
    if (td.has_spike) {
      di.textContent = `Linguistic complexity spike observed mid-response (+${(td.drift_score||0).toFixed(1)} pts). Mid-session style elevation detected.`;
      di.className = 'drift-info warn';
    } else {
      di.textContent = 'Communication complexity remained stable throughout the session.';
      di.className = 'drift-info ok';
    }

    // Live alert summary
    if (liveAlerts.length) {
      $('liveAlertSummary').textContent = `${liveAlerts.length} real-time style alert${liveAlerts.length > 1 ? 's' : ''} recorded during technical round.`;
      $('liveAlertSummary').style.display = 'block';
    }
  }

  function buildSummary(score, tierLabel, alertCount) {
    const note = alertCount > 0 ? ` ${alertCount} real-time style variance${alertCount > 1 ? 's were' : ' was'} flagged.` : '';
    if (score >= 75) return `Behavioral Analysis: ${tierLabel} (${score}/100). Communication remained largely stable throughout the session. Behavioral consistency and semantic continuity were strong.${note} No significant authenticity concerns detected.`;
    if (score >= 50) return `Behavioral Analysis: ${tierLabel} (${score}/100). Some variations in linguistic sophistication were observed between rounds.${note} These patterns warrant attention but do not conclusively indicate external assistance.`;
    return `Behavioral Analysis: ${tierLabel} (${score}/100). Significant communication style differences were detected between rounds.${note} This warrants direct follow-up questioning to assess knowledge ownership.`;
  }

  // ── New session ───────────────────────────────────────────────────────────
  $('btnNewSession').addEventListener('click', () => {
    // Signal CC guard to save + disconnect
    chrome.runtime.sendMessage({ type: 'SAI_SESSION_END' }).catch(() => {});

    candidateId = ''; personalText = ''; technicalText = '';
    personalSignals = null; technicalSignals = null;
    audioChunks = []; liveAlerts = []; analysisResult = null; currentRound = null;
    clearInterval(recTimer); clearInterval(liveCheckTimer); clearInterval(baselineUpdateTimer);
    $('candidateIdInput').value     = '';
    $('sessionLabel').style.display = 'none';
    $('alertCount').style.display   = 'none';
    $('liveAlerts').innerHTML       = '';
    $('liveAlerts').style.display   = 'none';
    $('manualPersonalWrap').style.display = 'none';
    $('manualTechWrap').style.display     = 'none';
    $('personalPreview').style.display    = 'none';
    $('manualPersonalText').value = '';
    $('manualTechText').value     = '';
    $('btnStartPersonal').style.display   = 'flex';
    $('btnStopPersonal').style.display    = 'none';
    $('btnConfirmPersonal').style.display = 'none';
    $('btnStartTech').style.display       = 'flex';
    $('btnStopTech').style.display        = 'none';
    $('recStatusP').textContent = 'Ready to record'; $('recStatusP').className = 'rec-status idle';
    $('recStatusT').textContent = 'Ready';           $('recStatusT').className = 'rec-status idle';
    $('timerP').textContent = '0:00'; $('timerT').textContent = '0:00';
    // Hide live panel
    const lp = $('liveRtPanel'); if (lp) lp.style.display = 'none';
    switchPhase('IDLE');
  });

  // ── Live analysis from CC guard ──────────────────────────────────────────
  chrome.runtime.onMessage.addListener(msg => {
    if (msg.type === 'SAI_SRC_CHANGED' && msg.src) {
      setAudioSource(msg.src);
    }
    if (msg.type === 'SAI_AUTH' && msg.token) { saveAuth(msg); showApp(); }

    // Real-time live score from meet_cc_guard.js via background
    if (msg.type === 'SAI_LIVE_ANALYSIS') {
      updateLivePanel(msg);
    }
    if (msg.type === 'SAI_LIVE_STATUS') {
      const el = $('liveRtStatus');
      if (el) el.textContent = msg.message || '';
    }
  });

  // ── Live panel updater ────────────────────────────────────────────────────
  function updateLivePanel(d) {
    const panel = $('liveRtPanel');
    if (!panel) return;
    panel.style.display = 'block';

    // Score number + color
    const scoreEl = $('liveRtScore');
    const score = d.score != null ? Math.round(d.score) : null;
    if (scoreEl && score != null) {
      scoreEl.textContent = score;
      scoreEl.style.color = score >= 80 ? '#10b981'
        : score >= 60 ? '#f59e0b'
        : score >= 40 ? '#f97316' : '#ef4444';
    }

    // Verdict
    const verdictEl = $('liveRtVerdict');
    if (verdictEl && d.verdict) {
      verdictEl.textContent = d.verdict;
      const col = d.verdict.includes('HIGHLY') ? '#ef4444'
        : d.verdict.includes('SUSPICIOUS') ? '#f97316'
        : d.verdict.includes('REVIEW') ? '#f59e0b' : '#10b981';
      verdictEl.style.color = col;
    }

    // LSDI bar
    const lsdiBar = $('liveRtLsdiBar');
    const lsdiVal = $('liveRtLsdiVal');
    if (lsdiBar && d.lsdi != null) {
      const pct = Math.min(100, d.lsdi);
      lsdiBar.style.width = pct + '%';
      lsdiBar.style.background = pct > 60 ? '#ef4444' : pct > 35 ? '#f59e0b' : '#10b981';
    }
    if (lsdiVal && d.lsdi != null) lsdiVal.textContent = d.lsdi.toFixed(1);

    // Words
    const wordsEl = $('liveRtWords');
    if (wordsEl && d.words != null) wordsEl.textContent = `${d.words} words`;

    // Status
    const statusEl = $('liveRtStatus');
    if (statusEl && d.verdict) statusEl.textContent = `Live • ${d.shift || ''} shift`;

    // Flag — show top one if present
    const flagEl = $('liveRtFlag');
    if (flagEl) {
      const topFlag = (d.flags || [])[0];
      if (topFlag) {
        flagEl.textContent = '⚡ ' + topFlag.slice(0, 90);
        flagEl.style.display = 'block';
      } else {
        flagEl.style.display = 'none';
      }
    }

    // Alert badge on Technical tab
    if (d.score != null && d.score < 60 && phase === 'TECHNICAL_REC') {
      addLiveAlert(d.shift || 'MODERATE', d.lsdi || 50, d.flags || []);
    }
  }

  // ── Startup ───────────────────────────────────────────────────────────────
  chrome.runtime.sendMessage({ type: 'SAI_GET_SRC' }, resp => {
    if (resp && (resp.src === 'tab' || resp.src === 'mic')) {
      setAudioSource(resp.src);
    } else {
      setAudioSource('tab');
    }
  });

  chrome.storage.local.get('sai_auth', r => {
    if (r.sai_auth && r.sai_auth.token) { auth = r.sai_auth; showApp(); }
    else showLogin();
  });
});