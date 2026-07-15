import cssText from "data-text:~/style.css"
import type { PlasmoCSConfig, PlasmoGetStyle } from "plasmo"
import React, { useState, useRef, useEffect } from "react"


export const config: PlasmoCSConfig = { matches: ["https://meet.google.com/*"] }
export const getStyle: PlasmoGetStyle = () => {
  const s = document.createElement("style")
  s.textContent = cssText + `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    .sh-root * { font-family:'Inter',sans-serif; box-sizing:border-box; }
    .sh-root { all:initial; }
    .sh-scroll::-webkit-scrollbar { width:3px; }
    .sh-scroll::-webkit-scrollbar-thumb { background:#334155; border-radius:99px; }
    @keyframes sh-pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    @keyframes sh-spin { to{transform:rotate(360deg)} }
    @keyframes sh-fadein { from{opacity:0;transform:translateY(-8px)} to{opacity:1;transform:translateY(0)} }
    .sh-pulse { animation:sh-pulse 2s infinite; }
    .sh-fadein { animation:sh-fadein 0.35s ease; }
    .sh-spin { animation:sh-spin .7s linear infinite; }
    .sh-input { width:100%;background:#ffffff08;border:1px solid #1e2d4a;border-radius:10px;padding:9px 12px;color:#e2e8f0;font-size:12px;font-family:'Inter',sans-serif;outline:none;transition:border-color .2s; }
    .sh-input:focus { border-color:#2563eb; }
    .sh-input::placeholder { color:#334155; }
  `
  return s
}

// ── Backend endpoints — tries HF Space first, falls back to local ─────────────
const HF_API  = "https://naagazz-interview-checker.hf.space"
const HF_WS   = "wss://naagazz-interview-checker.hf.space"
const LOC_API = "http://127.0.0.1:8000"
const LOC_WS  = "ws://127.0.0.1:8000"

let API = HF_API
let WS  = HF_WS
let backendLabel = "HF"

// Probe both endpoints on startup; use whichever responds first
async function resolveBackend() {
  // Try local first (faster if running locally)
  try {
    const r = await fetch(`${LOC_API}/health`, { signal: AbortSignal.timeout(1800) })
    if (r.ok) { API = LOC_API; WS = LOC_WS; backendLabel = "Local"; return }
  } catch (_) {}
  // Fall back to HF
  try {
    const r = await fetch(`${HF_API}/health`, { signal: AbortSignal.timeout(4000) })
    if (r.ok) { API = HF_API; WS = HF_WS; backendLabel = "HF"; return }
  } catch (_) {}
  backendLabel = "Offline"
}
resolveBackend()

// ── SPEECH FILTER ─────────────────────────────────────────────────────────────
const IGNORE_PREFIXES = [
  "http", "www.", "meet.google", "Join", "Copy link", "More options",
  "Mute", "Camera", "Present", "Raise hand", "Emoji", "React",
  "Leave call", "Turn", "Settings", "End call", "Share screen",
  "Add", "Chat", "People", "Activities", "Host", "You are",
  "Closed captions", "Caption", "0:", "1:", "2:", "3:", "4:",
  "AM", "PM", "SachhAI",
  // Meet UI panels that get scraped accidentally
  "Developing an extension", "An add-on", "Extensions frequently",
  "Afrikaans", "Albanian", "Amharic", "Bengali", "Bulgarian",
  "arrow_downward", "Jump to bottom", "Font size", "Font color",
  "Open caption settings", "format_size", "circle",
  "English (Australia)", "English (India)", "English (UK)",
  // Meet microphone / camera status strings
  "Your microphone is", "Your camera is", "Mic muted", "Camera off",
  "You are muted", "Microphone muted", "microphone is on", "microphone is off",
  "You're muted", "You're presenting", "You are presenting",
  "Hand raised", "Hand lowered", "Press Down Arrow",
  "Send a reaction", "Hover tray",
  // Meet notification banners / info toasts — these pass word checks but are NOT speech
  "Others might still see your full video",
  "Others might still see",
  "might still see your full video",
  "Your video is still on",
  "your full video",
  "screen sharing",
  "You're sharing",
  "Stop sharing",
  "Everyone can see",
  "Pin to your screen",
  "Pinned to your screen",
  "Pinned for you",
  "Everyone is muted",
  "No one else is here",
  "Someone joined",
  "Someone left",
  "Waiting for others",
  "Let others in",
  "Admit all",
  "View all",
  "Show all",
  "participants can see",
  "everyone in the call",
  "This message was sent",
  "Turn on captions",
  "Turn off captions",
  "Captions are on",
  "Captions are off",
  "Generating captions",
  "Caption language",
  "Live captions",
  "Not connected",
  "Reconnecting",
  "Poor connection",
  "Connection lost",
  "Network issues",
  "Background is blurred",
  "Background effect",
  "Visual effects",
  "noise cancellation",
  "Noise cancellation",
  // Pre-join / lobby screen strings
  "Ready to join",
  "ready to join",
  "Meeting details",
  "meeting details",
  "meeting_room",
  "This call is open to anyone",
  "call is open to anyone",
  "open to anyone",
  "Show more info",
  "Show less info",
  "visual_effects",
  "Backgrounds and effects",
  "backgrounds and effects",
  "If you must use an extension",
  "you can inject buttons",
  "browser-extension",
  "not officially supported",
  "inject buttons into",
  "This is not officially supported",
  "You reacted with",
  "reacted with",
  "reaction",
  // Picture-in-picture and active window prompts
  "Your Meet call is in another window",
  "Using picture-in-picture lets you stay in the call",
  "while you do other things",
  "Bring the call back here",
  "in another window",
  "Your Meet call",
  "picture-in-picture",
  "lets you stay in the call",
]

// Regex guard — catches Meet UI blobs that slip past prefix matching
const MEET_UI_REGEX = /ready to join|meeting details|meeting_room|open to anyone|show more info|visual_effects|backgrounds and effects|inject buttons|browser-extension|not officially supported|others might still|your full video|screen sharing|stop sharing|everyone (can|is) (see|muted)|someone (joined|left)|waiting for others|captions are (on|off)|poor connection|connection lost|noise cancellation|background (is blurred|effect)|visual effects|participants can see|everyone in the call|you reacted with|another window|picture-in-picture|bring the call back|stay in the call/i

// Common spoken English words — at least one must appear for speech detection
const COMMON_SPOKEN = /\b(i|we|the|a|is|was|are|have|had|so|and|but|that|it|my|our|you|this|which|for|with|be|they|not|been|at|by|from|or|an|as|do|can|will|one|if|also|just|actually|like|well|yeah|basically|kind|think|mean|know|feel|about|when|how|what|why|where|who|more|some|other|there|because|then|after|before|while|although|through|even|very|really|much|many|any|its|their|all|would|could|should|might|may|these|those|his|her|him|them|us|we|me|he|she|yes|no|okay|right|good|great|sure|need|want|make|get|use|see|go|back|work|build|run|help|try|show|set|add|new|up|out|into|over|on|in|at|to|of|and|or|but|so|yet|still|already|now|just|only|also|both|even|well|too|very|quite|rather|almost|often|never|always|sometimes|usually|first|last|next|other|same|different|own|each|every|few|much|more|most|some|any|all|both|each|few|less|many|much|no|other|several|some|such|most|own)\b/i

function looksLikeSpeech(text: string): boolean {
  if (!text) return false
  const t = text.trim()
  // Hard cap: captions are never > 4000 chars; allow shorter speech segments (length >= 3)
  if (t.length < 3 || t.length > 4000) return false
  // Must contain at least one word
  const words = t.split(/\s+/)
  if (words.length < 1) return false
  // Must have actual letters
  if (!/[a-zA-Z]{2,}/.test(t)) return false
  // Filter out short UI nouns by requiring a common spoken word only for ultra-short phrases (< 3 words)
  if (words.length < 3 && !COMMON_SPOKEN.test(t)) return false
  // Regex guard: catch Meet UI blobs regardless of word order
  if (MEET_UI_REGEX.test(t)) return false
  // Ignore UI strings via blocklist:
  // - Short entries (< 8 chars, single word): only block if text STARTS WITH it — prevents
  //   "Add" from blocking "I added a new feature" or "reaction" from nuking real speech.
  // - Long entries (phrases): use substring match as before.
  for (const p of IGNORE_PREFIXES) {
    if (p.length <= 7 && !p.includes(" ")) {
      // short single-word prefix — only block if text literally starts with it
      if (t.startsWith(p)) return false
    } else {
      // multi-word phrase or long token — safe to substring match
      if (t.startsWith(p) || t.toLowerCase().includes(p.toLowerCase())) return false
    }
  }
  // Ignore all-caps (buttons/labels)
  if (t === t.toUpperCase() && t.length > 4) return false
  // Ignore strings with too many special chars (URLs, code, language menus)
  const specialRatio = (t.match(/[^a-zA-Z0-9\s'.,?!\-()]/g) || []).length / t.length
  if (specialRatio > 0.20) return false
  // Ignore if > 90% words are capitalised (proper noun lists like language menus)
  const capsWords = words.filter(w => w.length > 3 && w[0] === w[0].toUpperCase() && w[0] !== w[0].toLowerCase())
  if (capsWords.length / words.length > 0.9 && words.length > 4) return false
  return true
}

function dedupKey(text: string): string {
  // Normalize: lowercase, strip punctuation, trim whitespace
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, " ").trim().slice(0, 80)
}

function clamp(v: number, a = 0, b = 100) { return Math.max(a, Math.min(b, v)) }

function Bar({ value, max = 100, color }: { value: number, max?: number, color: string }) {
  return (
    <div style={{ height: 3, background: "#1e293b", borderRadius: 99, overflow: "hidden", marginTop: 3 }}>
      <div style={{ width: `${clamp((value / max) * 100)}%`, height: "100%", background: color, borderRadius: 99, transition: "width .8s ease" }} />
    </div>
  )
}

function Pill({ text, bg, border, color }: { text: string, bg: string, border: string, color: string }) {
  return <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 99, background: bg, border: `1px solid ${border}`, color, fontSize: 9, fontWeight: 700, letterSpacing: 1 }}>{text}</span>
}

function Dropdown({ id, label, labelColor, open, onToggle, children }: {
  id: string; label: string; labelColor: string; open: boolean; onToggle: (id: string) => void; children: React.ReactNode
}) {
  return (
    <div style={{ marginBottom: 6 }}>
      <button
        onClick={() => onToggle(id)}
        style={{ width: "100%", display: "flex", justifyContent: "space-between", alignItems: "center", background: "transparent", border: `1px solid ${labelColor}20`, borderRadius: open ? "7px 7px 0 0" : 7, padding: "5px 9px", cursor: "pointer", color: labelColor, fontSize: 8, fontWeight: 700, letterSpacing: 0.8, textTransform: "uppercase" }}
      >
        {label}
        <span style={{ fontSize: 10, opacity: 0.7 }}>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div style={{ padding: "8px 10px", background: `${labelColor}06`, borderRadius: "0 0 7px 7px", border: `1px solid ${labelColor}15`, borderTop: "none" }}>
          {children}
        </div>
      )}
    </div>
  )
}

type Phase = "info" | "personal" | "profile" | "live" | "report"

interface Profile {
  formality_score: number; vocabulary_level: number; grammar_score: number;
  lexical_diversity: number; filler_ratio: number; avg_sentence_len: number;
  transition_density: number; word_count: number;
  flesch_kincaid?: number; gunning_fog?: number; passive_voice_ratio?: number;
  sentence_burstiness?: number; ai_boilerplate?: number; personal_pronoun_ratio?: number;
  ai_sentence_starters?: number;
}
interface LiveData {
  score: number; verdict: string; lsdi: number; style_shift: string;
  ml_prob: number | null; strong_signals: number; cosine_sim: number;
  confidence: string; conf_low: number; conf_high: number;
  // 14-parameter live metrics
  formality: number; vocabulary: number; grammar: number;
  lexical_diversity: number; filler_ratio: number; avg_sent_len: number; transition_density: number;
  flesch_kincaid: number; gunning_fog: number; passive_voice: number; sentence_burstiness: number; hedging: number;
  // v3 AI signal metrics
  ai_boilerplate: number; pronouns: number; ai_starters: number;
  // Baselines
  base_formality: number; base_vocabulary: number; base_grammar: number; base_filler: number;
  // Temporal drift
  drift_score: number; has_spike: boolean; drift_window: number;
  flags: string[]; summary: string;
  elapsed: number; total_words: number; session_drift: number | null;
  plagiarism_risk: number; plagiarism_signals: string[];
  timeline: Array<{ t: number; score: number; verdict: string }>;
  fairness_applied: boolean; analysis_mode: string;
}

const Logo = () => (
  <div style={{ width: 30, height: 30, borderRadius: 9, background: "linear-gradient(to top right, #1d4ed8, #3b82f6)", padding: 1, flexShrink: 0 }}>
    <div style={{ width: "100%", height: "100%", background: "#04060f", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="18" height="18" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="17" cy="16" rx="9" ry="6" stroke="#3b82f6" strokeWidth="2" fill="none"/>
        <circle cx="17" cy="16" r="3" fill="#1d4ed8"/>
        <polyline points="11,24 14,27 22,20" stroke="#3b82f6" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
      </svg>
    </div>
  </div>
)

const GLASS_BG = "radial-gradient(circle at top left, #1a0a2e, #04060f 40%, #0d1b2a 100%)"
const GLASS_BDR = "rgba(255,255,255,0.08)"

const vStyle = (v: string) => ({
  "GENUINE": { bg: GLASS_BG, bdr: "#064e3b", txt: "#10b981", glow: "#10b98120" },
  "NEEDS REVIEW": { bg: GLASS_BG, bdr: "#78350f", txt: "#f59e0b", glow: "#f59e0b20" },
  "SUSPICIOUS": { bg: GLASS_BG, bdr: "#9a3412", txt: "#f97316", glow: "#f9731620" },
  "HIGHLY SUSPICIOUS": { bg: GLASS_BG, bdr: "#7f1d1d", txt: "#ef4444", glow: "#ef444420" },
}[v] ?? { bg: GLASS_BG, bdr: GLASS_BDR, txt: "#94a3b8", glow: "transparent" })

const S = {
  card: (bdr: string, glow: string, bg: string) => ({
    position: "relative" as const,
    background: bg, border: `1px solid ${bdr}`, borderRadius: 18, overflow: "hidden",
    boxShadow: `0 0 40px ${glow},0 24px 80px rgba(0,0,0,.8)`, backdropFilter: "blur(24px)",
  }),
  hdr: { padding: "10px 14px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: `1px solid ${GLASS_BDR}`, background: "rgba(255,255,255,0.02)" },
  body: { padding: "14px" },
  lbl: { color: "#94a3b8", fontSize: 9, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase" as const, marginBottom: 4, display: "block" },
  btn: (bg: string, mt = 8) => ({ width: "100%", padding: "10px", border: "none", borderRadius: 10, background: bg, color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer", marginTop: mt }),
  row: { marginBottom: 7 },
  rl: { display: "flex", justifyContent: "space-between", alignItems: "center" },
}

function GlassCard({ children, bdr, glow, bg, style }: { children: React.ReactNode, bdr: string, glow: string, bg: string, style?: any }) {
  return (
    <div style={{ ...S.card(bdr, glow, bg), ...style }}>
      <div style={{ position: "absolute", top: -40, left: -40, width: 120, height: 120, background: "#1d4ed8", borderRadius: "50%", filter: "blur(50px)", opacity: 0.25, zIndex: 0, pointerEvents: "none" }} />
      <div style={{ position: "absolute", bottom: -40, right: -40, width: 120, height: 120, background: "#3b82f6", borderRadius: "50%", filter: "blur(50px)", opacity: 0.1, zIndex: 0, pointerEvents: "none" }} />
      <div style={{ position: "relative", zIndex: 1, width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
        {children}
      </div>
    </div>
  )
}

export default function MeetOverlay() {
  const [phase, setPhase] = useState<Phase>("info")
  const [visible, setVisible] = useState(true)
  const [candidateName, setCandidateName] = useState("")
  const [role, setRole] = useState("")
  const [personalText, setPersonalText] = useState("")
  // ── Interviewer auth — replaces free-text interviewer name field ──
  const [authToken, setAuthToken] = useState("")
  const [authUser, setAuthUser] = useState("")
  const [authDisplayName, setAuthDisplayName] = useState("")
  const [authRole, setAuthRole] = useState("")
  const [loginUsername, setLoginUsername] = useState("")
  const [loginPassword, setLoginPassword] = useState("")
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState("")
  const [isRec, setIsRec] = useState(false)
  const [recHint, setRecHint] = useState("")
  const [err, setErr] = useState("")
  const [loading, setLoading] = useState(false)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [profileMeta, setProfileMeta] = useState<any>(null)
  const [status, setStatus] = useState("")
  const [live, setLive] = useState<LiveData | null>(null)
  const [questions, setQuestions] = useState<string[]>([])
  const [plagRisk, setPlagRisk] = useState(0)
  const [plagVerdict, setPlagVerdict] = useState("")
  const [plagSignals, setPlagSignals] = useState<string[]>([])
  const [showQ, setShowQ] = useState(true)
  const [showFlags, setShowFlags] = useState(false)
  const [sessionLog, setSessionLog] = useState<LiveData[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [expanded, setExpanded] = useState(true)
  const [savedId, setSavedId] = useState("")
  const [openDropdown, setOpenDropdown] = useState<string | null>(null)
  const [showCcReminder, setShowCcReminder] = useState(false)
  // ── Recording mode: dual (HR + candidate, uses CC) | solo (candidate only, uses system audio) ──
  const [recordingMode, setRecordingMode] = useState<"dual" | "solo">("dual")
  // Manual tech text input (for testing without live CC captions)
  const [showManualTech, setShowManualTech] = useState(false)
  const [manualTechDraft, setManualTechDraft] = useState("")
  // Calibration progress (words collected before baseline locks)
  const [calibWords, setCalibWords] = useState(0)
  const [baselineLocked, setBaselineLocked] = useState(false)
  // Backend label (HF / Local / Offline)
  const [beLabel, setBeLabel] = useState("…")
  // ── Credibility checker ───────────────────────────────────────────────────
  interface CredResult {
    question: string
    verdict: "CORRECT" | "PARTIALLY" | "INCORRECT" | "INSUFFICIENT"
    score: number
    confidence: number
    explanation: string
    key_points_hit: string[]
    key_points_missed: string[]
    suggestions: string
    timestamp: number
  }
  const [credResults, setCredResults] = useState<CredResult[]>([])
  const [credLoading, setCredLoading] = useState(false)
  const [credQuestion, setCredQuestion] = useState("")
  const [showCred, setShowCred] = useState(false)
  const credInputRef = useRef<HTMLInputElement | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const lastCapRef = useRef("")
  const timerRef = useRef<any>(null)
  const startRef = useRef(0)
  const pTextRef = useRef("")
  const qThrotRef = useRef(0)
  const speechRef = useRef<any>(null)
  // BUG FIX: ref for manual caption input (getElementById fails in shadow DOM)
  const manualInputRef = useRef<HTMLInputElement | null>(null)
  // BUG FIX: flag to stop WS reconnect loop after interview ends
  const stoppedRef = useRef(false)
  // Accumulate full technical transcript for post-session deep analysis
  const techTranscriptRef = useRef("")
  const transcriptRef = useRef("")
  const [transcript, setTranscript] = useState("")
  const scoringTimerRef = useRef<any>(null)
  const audioCtxRef = useRef<any>(null)
  const audioProcRef = useRef<any>(null)
  const seenTextsRef = useRef<Set<string>>(new Set())
  const pollRef = useRef<any>(null)
  const obsRef = useRef<MutationObserver | null>(null)
  // MediaRecorder-based personal recording
  const mediaRecRef   = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const analyserRef   = useRef<AnalyserNode | null>(null)
  const animFrameRef  = useRef<number>(0)
  const waveCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [recSecs, setRecSecs] = useState(0)
  const recTimerRef = useRef<any>(null)
  // Solo mode: system audio stream + Deepgram WebSocket for real-time candidate STT
  const soloStreamRef = useRef<MediaStream | null>(null)
  const soloWsRef = useRef<WebSocket | null>(null)
  const soloMrRef = useRef<MediaRecorder | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
      if (scoringTimerRef.current) clearInterval(scoringTimerRef.current)
      if (obsRef.current) { obsRef.current.disconnect(); obsRef.current = null }
      if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null }
      stopSoloCapture()
    }
  }, [])

  // ── Solo mode system audio capture helpers ────────────────────────────────
  const stopSoloCapture = () => {
    try { soloMrRef.current?.stop() } catch (_) {}
    try { soloWsRef.current?.close() } catch (_) {}
    try { soloStreamRef.current?.getTracks().forEach(t => t.stop()) } catch (_) {}
    try { audioProcRef.current?.disconnect() } catch (_) {}
    try { audioCtxRef.current?.close() } catch (_) {}
    audioProcRef.current = null
    audioCtxRef.current = null
    soloMrRef.current = null
    soloWsRef.current = null
    soloStreamRef.current = null
  }

  const startSoloCapture = async () => {
    // Prompt user to share the Meet tab audio (system audio = candidate's voice)
    let stream: MediaStream
    try {
      // Chrome requires video:true — audio-only getDisplayMedia is NOT supported.
      // We request both, then immediately mute/discard the video track.
      stream = await (navigator.mediaDevices as any).getDisplayMedia({
        video: { frameRate: 1, width: 1, height: 1 },   // minimal video — we don't use it
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          sampleRate: 16000,
        },
      })
      // Stop video tracks immediately — we only need audio
      stream.getVideoTracks().forEach(t => { t.enabled = false; t.stop() })
    } catch (e: any) {
      const msg = e?.message || String(e)
      if (e?.name === "NotAllowedError" || e?.name === "PermissionDeniedError") {
        setStatus("Solo mode: screen share cancelled — click Start Interview and allow tab share")
      } else if (e?.name === "NotSupportedError" || msg.includes("Not supported")) {
        setStatus("Solo mode not supported in this browser. Use Dual Mode with CC instead.")
      } else {
        setStatus(`Solo mode: could not capture audio — ${msg}`)
      }
      return
    }
    soloStreamRef.current = stream
    // Build Deepgram real-time WebSocket (same as personal mic recording)
    const DG_WS_URL = `wss://api.deepgram.com/v1/listen?model=nova-2&language=en&punctuate=true&interim_results=false&endpointing=300&vad_events=false&encoding=linear16&sample_rate=16000&channels=1`
    const DEEPGRAM_KEY = "5e0f6a21c7ff5a576e38c87c99e6db10e55c4090"
    const dg = new WebSocket(DG_WS_URL, ["token", DEEPGRAM_KEY])
    soloWsRef.current = dg

    dg.onopen = () => {
      setStatus("Solo mode: Deepgram listening to candidate audio…")
      // Stream mic audio via MediaRecorder → binary chunks to Deepgram
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm"
      // Convert to 16-bit PCM using AudioContext
      const AudioCtx = (window as any).AudioContext || (window as any).webkitAudioContext
      if (!AudioCtx) { setStatus("Solo: AudioContext not available"); return }
      const ctx = new AudioCtx({ sampleRate: 16000 })
      audioCtxRef.current = ctx
      const src = ctx.createMediaStreamSource(stream)
      const proc = ctx.createScriptProcessor(4096, 1, 1)
      audioProcRef.current = proc
      proc.onaudioprocess = (e: any) => {
        if (stoppedRef.current) { proc.disconnect(); ctx.close(); return }
        if (dg.readyState !== WebSocket.OPEN) return
        const f32 = e.inputBuffer.getChannelData(0)
        // Convert Float32 → Int16
        const buf = new Int16Array(f32.length)
        for (let i = 0; i < f32.length; i++) buf[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768))
        dg.send(buf.buffer)
      }
      src.connect(proc)
      proc.connect(ctx.destination)
    }

    dg.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data)
        const transcriptText = msg?.channel?.alternatives?.[0]?.transcript?.trim()
        if (transcriptText && msg?.is_final) {
          // Send to analysis WebSocket just like CC captions would
          lastCapRef.current = transcriptText
          techTranscriptRef.current = (techTranscriptRef.current.trim() + " " + transcriptText).trim()
          transcriptRef.current = (transcriptRef.current.trim() + " " + transcriptText).trim()
          setTranscript(transcriptRef.current)
          const key = dedupKey(transcriptText)
          if (!seenTextsRef.current.has(key)) {
            seenTextsRef.current.add(key)
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({ type: "transcript", text: transcriptText, speaker: "Candidate" }))
            }
          }
        }
      } catch (_) {}
    }

    dg.onerror = () => setStatus("Solo: Deepgram connection error")
    dg.onclose = () => {
      if (!stoppedRef.current) setStatus("Solo: Deepgram disconnected — audio may have stopped")
    }

    // If user stops sharing the tab, clean up
    stream.getTracks().forEach(t => t.onended = () => {
      stopSoloCapture()
      setStatus("Solo mode: screen share stopped")
    })
  }

  // ── Auth headers helper ─────────────────────────────────────────────────────
  const authHeaders = () => ({
    "Content-Type": "application/json",
    ...(authToken ? { "Authorization": `Bearer ${authToken}`, "X-Username": authUser, "X-Role": authRole } : {})
  })

  // ── Login ──────────────────────────────────────────────────────────────
  const doLogin = async (u?: string, p?: string) => {
    const finalUser = (u !== undefined ? u : loginUsername).trim()
    const finalPass = p !== undefined ? p : loginPassword
    if (!finalUser || !finalPass) {
      setLoginError("Enter both username and password")
      return
    }
    setLoginLoading(true)
    setLoginError("")
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: finalUser, password: finalPass }),
      })
      if (r.status === 401) {
        setLoginError("⛔ Unauthorized — this account is not registered or the password is incorrect. Access denied.")
        setLoginLoading(false)
        return
      }
      if (!r.ok) {
        setLoginError(`Server error (${r.status}) — try again`)
        setLoginLoading(false)
        return
      }
      const j = await r.json()
      setAuthToken(j.token)
      setAuthUser(j.username)
      setAuthDisplayName(j.display_name || j.username)
      setAuthRole(j.role)
      setLoginUsername("")
      setLoginPassword("")  // clear password from memory
      setLoginError("")
    } catch (e: any) {
      setLoginError(`Could not reach server — ${e?.message || e}`)
    }
    setLoginLoading(false)
  }
  useEffect(() => {
    // Read initial persisted state
    try {
      chrome.storage.local.get("sachhAI_enabled", (r) => {
        if (r.sachhAI_enabled === false) setVisible(false)
      })
    } catch (_) { }

    const handler = (msg: any) => {
      if (msg?.type === "SACHHÁI_TOGGLE") setVisible(msg.enabled)
    }
    try { chrome.runtime.onMessage.addListener(handler) } catch (_) { }
    return () => {
      try { chrome.runtime.onMessage.removeListener(handler) } catch (_) { }
    }
  }, [])

  // Personal phase: CC auto-capture DISABLED.
  // Personal baseline text ONLY comes from the Deepgram mic recording below.
  // The observer was previously picking up random DOM text before the user clicked Record.
  // useEffect removed intentionally.

  // ── Personal phase recording — MediaRecorder → Deepgram Nova-2 (accurate STT) ──

  // Draw live waveform on canvas while recording
  const drawWave = () => {
    const analyser = analyserRef.current
    const canvas   = waveCanvasRef.current
    if (!analyser || !canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const buf = new Uint8Array(analyser.frequencyBinCount)
    analyser.getByteTimeDomainData(buf)
    const W = canvas.width, H = canvas.height
    ctx.clearRect(0, 0, W, H)
    ctx.lineWidth   = 1.5
    ctx.strokeStyle = "#3b82f6"
    ctx.shadowColor = "#3b82f6"
    ctx.shadowBlur  = 6
    ctx.beginPath()
    const step = W / buf.length
    for (let i = 0; i < buf.length; i++) {
      const y = (buf[i] / 128) * (H / 2)
      if (i === 0) ctx.moveTo(0, y); else ctx.lineTo(i * step, y)
    }
    ctx.stroke()
    animFrameRef.current = requestAnimationFrame(drawWave)
  }

  const startRec = async () => {
    setErr("")
    setRecSecs(0)
    try {
      // ── Audio source: solo = system audio (candidate speaker), dual = HR mic ──
      let stream: MediaStream
      if (recordingMode === "solo") {
        try {
          // Chrome requires video:true — audio-only getDisplayMedia is NOT supported.
          // Request both, immediately discard video track.
          stream = await (navigator.mediaDevices as any).getDisplayMedia({
            video: { frameRate: 1, width: 1, height: 1 },
            audio: { echoCancellation: false, noiseSuppression: false, sampleRate: 48000 },
          })
          // Stop video track immediately — audio only needed
          stream.getVideoTracks().forEach(t => { t.enabled = false; t.stop() })
        } catch (e: any) {
          const msg = e?.message || String(e)
          if (e?.name === "NotAllowedError" || e?.name === "PermissionDeniedError") {
            setErr("Screen share cancelled. In Solo Mode you must share the Meet tab to capture candidate audio.")
          } else if (e?.name === "NotSupportedError" || msg.includes("Not supported")) {
            setErr("System audio capture is not supported in this browser. Switch to Dual Mode and use Meet CC.")
          } else {
            setErr(`Could not capture system audio: ${msg}`)
          }
          return
        }
      } else {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1, sampleRate: 48000 }
        })
      }

      // Build analyser for waveform visualisation
      const AudioCtx = (window as any).AudioContext || (window as any).webkitAudioContext
      if (AudioCtx) {
        const ctx   = new AudioCtx()
        const src   = ctx.createMediaStreamSource(stream)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        src.connect(analyser)
        analyserRef.current = analyser
        animFrameRef.current = requestAnimationFrame(drawWave)
      }

      // Pick best supported codec
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : ""

      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
      audioChunksRef.current = []

      mr.ondataavailable = (e: any) => {
        if (e.data && e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      mr.onstop = async () => {
        cancelAnimationFrame(animFrameRef.current)
        stream.getTracks().forEach(t => t.stop())
        if (recTimerRef.current) clearInterval(recTimerRef.current)

        const blob = new Blob(audioChunksRef.current, { type: mime || "audio/webm" })
        if (blob.size < 1000) {
          setRecHint("Recording too short — try again and record for at least 5 seconds")
          setIsRec(false)
          return
        }

        setIsRec(false)
        setIsTranscribing(true)
        setRecHint("⏳ Transcribing with Deepgram Nova-2… this takes a few seconds")

        try {
          const fd = new FormData()
          fd.append("audio", blob, "personal.webm")
          fd.append("type", "personal")
          const res = await fetch(`${API}/voice/transcribe-chunk`, { method: "POST", body: fd })
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = await res.json()
          const text = (data.text || "").trim()
          if (text) {
            setPersonalText(prev => (prev.trimEnd() ? prev.trimEnd() + " " : "") + text)
            const wc = text.split(/\s+/).filter(Boolean).length
            setRecHint(`✓ Transcribed ${wc} words via Deepgram — review and edit below, then click Analyze`)
          } else {
            setRecHint("No speech detected — make sure the candidate was speaking and audio was audible")
          }
        } catch (err: any) {
          setRecHint(`Transcription failed (${err?.message || err}) — type the intro manually below`)
        }
        setIsTranscribing(false)
      }

      // Stop stream if user ends screen share mid-recording (solo mode)
      stream.getTracks().forEach(t => {
        t.onended = () => {
          if (mediaRecRef.current && mediaRecRef.current.state !== "inactive") {
            mediaRecRef.current.stop()
          }
        }
      })

      mr.start(250)
      mediaRecRef.current = mr
      setIsRec(true)
      setRecHint(
        recordingMode === "solo"
          ? "🔊 Recording candidate audio from speakers — click Stop when their intro is done"
          : "🔴 Recording… speak your intro, background, hobbies — click Stop when done"
      )

      recTimerRef.current = setInterval(() => setRecSecs(s => s + 1), 1000)

    } catch (e: any) {
      if (e?.name === "NotAllowedError" || e?.name === "PermissionDeniedError") {
        setErr("Permission denied. Allow microphone access in Chrome then try again.")
      } else {
        setErr(`Could not start recording: ${e?.message || e}`)
      }
    }
  }

  const stopRec = () => {
    if (mediaRecRef.current && mediaRecRef.current.state !== "inactive") {
      mediaRecRef.current.stop()
      mediaRecRef.current = null
    }
    cancelAnimationFrame(animFrameRef.current)
    if (recTimerRef.current) { clearInterval(recTimerRef.current); recTimerRef.current = null }
    // onstop callback handles the rest
  }

  // ── Analyze personal text ─────────────────────────────────────────────────
  const analyzePersonal = async () => {
    setErr("")
    const wc = personalText.trim().split(/\s+/).filter(Boolean).length
    if (wc < 15) { setErr("Need at least 15 words. Record or type above."); return }
    setLoading(true)
    try {
      const r = await fetch(`${API}/voice/analyze-personal`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: personalText.trim(), role }) })
      const d = await r.json()
      if (d.status === "ok") { setProfile(d.profile); setProfileMeta(d); pTextRef.current = personalText.trim(); setPhase("profile") }
      else setErr(d.message || "Analysis failed")
    } catch (e) {
      setErr(`Backend unreachable at ${API}\nRun: cd backend && uvicorn server:app --reload`)
    }
    setLoading(false)
  }

  // ── Start live technical phase ─────────────────────────────────────────────
  const startLive = () => {
    stoppedRef.current = false
    setPhase("live")
    setCalibWords(0)
    setBaselineLocked(false)
    setBeLabel(backendLabel)
    transcriptRef.current = ""
    setTranscript("")
    setStatus("Listening... (0/50 words needed)")
    
    // Solo mode: skip CC reminder, start system audio capture instead
    if (recordingMode === "solo") {
      setShowCcReminder(false)
      // startSoloCapture runs after WS connects (called below)
    } else {
      setShowCcReminder(true)
    }
    
    // Clear any active observer/poll from a previous session first
    if (pollRef.current) clearInterval(pollRef.current)
    if (scoringTimerRef.current) clearInterval(scoringTimerRef.current)
    if (obsRef.current) {
      obsRef.current.disconnect()
      obsRef.current = null
    }
    seenTextsRef.current.clear()

    startRef.current = Date.now()
    timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000)

    const runCompareCycle = async () => {
      const text = transcriptRef.current.trim()
      const wordCount = text.split(/\s+/).filter(Boolean).length
      if (wordCount < 50) {
        setStatus(`Listening... (${wordCount}/50 words needed)`)
        return
      }
      
      let attempts = 0
      const maxAttempts = 3
      const backoffMs = 5000
      
      const tryFetch = async (): Promise<boolean> => {
        try {
          const resp = await fetch(`${API}/voice/text-compare`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
              candidate_id: candidateName,
              personal: personalText,
              technical: text
            })
          })
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`)
          }
          const j = await resp.json()
          if (j && j.analysis) {
            const m = j.analysis
            setBaselineLocked(true)
            setLive(m)
            setSessionLog(p => [...p.slice(-200), m])
            if (m.plagiarism_risk !== undefined) setPlagRisk(m.plagiarism_risk)
            if (m.plagiarism_signals) setPlagSignals(m.plagiarism_signals)
            const pr = m.plagiarism_risk || 0
            setPlagVerdict(pr >= 60 ? "HIGH RISK — Likely reading from script" : pr >= 35 ? "MODERATE RISK — Some scripted elements" : "CLEAN")
            if (Array.isArray(m.followup_questions) && m.followup_questions.length > 0) {
              setQuestions(m.followup_questions)
            }
            setStatus(`Analysis updated (${wordCount} words)`)
            return true
          }
          return false
        } catch (e: any) {
          attempts++
          console.warn(`[Scoring cycle] Attempt ${attempts} failed:`, e)
          if (attempts < maxAttempts) {
            setStatus("Score unavailable — retrying…")
            await new Promise(r => setTimeout(r, backoffMs))
            return tryFetch()
          } else {
            setStatus("Score unavailable — retrying")
            return false
          }
        }
      }
      
      await tryFetch()
    }

    scoringTimerRef.current = setInterval(runCompareCycle, 8000)

    const tryConnect = (wsUrl: string) => {
      if (stoppedRef.current) return
      // Clean up previous socket if it exists and is open
      if (wsRef.current) {
        try {
          wsRef.current.onclose = null
          wsRef.current.close()
        } catch (_) {}
      }
      const ws = new WebSocket(`${wsUrl}/voice/meet-analyze?token=${encodeURIComponent(authToken)}`)
      ws.onopen = () => {
        setStatus(`Connected (${backendLabel}) · waiting for captions…`)
        setBeLabel(backendLabel)
        ws.send(JSON.stringify({ type: "baseline", text: pTextRef.current }))
        if (techTranscriptRef.current.trim()) {
          ws.send(JSON.stringify({ type: "transcript", text: techTranscriptRef.current.trim(), speaker: "Candidate" }))
        }
      }
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data)
          if (m.type === "analysis") {
            setBaselineLocked(true)
            setLive(m)
            setSessionLog(p => [...p.slice(-200), m])
            if (m.plagiarism_risk !== undefined) setPlagRisk(m.plagiarism_risk)
            if (m.plagiarism_signals) setPlagSignals(m.plagiarism_signals)
            const pr = m.plagiarism_risk || 0
            setPlagVerdict(pr >= 60 ? "HIGH RISK — Likely reading from script" : pr >= 35 ? "MODERATE RISK — Some scripted elements" : "CLEAN")
            // Real-time: always update follow-up questions from the WebSocket analysis payload
            if (Array.isArray(m.followup_questions) && m.followup_questions.length > 0) {
              setQuestions(m.followup_questions)
            }
            // Also run the HTTP enrichment every 15s for additional context-aware questions
            const now = Date.now()
            if (now - qThrotRef.current > 15000) { qThrotRef.current = now; fetchQ(m) }
          } else if (m.type === "status") {
            setStatus(m.message || "Active")
            // Parse calibration word count from status message
            const match = /\((\d+)\/(\d+) words\)/.exec(m.message || "")
            if (match) {
              setCalibWords(parseInt(match[1]))
            } else if ((m.message || "").includes("locked") || (m.message || "").includes("active")) {
              setBaselineLocked(true)
              setCalibWords(40)
            }
          }
          else if (m.type === "error") setStatus(`${m.message}`)
        } catch (_) { }
      }
      ws.onclose = () => {
        if (!stoppedRef.current) {
          setStatus("Reconnecting…")
          setTimeout(() => tryConnect(wsUrl), 3000)
        }
      }
      wsRef.current = ws
    }

    // Connect — use whichever backend resolved on startup
    tryConnect(WS)

    // Solo mode: start system audio capture after a short delay (WS needs to connect first)
    if (recordingMode === "solo") {
      setTimeout(() => {
        if (!stoppedRef.current) startSoloCapture()
      }, 1500)
      // In solo mode, skip CC observer — audio capture handles everything
      return
    }

    // ── CC-aware text capture — finality-gated ─────────────────────────────
    // Google Meet CC captions are incremental: each ASR tick appends a word.
    // We only send a "sentence" to the backend when it is FINAL — detected by:
    //   a) sentence-ending punctuation (. ? !), OR
    //   b) the new CC line is NOT a prefix/extension of the previous line
    //      (meaning the ASR engine committed the previous sentence and started fresh)
    //
    // For personal phase the MutationObserver is disabled; personal text comes
    // exclusively from the Deepgram mic recording (no observer noise).

    // Tracking for incremental updates
    let lastSentText = ""
    let flushTimer: ReturnType<typeof setTimeout> | null = null

    const sendFinal = (text: string) => {
      if (!text.trim() || !looksLikeSpeech(text)) return
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "transcript", text, speaker: "Candidate" }))
      }
    }

    const processCC = (rawText: string) => {
      const text = rawText.trim()
      if (!text || text.length < 5) return
      if (!looksLikeSpeech(text)) return

      // Split words to calculate suffix difference since lastSentText
      const lastSentWords = lastSentText.toLowerCase().split(/\s+/).filter(Boolean)
      const currentWords = text.toLowerCase().split(/\s+/).filter(Boolean)

      // Find maximum overlap between the end of lastSentWords and start of currentWords
      let bestK = 0
      for (let k = Math.min(lastSentWords.length, currentWords.length); k > 0; k--) {
        const sliceOld = lastSentWords.slice(-k)
        const sliceNew = currentWords.slice(0, k)
        if (sliceOld.join(" ") === sliceNew.join(" ")) {
          bestK = k
          break
        }
      }

      const newWordsSuffix = text.split(/\s+/).filter(Boolean).slice(bestK)
      const endsWithPunc = /[.?!]$/.test(text)

      // Send immediately if we have >= 3 new words, or if the speaker hit a punctuation boundary
      if (newWordsSuffix.length >= 3 || (endsWithPunc && newWordsSuffix.length > 0)) {
        if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
        sendFinal(text)

        // Append only the new suffix words to client-side session transcript
        const suffixStr = newWordsSuffix.join(" ")
        techTranscriptRef.current = (techTranscriptRef.current.trim() + " " + suffixStr).trim()
        transcriptRef.current = (transcriptRef.current.trim() + " " + suffixStr).trim()
        setTranscript(transcriptRef.current)
        lastCapRef.current = suffixStr

        lastSentText = text
      } else {
        // Fallback: if they stop speaking but haven't reached 3 words, flush after 1.5 seconds of silence
        if (flushTimer) clearTimeout(flushTimer)
        flushTimer = setTimeout(() => {
          const currentWordsNow = text.toLowerCase().split(/\s+/).filter(Boolean)
          let bestKNow = 0
          for (let k = Math.min(lastSentWords.length, currentWordsNow.length); k > 0; k--) {
            if (lastSentWords.slice(-k).join(" ") === currentWordsNow.slice(0, k).join(" ")) {
              bestKNow = k
              break
            }
          }
          const suffixNow = text.split(/\s+/).filter(Boolean).slice(bestKNow)
          if (suffixNow.length > 0) {
            sendFinal(text)
            const suffixStr = suffixNow.join(" ")
            techTranscriptRef.current = (techTranscriptRef.current.trim() + " " + suffixStr).trim()
            transcriptRef.current = (transcriptRef.current.trim() + " " + suffixStr).trim()
            setTranscript(transcriptRef.current)
            lastCapRef.current = suffixStr
            lastSentText = text
          }
          flushTimer = null
        }, 1500)
      }
    }

    // ── Target Google Meet CC aria-live regions specifically ─────────────────
    // Meet renders captions inside [aria-live] containers — targeting these
    // prevents capturing button labels, tooltips, and other UI chrome.
    //
    // IMPORTANT: Meet has MULTIPLE aria-live regions (notifications, status,
    // and actual captions). We must pick the LONGEST text across all matches —
    // that is almost always the real caption container, not a short toast/status.
    const CC_SELECTORS = [
      "[aria-live='polite']",
      "[aria-live='assertive']",
      "[aria-label='Captions']",
      "[aria-label='captions']",
      "[role='region'][aria-label='Captions']",
      "[data-message-text]",
      ".a4cQT",   // Meet CC container class (changes with UI updates; kept as hint)
      ".iOzk7",   // alternate CC span class observed in 2025 Meet builds
      ".TBMuR",   // another observed caption wrapper
    ]

    const extractCCText = (): string => {
      // Collect text from ALL CC selector matches and pick the longest — this
      // avoids the bug where a short notification aria-live region wins over the
      // actual multi-word caption container that appears later in the DOM.
      let best = ""
      for (const sel of CC_SELECTORS) {
        const els = document.querySelectorAll(sel)
        els.forEach(el => {
          const t = ((el as HTMLElement).innerText || el.textContent || "").trim()
          // Only consider text that looks like speech (filters out UI labels)
          if (t.length > best.length && looksLikeSpeech(t)) best = t
        })
      }
      // Fallback: walk all aria-live elements and take the longest speech-like one
      if (!best) {
        document.querySelectorAll("[aria-live]").forEach(el => {
          const t = ((el as HTMLElement).innerText || el.textContent || "").trim()
          if (t.length > best.length && looksLikeSpeech(t)) best = t
        })
      }
      return best
    }

    // MutationObserver — watch for CC text changes only
    const obs = new MutationObserver((mutations) => {
      if (stoppedRef.current) return
      for (const mut of mutations) {
        // Check if this mutation is inside a CC container
        let target: Node | null = mut.target
        let inCC = false
        while (target) {
          if (target.nodeType === Node.ELEMENT_NODE) {
            const el = target as HTMLElement
            const ariaLive = el.getAttribute?.("aria-live")
            const ariaLabel = el.getAttribute?.("aria-label")
            const role = el.getAttribute?.("role")
            if (
              ariaLive === "polite" ||
              ariaLive === "assertive" ||
              el.hasAttribute?.("data-message-text") ||
              ariaLabel?.toLowerCase() === "captions" ||
              (role === "region" && ariaLabel?.toLowerCase() === "captions") ||
              el.classList?.contains("a4cQT") ||
              el.classList?.contains("iOzk7") ||
              el.classList?.contains("TBMuR")
            ) {
              inCC = true
              break
            }
          }
          target = target.parentNode
        }

        if (inCC) {
          // Extract the full text of this CC region
          let ccEl: Node | null = mut.target
          while (ccEl?.parentNode) {
            const el = ccEl as HTMLElement
            const ariaLive = el.getAttribute?.("aria-live")
            const ariaLabel = el.getAttribute?.("aria-label")
            const role = el.getAttribute?.("role")
            if (
              ariaLive || 
              ariaLabel?.toLowerCase() === "captions" || 
              (role === "region" && ariaLabel?.toLowerCase() === "captions")
            ) break
            ccEl = ccEl.parentNode
          }
          const fullText = ((ccEl as HTMLElement)?.innerText || (ccEl as HTMLElement)?.textContent || "").trim()
          if (fullText) processCC(fullText)
        }
      }
    })

    obs.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    })
    obsRef.current = obs

    // Polling fallback — reads CC regions every 800ms as a safety net
    let lastPollSnapshot = ""
    const poll = setInterval(() => {
      if (stoppedRef.current) { clearInterval(poll); return }
      const cc = extractCCText()
      if (cc && cc !== lastPollSnapshot) {
        lastPollSnapshot = cc
        processCC(cc)
      }
    }, 800)
    pollRef.current = poll
  }

  // Manual caption send (shadow DOM safe — reads from ref, not getElementById)
  const sendManual = (text: string) => {
    if (!text.trim()) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatus("Not connected — start the interview first")
      return
    }
    lastCapRef.current = text
    techTranscriptRef.current += " " + text
    wsRef.current.send(JSON.stringify({ type: "transcript", text: text.trim(), speaker: "Candidate" }))
  }

  // Send full manual tech text block, chunked into 30-word segments so
  // the backend processes it exactly as if it arrived from live captions
  const sendManualTechBlock = (fullText: string) => {
    if (!fullText.trim()) return
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setStatus("Not connected — start the interview first")
      return
    }
    const words = fullText.trim().split(/\s+/)
    const CHUNK = 30
    let i = 0
    const sendNext = () => {
      if (i >= words.length) {
        setStatus("✓ All manual text sent — analyzing…")
        return
      }
      const chunk = words.slice(i, i + CHUNK).join(" ")
      i += CHUNK
      techTranscriptRef.current += " " + chunk
      lastCapRef.current = chunk
      if (wsRef.current?.readyState === WebSocket.OPEN)
        wsRef.current.send(JSON.stringify({ type: "transcript", text: chunk, speaker: "Candidate" }))
      setTimeout(sendNext, 400)  // stagger chunks 400ms apart
    }
    sendNext()
    setManualTechDraft("")
    setShowManualTech(false)
    setStatus("Sending manual text…")
  }

  // ── Credibility check: send current question + last transcript to backend ──
  const checkCredibility = async () => {
    const q = credQuestion.trim()
    if (!q) return
    // Use last 200 words of candidate transcript as the response
    const words = techTranscriptRef.current.trim().split(/\s+/).filter(Boolean)
    const recentTranscript = words.slice(-200).join(" ")
    if (recentTranscript.split(/\s+/).length < 5) {
      setStatus("Not enough candidate speech captured yet to check credibility")
      return
    }
    setCredLoading(true)
    try {
      const r = await fetch(`${API}/voice/check-credibility`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...( authToken ? { "Authorization": `Bearer ${authToken}`, "X-Username": authUser } : {}) },
        body: JSON.stringify({
          candidate_id: savedId || candidateName || "",
          items: [{ question: q, candidate_response: recentTranscript }]
        })
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const j = await r.json()
      const res = j.results?.[0]
      if (res) {
        setCredResults(prev => [{
          question: q,
          verdict: res.verdict,
          score: res.score ?? 0,
          confidence: res.confidence ?? 0,
          explanation: res.explanation ?? "",
          key_points_hit: res.key_points_hit ?? [],
          key_points_missed: res.key_points_missed ?? [],
          suggestions: res.suggestions ?? "",
          timestamp: Date.now()
        }, ...prev.slice(0, 9)])
        setCredQuestion("")
        if (credInputRef.current) credInputRef.current.value = ""
      }
    } catch (e: any) {
      setStatus(`Credibility check failed: ${e?.message || e}`)
    }
    setCredLoading(false)
  }

  const fetchQ = async (d: LiveData) => {
    try {
      const words = techTranscriptRef.current.trim().split(/\s+/).filter(Boolean);
      const rollingTranscript = words.slice(-200).join(" ");
      const r = await fetch(`${API}/voice/suggest-questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: rollingTranscript,
          flags: d.flags,
          hedging: d.hedging ?? 0.0,
          passive_voice: d.passive_voice ?? 0.0,
          formality_drop: (profile?.formality_score || 0) - d.formality,
          vocabulary_drop: (profile?.vocabulary_level || 0) - d.vocabulary,
          role
        })
      })
      const j = await r.json()
      if (j.status === "ok") setQuestions(j.questions)
    } catch (_) { }
  }


  const closeOverlay = async () => {
    stoppedRef.current = true
    stopSoloCapture()
    
    if (timerRef.current) clearInterval(timerRef.current)
    if (pollRef.current) clearInterval(pollRef.current)
    if (scoringTimerRef.current) clearInterval(scoringTimerRef.current)
    if (recTimerRef.current) clearInterval(recTimerRef.current)
    if (obsRef.current) {
      obsRef.current.disconnect()
      obsRef.current = null
    }
    
    if (wsRef.current) {
      try {
        wsRef.current.onclose = null
        wsRef.current.close()
      } catch (_) {}
      wsRef.current = null
    }
    
    try {
      chrome.runtime.sendMessage({ type: "SAI_SESSION_END" }).catch(() => {})
      chrome.storage.local.set({ sachhAI_enabled: false }).catch(() => {})
    } catch (_) {}
    
    try {
      const payload = {
        candidate_name: candidateName || "Unknown Candidate",
        interviewer_name: authDisplayName || authUser || "Unknown Interviewer",
        role: role || "N/A",
        duration_s: elapsed,
        final_score: 0.0,
        verdict: "cancelled",
        strong_signals: 0,
        flags: ["Interview cancelled by user."],
        questions: [],
        plagiarism_risk: 0,
        summary: "The interview session was cancelled by the interviewer before completion.",
        personal_text: personalText || "",
        technical_text: transcriptRef.current || "",
        personal_profile: {},
        technical_profile: {}
      }
      await fetch(`${API}/voice/save-session`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload)
      })
    } catch (e) {
      console.error("Failed to save cancelled session status:", e)
    }
    
    setVisible(false)
  }

  const endInterview = () => {
    stoppedRef.current = true     // BUG FIX: prevent WS auto-reconnect
    if (timerRef.current) clearInterval(timerRef.current)
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    if (scoringTimerRef.current) { clearInterval(scoringTimerRef.current); scoringTimerRef.current = null }
    if (obsRef.current) { obsRef.current.disconnect(); obsRef.current = null }
    if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null }
    stopSoloCapture()  // stop system audio stream if solo mode
    setPhase("report")
    saveSession()
  }

  const saveSession = async () => {
    let last = sessionLog.length > 0 ? sessionLog[sessionLog.length - 1] : null
    if (!last) {
      last = {
        score: profile?.formality_score ?? 50,
        verdict: "INCOMPLETE",
        strong_signals: 0,
        flags: ["Interview ended before sufficient technical analysis data was gathered."],
        summary: "Session was terminated before the live analysis could compile a final verdict."
      } as any
    }
    const sessionScore = sessionLog.length ? (sessionLog.reduce((a, b) => a + b.score, 0) / sessionLog.length) : (last.score ?? 0)
    let sessionVerdict = last.verdict ?? "NEEDS REVIEW"
    if (sessionLog.length > 0) {
      if (sessionScore < 40) sessionVerdict = "HIGHLY SUSPICIOUS"
      else if (sessionScore < 60) sessionVerdict = "SUSPICIOUS"
      else if (sessionScore < 80) sessionVerdict = "NEEDS REVIEW"
      else sessionVerdict = "GENUINE"
    }
    try {
      const payload = {
        candidate_name: candidateName,
        interviewer_name: authDisplayName || authUser,   // always the logged-in HR user
        role,
        duration_s: elapsed,
        final_score: sessionScore,
        verdict: sessionVerdict,
        strong_signals: last.strong_signals,
        flags: last.flags,
        questions,
        plagiarism_risk: plagRisk,
        summary: last.summary,
        personal_text: pTextRef.current,
        technical_text: techTranscriptRef.current.trim(),
        personal_profile: profile || {},
        technical_profile: {
          formality_score: last.formality || 0,
          vocabulary_level: last.vocabulary || 0,
          grammar_score: last.grammar || 0,
          lexical_diversity: last.lexical_diversity || 0,
          filler_ratio: last.filler_ratio || 0,
          avg_sentence_len: last.avg_sent_len || 0,
          transition_density: last.transition_density || 0,
          flesch_kincaid: last.flesch_kincaid || 0,
          gunning_fog: last.gunning_fog || 0,
          passive_voice_ratio: last.passive_voice || 0,
          sentence_burstiness: last.sentence_burstiness || 0,
          ai_boilerplate: last.ai_boilerplate || 0,
          personal_pronoun_ratio: last.pronouns || 0,
          ai_sentence_starters: last.ai_starters || 0,
        }
      }
      console.log("Saving session...", payload)
      const r = await fetch(`${API}/voice/save-session`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload)
      })
      const j = await r.json()
      console.log("Save session response:", j)
      if (j.status === "ok") setSavedId(j.session_id)
    } catch (e) {
      console.error("Failed to save session", e)
    }
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "00")}`

  const canProceed = candidateName.trim() !== "" && authToken !== ""

  // ─── INVISIBLE: overlay disabled via popup toggle ────────────────────────
  if (!visible) return null

  // ─── PHASE: INFO ──────────────────────────────────────────────────────────
  if (phase === "info") {
    return (
      <div className="sh-root sh-fadein" style={{ position: "fixed", top: 72, right: 14, zIndex: 9999, width: 340, fontFamily: "'Inter',sans-serif", display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)" }}>
        <GlassCard bdr={GLASS_BDR} glow="rgba(0,245,255,0.05)" bg={GLASS_BG} style={{ display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)", overflow: "hidden" }}>
          <div style={S.hdr}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Logo />
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 12 }}>SachhAI Live</div>
                <div style={{ color: "#94a3b8", fontSize: 9 }}>Step 1 of 3 · Session Setup</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <a href={`${API}/dashboard`} target="_blank" rel="noreferrer" style={{ color: "#059669", fontSize: 9, textDecoration: "none", fontWeight: 700 }}>Dashboard →</a>
              <button onClick={closeOverlay} style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer", fontWeight: 700 }}>X</button>
            </div>
          </div>
          <div style={{ ...S.body, overflowY: "auto", flex: 1, paddingBottom: 14 }} className="sh-scroll">

            {/* ── Mode Toggle ─────────────────────────────────────────── */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ ...S.lbl, marginBottom: 8 }}>Recording Mode</label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                {(["dual", "solo"] as const).map(m => {
                  const isActive = recordingMode === m
                  const icon = m === "dual" ? "💬 [Meet CC]" : "🔊 [System Audio]"
                  const title = m === "dual" ? "Dual Mode (CC)" : "Solo Mode (Audio)"
                  const sub = m === "dual" ? "HR + Candidate · uses Meet CC" : "Candidate only · system audio share"
                  return (
                    <button
                      key={m}
                      onClick={() => setRecordingMode(m)}
                      style={{
                        background: isActive ? "linear-gradient(135deg,#2563eb20,#2563eb20)" : "#ffffff06",
                        border: isActive ? "1px solid #2563eb50" : "1px solid #ffffff10",
                        borderRadius: 10, padding: "9px 10px", cursor: "pointer",
                        textAlign: "left" as const, transition: "all .18s"
                      }}
                    >
                      <div style={{ fontSize: 14, marginBottom: 3 }}>{icon}</div>
                      <div style={{ color: isActive ? "#93c5fd" : "#64748b", fontSize: 9, fontWeight: 700 }}>{title}</div>
                      <div style={{ color: isActive ? "#2563eb" : "#334155", fontSize: 7, marginTop: 2, lineHeight: 1.4 }}>{sub}</div>
                    </button>
                  )
                })}
              </div>
              {recordingMode === "solo" && (
                <div style={{ marginTop: 7, background: "#f59e0b10", border: "1px solid #f59e0b30", borderRadius: 8, padding: "7px 10px", color: "#fbbf24", fontSize: 8, lineHeight: 1.6 }}>
                  <strong>Solo Mode</strong> — captures only the candidate's audio from your speakers via screen share. You'll be asked to share the Meet tab when the interview starts.
                </div>
              )}
              {recordingMode === "dual" && (
                <div style={{ marginTop: 7, background: "rgba(99,102,241,0.1)", border: "1px solid #6366f130", borderRadius: 8, padding: "7px 10px", color: "#fbbf24", fontSize: 8, lineHeight: 1.6 }}>
                  💬 <strong>Dual Mode</strong> — uses Google Meet Closed Captions (CC). Both HR and candidate audio is captured. Enable CC in Meet before starting.
                </div>
              )}
            </div>

            <label style={S.lbl}>Candidate Name *</label>
            <input className="sh-input" style={{ marginBottom: 10 }} value={candidateName} onChange={e => setCandidateName(e.target.value)} placeholder="e.g. Arjun Mehta" />

            {/* ── Interviewer Login ─────────────────────────────────── */}
            {authToken ? (
              <div style={{ marginBottom: 14, background: "#10b98112", border: "1px solid #10b98130", borderRadius: 10, padding: "9px 12px", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 14, color: "#10b981" }}>✓</span>
                <div>
                  <div style={{ color: "#10b981", fontWeight: 700, fontSize: 10 }}>{authDisplayName}</div>
                  <div style={{ color: "#64748b", fontSize: 8 }}>@{authUser} · {authRole.toUpperCase()} · Signed in</div>
                </div>
                <button onClick={() => { setAuthToken(""); setAuthUser(""); setAuthDisplayName(""); setAuthRole("") }}
                  style={{ marginLeft: "auto", background: "#ef444412", border: "1px solid #ef444430", borderRadius: 6, padding: "3px 8px", color: "#f87171", fontSize: 8, cursor: "pointer" }}>
                  Sign out
                </button>
              </div>
            ) : (
              <div style={{ marginBottom: 14 }}>
                <label style={{ ...S.lbl, marginBottom: 6 }}>Interviewer Login *</label>
                <input className="sh-input" style={{ marginBottom: 7 }}
                  value={loginUsername} onChange={e => setLoginUsername(e.target.value)}
                  placeholder="Username" autoComplete="username" />
                <input className="sh-input" style={{ marginBottom: 7 }}
                  type="password" value={loginPassword} onChange={e => setLoginPassword(e.target.value)}
                  placeholder="Password" autoComplete="current-password"
                  onKeyDown={e => e.key === "Enter" && doLogin()} />
                <button onClick={() => doLogin()} disabled={loginLoading}
                  style={{ width: "100%", padding: "8px", border: "none", borderRadius: 9,
                    background: loginLoading ? "#1e293b" : "linear-gradient(135deg,#2563eb,#2563eb)",
                    color: "#fff", fontSize: 11, fontWeight: 700, cursor: loginLoading ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
                  {loginLoading
                    ? <><span className="sh-spin" style={{ width: 8, height: 8, border: "2px solid rgba(255,255,255,.3)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block" }} /> Verifying…</>
                    : "🔑 Sign In"}
                </button>
                <button onClick={() => { doLogin("hr1", "hr123") }} disabled={loginLoading}
                  style={{ width: "100%", padding: "7px", border: "1px dashed rgba(255,255,255,0.15)", borderRadius: 9,
                    background: "rgba(255,255,255,0.03)", color: "#94a3b8", fontSize: 10, fontWeight: 600, cursor: loginLoading ? "not-allowed" : "pointer",
                    marginTop: 6, display: "flex", alignItems: "center", justifyContent: "center", gap: 4, transition: "all 0.2s" }}
                  onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.08)"; e.currentTarget.style.color = "#fff"; }}
                  onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; e.currentTarget.style.color = "#94a3b8"; }}>
                  ⚡ Try Demo Account (hr1)
                </button>
                {loginError && (
                  <div style={{ marginTop: 7, background: "#ef444410", border: "1px solid #ef444440", borderRadius: 8, padding: "7px 10px", color: "#f87171", fontSize: 8, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                    {loginError}
                  </div>
                )}
                <div style={{ marginTop: 6, color: "#334155", fontSize: 7, textAlign: "center" as const }}>
                  Only registered portal users can conduct interviews.
                </div>
              </div>
            )}

            <label style={S.lbl}>Role / Position</label>
            <input className="sh-input" style={{ marginBottom: 14 }} value={role} onChange={e => setRole(e.target.value)} placeholder="e.g. Senior Backend Engineer" />

            <div style={{ background: "rgba(245,158,11,0.06)", border: "1px solid rgba(245,158,11,0.2)", borderRadius: 10, padding: "8px 10px", color: "#fbbf24", fontSize: 8.5, marginBottom: 12, lineHeight: 1.4 }}>
              ⚠️ <strong>Consent Notice:</strong> This session will transcribe and analyze speech using AI. Ensure the candidate has been informed before proceeding.
            </div>

            {err && <div style={{ background: "#ef444410", border: "1px solid #ef444430", borderRadius: 8, padding: "7px 10px", color: "#f87171", fontSize: 8, marginBottom: 10, whiteSpace: "pre-wrap" }}>{err}</div>}

            <button onClick={() => { if (!canProceed) { setErr("Please enter candidate name and sign in to conduct the interview."); return } setErr(""); setPhase("personal") }} style={S.btn("linear-gradient(to right,#d97706,#059669)")}>
              Continue → Record Personal Intro
            </button>
          </div>
        </GlassCard>
      </div>
    )
  }

  // ─── PHASE: PERSONAL ─────────────────────────────────────────────────────
  if (phase === "personal") {
    const wc = personalText.trim().split(/\s+/).filter(Boolean).length
    return (
      <div className="sh-root sh-fadein" style={{ position: "fixed", top: 72, right: 14, zIndex: 9999, width: 340, fontFamily: "'Inter',sans-serif", display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)" }}>
        <GlassCard bdr={GLASS_BDR} glow="rgba(0,245,255,0.05)" bg={GLASS_BG} style={{ display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)", overflow: "hidden" }}>
          <div style={S.hdr}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Logo />
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 12 }}>{candidateName}</div>
                <div style={{ color: "#94a3b8", fontSize: 9 }}>Step 2 · Personal Baseline · {role || "No role"}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <a href={`${API}/dashboard`} target="_blank" rel="noreferrer" style={{ color: "#059669", fontSize: 9, textDecoration: "none", fontWeight: 700 }}>Dashboard →</a>
              <button onClick={closeOverlay} style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer", fontWeight: 700 }}>X</button>
            </div>
          </div>
          <div style={{ ...S.body, overflowY: "auto", flex: 1, paddingBottom: 14 }} className="sh-scroll">
            {/* Info banner — mode aware */}
            {recordingMode === "solo" ? (
              <div style={{ background: "linear-gradient(135deg,#f59e0b12,#f97316_08)", border: "1px solid #f59e0b30", borderRadius: 10, padding: "10px 12px", marginBottom: 12, fontSize: 8, lineHeight: 1.8, color: "#fde68a" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 14 }}>🔊</span>
                  <strong style={{ color: "#fbbf24", fontSize: 9 }}>Solo Mode · System Audio Capture</strong>
                  <span style={{ marginLeft: "auto", fontSize: 7, padding: "1px 6px", background: "#f59e0b20", border: "1px solid #f59e0b40", borderRadius: 99, color: "#f59e0b", fontWeight: 700 }}>CANDIDATE ONLY</span>
                </div>
                Click <strong>Record</strong> — you'll be asked to share your <strong>Meet tab</strong>. This captures only the candidate's audio from your speakers as their personal baseline.
                <div style={{ color: "#f97316", marginTop: 3, fontWeight: 500 }}>💡 Deepgram Nova-2 transcribes candidate audio in real-time — no CC needed.</div>
              </div>
            ) : (
              <div style={{ background: "linear-gradient(135deg,#10b98112,#3b82f608)", border: "1px solid #10b98130", borderRadius: 10, padding: "10px 12px", marginBottom: 12, fontSize: 8, lineHeight: 1.8, color: "#6ee7b7" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 12 }}>[Mic]</span>
                  <strong style={{ color: "#a7f3d0", fontSize: 9 }}>Deepgram Nova-2 Recording</strong>
                  <span style={{ marginLeft: "auto", fontSize: 7, padding: "1px 6px", background: "#10b98120", border: "1px solid #10b98140", borderRadius: 99, color: "#10b981", fontWeight: 700 }}>HIGH ACCURACY</span>
                </div>
                Speak your name, background, hobbies, anything natural. We capture your real voice style as a personal baseline.
                <div style={{ color: "#475569", marginTop: 3 }}>Technical phase reads Meet CC captions automatically.</div>
              </div>
            )}

            {/* Record button row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <label style={{ ...S.lbl, marginBottom: 0 }}>Personal Introduction ({wc} words)</label>
              <button
                onClick={isRec ? stopRec : startRec}
                disabled={isTranscribing}
                style={{ background: isRec ? "linear-gradient(135deg,#ef4444,#b91c1c)" : isTranscribing ? "#1e293b" : recordingMode === "solo" ? "linear-gradient(135deg,#f59e0b,#f97316)" : "linear-gradient(135deg,#2563eb,#2563eb)", border: "none", borderRadius: 7, padding: "5px 13px", color: "#fff", fontSize: 9, fontWeight: 700, cursor: isTranscribing ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 5, transition: "all 0.2s ease" }}
              >
                {isTranscribing
                  ? <><span className="sh-spin" style={{ width: 7, height: 7, border: "1.5px solid rgba(255,255,255,.3)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block" }} />Processing</>
                  : <><span style={{ width: 7, height: 7, borderRadius: "50%", background: "#fff", display: "inline-block", ...(isRec ? { animation: "sh-pulse 1s infinite" } : {}) }} />{isRec ? "Stop" : recordingMode === "solo" ? "Capture" : "Record"}</>
                }
              </button>
            </div>

            {/* Live waveform canvas — shown while recording */}
            {isRec && (
              <div style={{ marginBottom: 8, borderRadius: 8, overflow: "hidden", border: "1px solid #3b82f625", background: "#3b82f606", padding: "4px 8px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                  <span style={{ color: "#d97706", fontSize: 7, fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
                    <span className="sh-pulse" style={{ width: 5, height: 5, borderRadius: "50%", background: "#ef4444", display: "inline-block" }} />
                    RECORDING
                  </span>
                  <span style={{ color: "#64748b", fontSize: 7 }}>
                    {Math.floor(recSecs / 60)}:{String(recSecs % 60).padStart(2, "0")}
                  </span>
                </div>
                <canvas
                  ref={waveCanvasRef}
                  width={290} height={36}
                  style={{ width: "100%", height: 36, display: "block" }}
                />
              </div>
            )}

            {/* Processing state */}
            {isTranscribing && (
              <div style={{ marginBottom: 8, padding: "8px 12px", background: "rgba(99,102,241,0.1)", border: "1px solid #6366f130", borderRadius: 8, display: "flex", alignItems: "center", gap: 8 }}>
                <span className="sh-spin" style={{ width: 14, height: 14, border: "2px solid #2563eb40", borderTopColor: "#2563eb", borderRadius: "50%", display: "inline-block", flexShrink: 0 }} />
                <div>
                  <div style={{ color: "#fbbf24", fontSize: 8, fontWeight: 700 }}>Deepgram Nova-2 is transcribing…</div>
                  <div style={{ color: "#475569", fontSize: 7, marginTop: 2 }}>This takes 2–5 seconds. Highly accurate for all accents.</div>
                </div>
              </div>
            )}

            {/* Status hint */}
            {recHint && !isTranscribing && <div style={{ color: recHint.startsWith("✓") ? "#10b981" : recHint.startsWith("⚠") ? "#f59e0b" : "#94a3b8", fontSize: 8, marginBottom: 6, lineHeight: 1.5 }}>{recHint}</div>}

            {/* Editable textarea */}
            <textarea
              className="sh-input"
              style={{ minHeight: 100, marginBottom: 4, resize: "vertical", lineHeight: 1.6, border: isRec ? "1px solid #ef444460" : isTranscribing ? "1px solid #6366f160" : "1px solid #1e2d4a", transition: "border-color .3s" }}
              value={personalText}
              onChange={e => setPersonalText(e.target.value)}
              placeholder="Click Record above → speak naturally → transcript appears here. Or type / paste directly."
            />

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span style={{ color: wc >= 15 ? "#10b981" : "#475569", fontSize: 8, fontWeight: wc >= 15 ? 700 : 400 }}>{wc}/15 words {wc >= 15 ? "✓ Ready" : "min"}</span>
              {personalText && <button onClick={() => { setPersonalText(""); setRecHint("") }} style={{ background: "none", border: "none", color: "#334155", fontSize: 9, cursor: "pointer" }}>✕ Clear</button>}
            </div>

            {err && <div style={{ background: "#ef444410", border: "1px solid #ef444430", borderRadius: 8, padding: "7px 10px", color: "#f87171", fontSize: 8, marginBottom: 10, whiteSpace: "pre-wrap" }}>{err}</div>}

            <button onClick={analyzePersonal} disabled={loading || isTranscribing} style={{ ...S.btn("linear-gradient(to right,#d97706,#059669)"), opacity: (loading || isTranscribing) ? .5 : 1 }}>
              {loading ? <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}><span className="sh-spin" style={{ width: 10, height: 10, border: "2px solid rgba(255,255,255,.3)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block" }} />Analyzing…</span> : "⚡ Analyze Baseline → Start Interview"}
            </button>
            <button onClick={() => { setErr(""); setPhase("info") }} style={{ ...S.btn("rgba(255,255,255,0.05)", 4), fontSize: 10, border: `1px solid ${GLASS_BDR}` }}>← Back</button>
          </div>
        </GlassCard>
      </div>
    )
  }

  // ─── PHASE: PROFILE ───────────────────────────────────────────────────────
  if (phase === "profile" && profile) {
    const bqColor  = profileMeta?.baseline_quality_info?.color  ?? "#10b981"
    const bqLabel  = profileMeta?.baseline_quality_info?.label  ?? "Baseline Locked"
    const bqScore  = profileMeta?.baseline_quality_score        ?? 0
    const cfColor  = profileMeta?.baseline_confidence_info?.color ?? "#10b981"
    const cfLabel  = profileMeta?.baseline_confidence_info?.label ?? "Medium"
    const readiness = profileMeta?.readiness ?? "Ready"
    const readinessNote = profileMeta?.readiness_note ?? ""
    const rdColor  = readiness === "Ready" ? "#10b981" : readiness === "Ready with caution" ? "#f59e0b" : "#ef4444"

    const toggle = (key: string) => setOpenDropdown(p => p === key ? null : key)

    return (
      <div className="sh-root sh-fadein" style={{ position: "fixed", top: 72, right: 14, zIndex: 9999, width: 340, fontFamily: "'Inter',sans-serif", display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)" }}>
        <GlassCard bdr={`${bqColor}30`} glow={`${bqColor}10`} bg={GLASS_BG} style={{ display: "flex", flexDirection: "column", maxHeight: "calc(100vh - 90px)", overflow: "hidden" }}>

          {/* ── Header (always visible) ──────────────────────────────── */}
          <div style={S.hdr}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Logo />
              <div>
                <div style={{ color: "#fff", fontWeight: 700, fontSize: 12 }}>{bqLabel} · {candidateName}</div>
                <div style={{ color: "#94a3b8", fontSize: 9 }}>{profile.word_count}w · {role || "No role"} · {authDisplayName || authUser}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <a href={`${API}/dashboard`} target="_blank" rel="noreferrer" style={{ color: "#059669", fontSize: 9, textDecoration: "none", fontWeight: 700 }}>Dashboard →</a>
              <button onClick={closeOverlay} style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer", fontWeight: 700 }}>X</button>
            </div>
          </div>

          {/* ── Scrollable body ──────────────────────────────────────── */}
          <div style={{ ...S.body, overflowY: "auto", flex: 1, paddingBottom: 6 }}>

            {/* Status pills */}
            <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
              <span style={{ fontSize: 8, padding: "3px 9px", borderRadius: 99, background: `${rdColor}18`, border: `1px solid ${rdColor}40`, color: rdColor, fontWeight: 700 }}>{readiness}</span>
              <span style={{ fontSize: 8, padding: "3px 9px", borderRadius: 99, background: `${cfColor}15`, border: `1px solid ${cfColor}35`, color: cfColor, fontWeight: 600 }}>{cfLabel} confidence</span>
              <span style={{ fontSize: 8, padding: "3px 9px", borderRadius: 99, background: "rgba(99,102,241,0.1)", border: "1px solid #6366f130", color: "#d97706", fontWeight: 600 }}>Baseline 1/1</span>
            </div>

            {/* Readiness note */}
            {readinessNote && (
              <div style={{ fontSize: 8, color: "#94a3b8", lineHeight: 1.6, padding: "6px 9px", background: `${rdColor}08`, border: `1px solid ${rdColor}20`, borderRadius: 7, marginBottom: 8 }}>
                {readinessNote}
              </div>
            )}

            {/* Sample adequacy + quality bars (always visible) */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ color: "#64748b", fontSize: 8 }}>Sample</span>
                <span style={{ color: bqColor, fontSize: 8, fontWeight: 700 }}>{profileMeta?.adequacy_label ?? "–"} · {profile.word_count}w</span>
              </div>
              <div style={{ height: 3, background: "#1e293b", borderRadius: 99, overflow: "hidden", marginBottom: 5 }}>
                <div style={{ width: `${Math.min(100, (profile.word_count / 80) * 100)}%`, height: "100%", background: bqColor, borderRadius: 99 }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                <span style={{ color: "#64748b", fontSize: 8 }}>Quality Score</span>
                <span style={{ color: bqColor, fontSize: 8, fontWeight: 700 }}>{bqScore}/100</span>
              </div>
              <div style={{ height: 3, background: "#1e293b", borderRadius: 99, overflow: "hidden" }}>
                <div style={{ width: `${bqScore}%`, height: "100%", background: bqColor, borderRadius: 99 }} />
              </div>
            </div>

            {/* Strengths / issues chips (compact, always visible) */}
            {(profileMeta?.strengths?.length > 0 || profileMeta?.issues?.length > 0) && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3, marginBottom: 8 }}>
                {(profileMeta?.strengths as string[] ?? []).map((s: string, i: number) => (
                  <span key={`s${i}`} style={{ fontSize: 7, padding: "2px 6px", borderRadius: 99, background: "#10b98112", border: "1px solid #10b98128", color: "#10b981" }}>{s}</span>
                ))}
                {(profileMeta?.issues as string[] ?? []).map((s: string, i: number) => (
                  <span key={`e${i}`} style={{ fontSize: 7, padding: "2px 6px", borderRadius: 99, background: "#f59e0b10", border: "1px solid #f59e0b28", color: "#f59e0b" }}>{s}</span>
                ))}
              </div>
            )}

            {/* ── DROPDOWNS ───────────────────────────────────────────── */}

            {/* Linguistic Fingerprint */}
            <Dropdown id="fingerprint" label="Linguistic Fingerprint" labelColor="#6366f1" open={openDropdown === "fingerprint"} onToggle={toggle}>
              {[
                { l: "Formality",         v: profile.formality_score,        max: 100, color: "#059669" },
                { l: "Vocabulary",        v: profile.vocabulary_level,        max: 100, color: "#059669" },
                { l: "Grammar",           v: profile.grammar_score,           max: 100, color: "#14b8a6" },
                { l: "Lexical Diversity", v: profile.lexical_diversity * 100, max: 100, color: "#f59e0b" },
                { l: "Filler Words",      v: profile.filler_ratio * 100,      max: 30,  color: "#10b981" },
                { l: "Avg Sentence Len",  v: profile.avg_sentence_len,        max: 40,  color: "#64748b", fmt: (v: number) => v.toFixed(1) + "w" },
              ].map(({ l, v, max, color, fmt }: any) => (
                <div key={l} style={S.row}>
                  <div style={S.rl}><span style={{ color: "#64748b", fontSize: 9 }}>{l}</span><span style={{ color: "#94a3b8", fontSize: 10, fontWeight: 600 }}>{fmt ? fmt(v) : v.toFixed(0)}</span></div>
                  <Bar value={v} max={max} color={color} />
                </div>
              ))}
            </Dropdown>

            {/* Recruiter Action */}
            {profileMeta?.recommendations?.length > 0 && (
              <Dropdown id="recruiter" label="Recruiter Action" labelColor="#f59e0b" open={openDropdown === "recruiter"} onToggle={toggle}>
                {(profileMeta.recommendations as string[]).map((r: string, i: number) => (
                  <div key={i} style={{ color: "#94a3b8", fontSize: 8, lineHeight: 1.6, paddingLeft: 7, borderLeft: "2px solid #f59e0b30", marginBottom: i < profileMeta.recommendations.length - 1 ? 5 : 0 }}>{r}</div>
                ))}
              </Dropdown>
            )}

            {/* Comparison Context */}
            {profileMeta?.comparison_context && (
              <Dropdown id="context" label="Comparison Context" labelColor="#6366f1" open={openDropdown === "context"} onToggle={toggle}>
                <div style={{ color: "#64748b", fontSize: 8, lineHeight: 1.6 }}>{profileMeta.comparison_context}</div>
              </Dropdown>
            )}

            {/* Disclaimer */}
            <Dropdown id="disclaimer" label="Disclaimer" labelColor="#475569" open={openDropdown === "disclaimer"} onToggle={toggle}>
              <div style={{ color: "#475569", fontSize: 7, lineHeight: 1.5 }}>
                {profileMeta?.disclaimer ?? "This tool supports interviewer judgment and should not be used as the sole basis for any hiring decision."}
              </div>
            </Dropdown>


            {/* Technical phase notice */}
            {recordingMode === "dual" && (
              <div style={{ marginTop: 4, background: "rgba(99,102,241,0.1)", border: "1px solid #6366f130", borderRadius: 8, padding: "7px 9px", fontSize: 8, lineHeight: 1.5, color: "#fbbf24" }}>
                <strong>Enable Meet CC</strong> before starting — captions are read automatically.
              </div>
            )}
            {recordingMode === "solo" && (
              <div style={{ marginTop: 4, background: "#f59e0b10", border: "1px solid #f59e0b30", borderRadius: 8, padding: "7px 9px", fontSize: 8, lineHeight: 1.5, color: "#fbbf24" }}>
                🔊 <strong>Solo Mode Active</strong> — you'll share your Meet tab audio when the interview starts. CC is not required.
              </div>
            )}

          </div>

          {/* ── Pinned action buttons (always visible, outside scroll) ── */}
          <div style={{ padding: "10px 14px 12px", borderTop: `1px solid ${GLASS_BDR}`, background: "rgba(4,6,15,0.7)" }}>
            <button onClick={startLive} style={S.btn(`linear-gradient(to right,${bqColor},${bqColor}cc)`)}>
              ▶ Start Technical Interview
            </button>
            <button onClick={() => { setErr(""); setPhase("personal") }} style={{ ...S.btn("rgba(255,255,255,0.05)", 4), fontSize: 10, marginTop: 6, border: `1px solid ${GLASS_BDR}` }}>
              Re-record Personal Intro
            </button>
          </div>

        </GlassCard>
      </div>
    )
  }


  // ─── PHASE: LIVE ──────────────────────────────────────────────────────────
  if (phase === "live") {
    const sc = live?.score ?? 100
    const liveVerdict = live?.verdict ?? "GENUINE"
    const vs = vStyle(liveVerdict)
    const scC = sc === null ? "#94a3b8" : sc >= 80 ? "#10b981" : sc >= 60 ? "#f59e0b" : sc >= 40 ? "#f97316" : "#ef4444"
    const isConn = status.includes("Connected") || status.includes("Calibrat") || status.includes("locked") || status.includes("Active")
    const pc = plagRisk >= 60 ? "#ef4444" : plagRisk >= 35 ? "#f59e0b" : "#10b981"
    // Score trend arrow
    const scoreHistory = sessionLog.slice(-2).map(s => s.score)
    const scoreTrend = scoreHistory.length >= 2 ? scoreHistory[1] - scoreHistory[0] : 0
    const trendArrow = scoreTrend > 1.5 ? "\u2191" : scoreTrend < -1.5 ? "\u2193" : "\u2192"
    const trendColor = scoreTrend > 1.5 ? "#10b981" : scoreTrend < -1.5 ? "#ef4444" : "#94a3b8"
    // Sparkline — last 20 scores
    const sparkPoints = sessionLog.slice(-20).map(s => s.score)
    // Live caption preview
    const lastCaption = lastCapRef.current ? lastCapRef.current.slice(0, 70) : ""
    return (
      <>
        {showCcReminder && (
          <div className="sh-root" style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 100000, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter',sans-serif" }}>
            <div className="sh-fadein" style={{ background: "rgba(4,6,15,0.95)", backdropFilter: "blur(16px)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px", textAlign: "center", border: `1px solid ${GLASS_BDR}`, borderRadius: 24, boxShadow: "0 24px 80px rgba(0, 245, 255, 0.15)", width: "420px" }}>
              <div style={{ width: 64, height: 64, background: "rgba(0,245,255,0.1)", border: "1px solid rgba(0,245,255,0.3)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 20, color: "#d97706", fontSize: 28, boxShadow: "0 0 30px rgba(0,245,255,0.2)" }}>💬</div>
              <h3 style={{ margin: "0 0 12px 0", color: "#fff", fontSize: 22, fontWeight: 700 }}>Enable Meet Captions (CC)</h3>
              <p style={{ margin: "0 0 28px 0", color: "#94a3b8", fontSize: 13, lineHeight: 1.6 }}>SachhAI requires Google Meet's Closed Captions to be active in order to analyze the live interview audio. Please turn them on now.</p>
              <button onClick={() => setShowCcReminder(false)} style={{ ...S.btn("linear-gradient(to right,#d97706,#059669)"), fontSize: 14, padding: "14px 24px", width: "100%", borderRadius: 12, boxShadow: "0 4px 14px rgba(124, 58, 237, 0.4)" }}>
                Okay, CC is ON
              </button>
            </div>
          </div>
        )}
        <div className="sh-root sh-fadein" style={{ position: "fixed", top: 72, right: 14, zIndex: 9999, width: expanded ? 360 : 200, fontFamily: "'Inter',sans-serif", transition: "width .3s ease" }}>
          <GlassCard bdr={vs.bdr} glow={vs.glow} bg={vs.bg}>
          {/* Header */}
          <div style={S.hdr}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: isConn ? "#3b82f6" : "#f59e0b", ...(isConn ? { animation: "sh-pulse 2s infinite", boxShadow: "0 0 10px #3b82f6" } : {}) }} />
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 11 }}>{candidateName}</div>
              <div style={{ color: "#94a3b8", fontSize: 9 }}>{fmt(elapsed)}</div>
              {/* Backend indicator */}
              <span style={{ fontSize: 7, padding: "1px 5px", borderRadius: 99, background: beLabel === "Local" ? "#10b98120" : beLabel === "HF" ? "#6366f120" : "#ef444420", border: `1px solid ${beLabel === "Local" ? "#10b98140" : beLabel === "HF" ? "#6366f140" : "#ef444440"}`, color: beLabel === "Local" ? "#10b981" : beLabel === "HF" ? "#3b82f6" : "#ef4444" }}>{beLabel}</span>
            </div>
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <span style={{ color: "#334155", fontSize: 8 }}>{live?.total_words ?? 0}w</span>
              <a href={`${API}/dashboard`} target="_blank" rel="noreferrer" style={{ color: "#059669", fontSize: 8, textDecoration: "none" }}>Dashboard</a>
              <button onClick={() => setExpanded(!expanded)} style={{ background: "#ffffff0f", border: "none", color: "#64748b", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}>{expanded ? "▲" : "▼"}</button>
              <button onClick={endInterview} style={{ background: "#ef444415", border: "1px solid #ef444430", color: "#f87171", borderRadius: 5, padding: "2px 8px", fontSize: 9, cursor: "pointer", fontWeight: 700 }}>End</button>
              <button onClick={closeOverlay} style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer", fontWeight: 700 }}>X</button>
            </div>
          </div>
          {/* Status bar + calibration progress */}
          <div style={{ padding: "4px 14px 0", background: "#ffffff03" }}>
            <div style={{ color: "#334155", fontSize: 8, marginBottom: 2 }}>{status || "Waiting for Meet CC captions…"}</div>
            {/* Calibration progress bar — shows until baseline locks */}
            {!baselineLocked && (
              <div style={{ marginBottom: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ color: "#475569", fontSize: 7 }}>Calibrating baseline</span>
                  <span style={{ color: "#059669", fontSize: 7, fontWeight: 700 }}>{calibWords}/40 words</span>
                </div>
                <div style={{ height: 2, background: "#1e293b", borderRadius: 99, overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, (calibWords / 40) * 100)}%`, height: "100%", background: "linear-gradient(90deg,#4b5563,#d97706)", borderRadius: 99, transition: "width .4s ease" }} />
                </div>
              </div>
            )}
            {/* Live caption preview — shows last captured sentence */}
            {baselineLocked && lastCaption && (
              <div style={{ marginBottom: 4, padding: "3px 7px", background: "#3b82f608", border: "1px solid #3b82f615", borderRadius: 5, display: "flex", alignItems: "flex-start", gap: 5 }}>
                <span style={{ color: "#d97706", fontSize: 7, flexShrink: 0, marginTop: 1 }}>●</span>
                <span style={{ color: "#64748b", fontSize: 7, lineHeight: 1.5, fontStyle: "italic", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>"{lastCaption}{lastCaption.length >= 70 ? "…" : ""}"</span>
              </div>
            )}
          </div>

          {/* ── Caption input row (single-line quick send) ── */}
          {expanded && <div style={{ margin: "6px 14px 0", display: "flex", gap: 4 }}>
            <input
              ref={manualInputRef}
              className="sh-input"
              placeholder="Quick caption send (Enter to send)…"
              style={{ fontSize: 9, padding: "6px 10px" }}
              onKeyDown={(e: any) => {
                if (e.key === "Enter") {
                  sendManual(e.target.value)
                  e.target.value = ""
                }
              }}
            />
            <button
              onClick={() => {
                const val = manualInputRef.current?.value || ""
                sendManual(val || "Test sentence for analysis.")
                if (manualInputRef.current) manualInputRef.current.value = ""
              }}
              style={{ background: "#2563eb", border: "none", borderRadius: 8, padding: "0 10px", color: "#fff", fontSize: 9, cursor: "pointer", whiteSpace: "nowrap" }}
            >Send</button>
          </div>}

          {/* ── Manual Technical Text Block (for testing without live CC) ── */}
          {expanded && (
            <div style={{ margin: "6px 14px 0" }}>
              <button
                onClick={() => setShowManualTech(p => !p)}
                style={{ width: "100%", background: "#1d4ed818", border: "1px solid #1d4ed840", color: "#fbbf24", borderRadius: 8, padding: "5px 10px", fontSize: 9, fontWeight: 700, cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}
              >
                <span>✍ Paste Technical Text (Testing Mode)</span>
                <span>{showManualTech ? "▲" : "▼"}</span>
              </button>
              {showManualTech && (
                <div style={{ marginTop: 4, background: "#1d4ed808", border: "1px solid #1d4ed825", borderRadius: "0 0 8px 8px", padding: "8px 10px" }}>
                  <div style={{ color: "#7c5cf5", fontSize: 8, marginBottom: 5, lineHeight: 1.5 }}>
                    Paste the candidate's technical answer here. It will be sent in chunks (simulates live CC).
                  </div>
                  <textarea
                    className="sh-input"
                    value={manualTechDraft}
                    onChange={(e: any) => setManualTechDraft(e.target.value)}
                    placeholder="Paste full technical answer here…"
                    style={{ minHeight: 90, resize: "vertical", fontSize: 9, lineHeight: 1.6, marginBottom: 6 }}
                  />
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => sendManualTechBlock(manualTechDraft)}
                      disabled={!manualTechDraft.trim()}
                      style={{ flex: 1, background: "linear-gradient(90deg,#d97706,#4b5563)", border: "none", borderRadius: 7, padding: "7px", color: "#fff", fontSize: 10, fontWeight: 700, cursor: "pointer", opacity: manualTechDraft.trim() ? 1 : 0.5 }}
                    >⚡ Analyse This Text</button>
                    <button
                      onClick={() => setManualTechDraft("")}
                      style={{ background: "rgba(255,255,255,0.06)", border: "1px solid #ffffff12", borderRadius: 7, padding: "7px 10px", color: "#64748b", fontSize: 9, cursor: "pointer" }}
                    >Clear</button>
                  </div>
                </div>
              )}
            </div>
          )}

          {expanded && (
            <div className="sh-scroll" style={{ maxHeight: "72vh", overflowY: "auto", paddingBottom: 8 }}>

            {/* Score + Verdict + Confidence badge */}
            <div style={{ padding: "14px 14px 10px", textAlign: "center" }}>
              <div style={{ color: "#475569", fontSize: 8, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 4 }}>Authenticity Score</div>
              {transcript.trim().split(/\s+/).filter(Boolean).length < 50 ? (
                <div style={{ color: "#94a3b8", fontSize: 11, padding: "16px 0", fontWeight: 500, background: "rgba(255,255,255,0.02)", borderRadius: 10, border: `1px dashed ${GLASS_BDR}`, margin: "10px 0" }}>
                  Listening… ({transcript.trim().split(/\s+/).filter(Boolean).length}/50 words needed)
                </div>
              ) : (
                <>
                  {/* Score number + trend arrow */}
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "center", gap: 6 }}>
                    <div style={{ fontSize: 52, fontWeight: 800, color: scC, lineHeight: 1, letterSpacing: -2, fontVariantNumeric: "tabular-nums", transition: "color 0.6s ease" }}>{sc !== null ? Math.round(sc) : "--"}</div>
                    {sc !== null && (
                      <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-start", paddingTop: 8 }}>
                        <span style={{ fontSize: 18, fontWeight: 800, color: trendColor, lineHeight: 1, transition: "color 0.4s ease" }}>{trendArrow}</span>
                        {Math.abs(scoreTrend) > 1.5 && <span style={{ fontSize: 7, color: trendColor, fontWeight: 700, marginTop: 2 }}>{Math.abs(scoreTrend).toFixed(1)}</span>}
                      </div>
                    )}
                  </div>
                  {/* Sparkline — mini score history dots */}
                  {sparkPoints.length > 2 && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 2, marginTop: 8, height: 20 }}>
                      {sparkPoints.map((pt, i) => {
                        const ptC = pt >= 80 ? "#10b981" : pt >= 60 ? "#f59e0b" : pt >= 40 ? "#f97316" : "#ef4444"
                        const isLast = i === sparkPoints.length - 1
                        return <div key={i} style={{ width: isLast ? 7 : 4, height: isLast ? 7 : 4, borderRadius: "50%", background: isLast ? ptC : `${ptC}55`, flexShrink: 0, transition: "all 0.4s ease", boxShadow: isLast ? `0 0 8px ${ptC}` : "none" }} />
                      })}
                    </div>
                  )}
                  {live && <div style={{ marginTop: 8, display: "flex", justifyContent: "center", gap: 6, flexWrap: "wrap" }}>
                    <Pill text={liveVerdict || live.style_shift} bg={`${vs.txt}18`} border={`${vs.txt}40`} color={vs.txt} />
                    {live.confidence_v2 && (() => {
                      const cl = live.confidence_v2.level
                      const cc = cl === "high" ? "#10b981" : cl === "medium" ? "#f59e0b" : cl === "low" ? "#f97316" : "#ef4444"
                      return <Pill text={`${live.confidence_v2.label} confidence`} bg={`${cc}15`} border={`${cc}35`} color={cc} />
                    })()}
                  </div>}
                  {live?.short_guardrail && (
                    <div style={{ color: "#f59e0b", fontSize: 8, marginTop: 6, padding: "4px 8px", background: "#f59e0b12", borderRadius: 6, border: "1px solid #f59e0b20" }}>
                      {live.short_guardrail}
                    </div>
                  )}
                  {live && !live.short_guardrail && <div style={{ color: "#334155", fontSize: 8, marginTop: 5 }}>CI: {live.conf_low?.toFixed(0) ?? "--"}–{live.conf_high?.toFixed(0) ?? "--"} · {authDisplayName || authUser}</div>}
                </>
              )}
            </div>

            {/* Evidence chips — active signals */}
            {live?.active_signals?.length > 0 && (
              <div style={{ margin: "0 14px 10px" }}>
                <div style={{ color: "#334155", fontSize: 7, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 5 }}>Evidence Signals</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {(live.active_signals as string[]).map((sig: string) => {
                    const chipMap: Record<string, { label: string; color: string }> = {
                      ai_combo:          { label: "AI combo", color: "#ef4444" },
                      filler_drop:       { label: "Filler drop", color: "#f97316" },
                      vocab_spike:       { label: "Vocab spike", color: "#f59e0b" },
                      fk_jump:           { label: "Complexity jump", color: "#f59e0b" },
                      hedging_density:   { label: "Hedging", color: "#a855f7" },
                      passive_voice:     { label: "Passive voice", color: "#059669" },
                      transition_density:{ label: "Transitions", color: "#059669" },
                      temporal_drift:    { label: "Temporal drift", color: "#ec4899" },
                      sentence_uniformity:{ label: "Uniform sentences", color: "#64748b" },
                      short_answer:      { label: "Short answer", color: "#94a3b8" },
                      fog_jump:          { label: "Fog index", color: "#f59e0b" },
                    }
                    const chip = chipMap[sig] ?? { label: sig, color: "#64748b" }
                    return (
                      <span key={sig} style={{
                        fontSize: 7, padding: "2px 7px", borderRadius: 99,
                        background: `${chip.color}18`, border: `1px solid ${chip.color}40`,
                        color: chip.color, fontWeight: 600,
                      }}>
                        {chip.label}
                      </span>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Follow-up questions strip — updated live from WS, animates on change */}
            {questions.length > 0 && (
              <div key={questions[0]} className="sh-fadein" style={{ margin: "0 14px 10px", background: "linear-gradient(135deg,#d9770610,#05966906)", border: "1px solid #6366f130", borderRadius: 10, padding: "10px 12px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 8 }}>
                  <span style={{ fontSize: 11 }}>💡</span>
                  <span style={{ color: "#d97706", fontSize: 8, fontWeight: 800, letterSpacing: 1.2, textTransform: "uppercase" }}>Live Follow-up Questions</span>
                  <span className="sh-pulse" style={{ marginLeft: "auto", fontSize: 7, color: "#d97706", padding: "1px 6px", background: "#00f5ff15", border: "1px solid #00f5ff30", borderRadius: 99, fontWeight: 700 }}>LIVE</span>
                </div>
                {questions.map((q: string, i: number) => (
                  <div key={i} style={{ color: i === 0 ? "#e2e8f0" : "#94a3b8", fontSize: 8, marginBottom: i < questions.length - 1 ? 7 : 0, paddingLeft: 10, borderLeft: `2px solid ${i === 0 ? "#00f5ff80" : "#6366f130"}`, lineHeight: 1.6 }}>
                    <span style={{ color: i === 0 ? "#00f5ff" : "#6366f1", fontWeight: 700, marginRight: 4 }}>{i + 1}.</span>{q}
                  </div>
                ))}
              </div>
            )}

            {/* ── Answer Credibility Checker ─────────────────────────────────── */}
            {(() => {
              const credSummary = credResults.length > 0 ? {
                avg: Math.round(credResults.reduce((a, r) => a + r.score, 0) / credResults.length),
                correct: credResults.filter(r => r.verdict === "CORRECT").length,
                partial: credResults.filter(r => r.verdict === "PARTIALLY").length,
                incorrect: credResults.filter(r => r.verdict === "INCORRECT" || r.verdict === "INSUFFICIENT").length,
              } : null
              const credColor = (v: string) =>
                v === "CORRECT" ? "#10b981" : v === "PARTIALLY" ? "#f59e0b" : v === "INCORRECT" ? "#ef4444" : "#64748b"
              return (
                <div style={{ margin: "0 14px 10px" }}>
                  {/* Collapsible header */}
                  <button
                    onClick={() => setShowCred(p => !p)}
                    style={{
                      width: "100%", background: showCred ? "#a855f718" : "#a855f710",
                      border: `1px solid ${credResults.length > 0 ? "#a855f740" : "#a855f730"}`,
                      borderRadius: showCred ? "10px 10px 0 0" : 10,
                      padding: "7px 10px", cursor: "pointer", fontSize: 9, fontWeight: 700,
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      color: "#c084fc"
                    }}
                  >
                    <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ fontSize: 11 }}>🎯</span>
                      Answer Credibility Checker
                      {credSummary && (
                        <span style={{ marginLeft: 4, fontSize: 7, padding: "1px 6px", borderRadius: 99, background: credSummary.avg >= 70 ? "#10b98120" : credSummary.avg >= 45 ? "#f59e0b20" : "#ef444420", border: `1px solid ${credSummary.avg >= 70 ? "#10b98140" : credSummary.avg >= 45 ? "#f59e0b40" : "#ef444440"}`, color: credSummary.avg >= 70 ? "#10b981" : credSummary.avg >= 45 ? "#f59e0b" : "#ef4444", fontWeight: 700 }}>
                          {credResults.length} checked · avg {credSummary.avg}/100
                        </span>
                      )}
                    </span>
                    <span style={{ fontSize: 10, opacity: 0.7 }}>{showCred ? "▲" : "▼"}</span>
                  </button>

                  {showCred && (
                    <div style={{ background: "#a855f708", border: "1px solid #a855f725", borderRadius: "0 0 10px 10px", borderTop: "none", padding: "10px 10px 8px" }}>

                      {/* Quick stats if we have results */}
                      {credSummary && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, marginBottom: 8 }}>
                          {[
                            { l: "Correct", v: credSummary.correct, c: "#10b981" },
                            { l: "Partial", v: credSummary.partial, c: "#f59e0b" },
                            { l: "Incorrect", v: credSummary.incorrect, c: "#ef4444" },
                          ].map(({ l, v, c }) => (
                            <div key={l} style={{ textAlign: "center", padding: "4px", background: `${c}10`, border: `1px solid ${c}25`, borderRadius: 7 }}>
                              <div style={{ color: c, fontSize: 13, fontWeight: 700 }}>{v}</div>
                              <div style={{ color: "#475569", fontSize: 7 }}>{l}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Question input */}
                      <div style={{ color: "#7c5cf5", fontSize: 7, marginBottom: 5, lineHeight: 1.5 }}>
                        Type the question you just asked the candidate, then click Check.
                        The system evaluates their last spoken response.
                      </div>
                      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                        <input
                          ref={credInputRef}
                          className="sh-input"
                          value={credQuestion}
                          onChange={(e: any) => setCredQuestion(e.target.value)}
                          placeholder="e.g. Explain polymorphism in OOP…"
                          style={{ fontSize: 9, padding: "6px 10px" }}
                          onKeyDown={(e: any) => { if (e.key === "Enter" && !credLoading) checkCredibility() }}
                        />
                        <button
                          onClick={checkCredibility}
                          disabled={credLoading || !credQuestion.trim()}
                          style={{
                            background: credLoading ? "#1e293b" : "linear-gradient(135deg,#7c3aed,#a855f7)",
                            border: "none", borderRadius: 8, padding: "0 10px",
                            color: "#fff", fontSize: 9, cursor: credLoading || !credQuestion.trim() ? "not-allowed" : "pointer",
                            whiteSpace: "nowrap", opacity: credLoading || !credQuestion.trim() ? 0.5 : 1,
                            minWidth: 56, display: "flex", alignItems: "center", justifyContent: "center", gap: 4
                          }}
                        >
                          {credLoading
                            ? <span className="sh-spin" style={{ width: 8, height: 8, border: "2px solid rgba(255,255,255,.3)", borderTopColor: "#fff", borderRadius: "50%", display: "inline-block" }} />
                            : "Check"}
                        </button>
                      </div>

                      {/* Results log */}
                      {credResults.length > 0 && (
                        <div className="sh-scroll" style={{ maxHeight: 220, overflowY: "auto" }}>
                          {credResults.map((r, i) => {
                            const cc = credColor(r.verdict)
                            return (
                              <div key={i} className="sh-fadein" style={{
                                background: `${cc}08`, border: `1px solid ${cc}25`,
                                borderRadius: 8, padding: "8px 10px", marginBottom: 5
                              }}>
                                {/* Question + verdict badge */}
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 6, marginBottom: 4 }}>
                                  <div style={{ color: "#e2e8f0", fontSize: 8, lineHeight: 1.5, flex: 1 }}>
                                    Q: {r.question.length > 80 ? r.question.slice(0, 80) + "…" : r.question}
                                  </div>
                                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, flexShrink: 0 }}>
                                    <span style={{ fontSize: 7, padding: "2px 7px", borderRadius: 99, background: `${cc}20`, border: `1px solid ${cc}40`, color: cc, fontWeight: 700 }}>
                                      {r.verdict}
                                    </span>
                                    <span style={{ color: cc, fontSize: 9, fontWeight: 700 }}>{r.score}/100</span>
                                  </div>
                                </div>
                                {/* Explanation */}
                                <div style={{ color: "#94a3b8", fontSize: 7, lineHeight: 1.5, marginBottom: r.key_points_hit.length > 0 || r.key_points_missed.length > 0 ? 4 : 0 }}>
                                  {r.explanation}
                                </div>
                                {/* Key points */}
                                {r.key_points_hit.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 2, marginBottom: 2 }}>
                                    {r.key_points_hit.slice(0, 3).map((p, pi) => (
                                      <span key={pi} style={{ fontSize: 6, padding: "1px 5px", borderRadius: 99, background: "#10b98112", border: "1px solid #10b98128", color: "#6ee7b7" }}>✓ {p}</span>
                                    ))}
                                  </div>
                                )}
                                {r.key_points_missed.length > 0 && (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 2, marginBottom: r.suggestions ? 4 : 0 }}>
                                    {r.key_points_missed.slice(0, 3).map((p, pi) => (
                                      <span key={pi} style={{ fontSize: 6, padding: "1px 5px", borderRadius: 99, background: "#ef444412", border: "1px solid #ef444428", color: "#fca5a5" }}>✗ {p}</span>
                                    ))}
                                  </div>
                                )}
                                {/* Suggestion */}
                                {r.suggestions && (
                                  <div style={{ color: "#7c5cf5", fontSize: 7, lineHeight: 1.4, paddingLeft: 7, borderLeft: "2px solid #7c5cf530", marginTop: 2 }}>
                                    💡 {r.suggestions}
                                  </div>
                                )}
                              </div>
                            )
                          })}
                        </div>
                      )}

                      {credResults.length === 0 && (
                        <div style={{ color: "#334155", fontSize: 8, textAlign: "center", padding: "8px 0", fontStyle: "italic" }}>
                          No checks yet — type a question above and click Check.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })()}

            {/* Quick stats */}
            {live && <div style={{ margin: "0 14px 10px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 5 }}>
              {[
                { l: "LSDI", v: live.lsdi?.toFixed(1) ?? "--", c: scC },
                { l: "Style Shift", v: live.style_shift, c: { LOW: "#10b981", MODERATE: "#f59e0b", HIGH: "#f97316", "VERY HIGH": "#ef4444" }[live.style_shift as string] ?? "#94a3b8" },
                { l: "Signals", v: `${live.strong_signals ?? 0}/14`, c: (live.strong_signals ?? 0) >= 4 ? "#ef4444" : (live.strong_signals ?? 0) >= 2 ? "#f59e0b" : "#10b981" },
              ].map(({ l, v, c }) => (
                <div key={l} style={{ background: "#ffffff06", border: "1px solid #ffffff0a", borderRadius: 9, padding: "7px 5px", textAlign: "center" }}>
                  <div style={{ color: c, fontSize: 10, fontWeight: 700 }}>{v}</div>
                  <div style={{ color: "#334155", fontSize: 7, marginTop: 1 }}>{l}</div>
                </div>
              ))}
            </div>}


            {/* Metrics */}
            {live && <div style={{ margin: "0 14px 10px" }}>
              <div style={{ color: "#334155", fontSize: 8, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 6 }}>Live vs Personal Baseline</div>
              {[
                { l: "Formality",         v: live.formality,                b: live.base_formality,   max: 100, color: "#059669" },
                { l: "Vocabulary",        v: live.vocabulary,               b: live.base_vocabulary,  max: 100, color: "#059669" },
                { l: "Grammar",           v: live.grammar,                  b: live.base_grammar,     max: 100, color: "#14b8a6" },
                { l: "Lexical Diversity", v: live.lexical_diversity * 100,  b: 0,                     max: 100, color: "#f59e0b" },
                { l: "Fillers",           v: live.filler_ratio * 100,       b: live.base_filler*100,  max: 30,  color: "#10b981" },
                { l: "Transitions",       v: live.transition_density*1000,  b: 0,                     max: 100, color: "#ec4899" },
                { l: "FK Grade",          v: live.flesch_kincaid ?? 0,      b: 0,                     max: 18,  color: "#f97316" },
                { l: "Gunning Fog",       v: live.gunning_fog ?? 0,         b: 0,                     max: 18,  color: "#fb923c" },
                { l: "Passive Voice",     v: (live.passive_voice ?? 0)*100, b: 0,                     max: 50,  color: "#fbbf24" },
                { l: "Burstiness",        v: (live.sentence_burstiness ?? 0)*100, b: 0,               max: 100, color: "#64748b" },
                { l: "AI Boilerplate",    v: live.ai_boilerplate ?? 0,      b: 0,                     max: 5,   color: "#ef4444" },
                { l: "Pronouns",          v: (live.pronouns ?? 0)*100,      b: 0,                     max: 20,  color: "#06b6d4" },
                { l: "AI Starters",       v: (live.ai_starters ?? 0)*100,   b: 0,                     max: 100, color: "#ef4444" },
                { l: "Avg Sent Len",      v: live.avg_sent_len ?? 0,        b: 0,                     max: 40,  color: "#94a3b8", fmt: (v: number) => v.toFixed(1)+"w" },
              ].map(({ l, v, b, max, color, fmt }: any) => {
                const delta = b > 0 ? v - b : null
                const deltaStr = delta !== null ? ` (${delta > 0 ? "+" : ""}${delta.toFixed(0)})` : ""
                const deltaColor = delta !== null && Math.abs(delta) > 15 ? "#f87171" : "#475569"
                return (
                  <div key={l} style={S.row}>
                    <div style={S.rl}>
                      <span style={{ color: "#64748b", fontSize: 9 }}>{l}</span>
                      <span style={{ color: "#94a3b8", fontSize: 10, fontWeight: 600 }}>
                        {fmt ? fmt(v) : v.toFixed(1)}<span style={{ color: deltaColor, fontSize: 7 }}>{deltaStr}</span>
                      </span>
                    </div>
                    <Bar value={v} max={max} color={color} />
                  </div>
                )
              })}
            </div>}

            {/* ML + Drift + Plag */}
            {live && <div style={{ margin: "0 14px 10px", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 5 }}>
              <div style={{ background: "#ffffff06", border: "1px solid #ffffff0a", borderRadius: 9, padding: "7px 8px" }}>
                <div style={{ color: "#475569", fontSize: 7, marginBottom: 3 }}>ML Classifier</div>
                {live.ml_prob !== null ? <>
                  <div style={{ color: live.ml_prob > 0.7 ? "#ef4444" : live.ml_prob > 0.4 ? "#f59e0b" : "#10b981", fontSize: 13, fontWeight: 700 }}>{(live.ml_prob * 100).toFixed(0)}%</div>
                  <div style={{ color: "#334155", fontSize: 7 }}>AI-assist prob</div>
                  <Bar value={live.ml_prob * 100} color={live.ml_prob > 0.7 ? "#ef4444" : "#f59e0b"} />
                </> : <div style={{ color: "#334155", fontSize: 8 }}>Heuristic only</div>}
              </div>
              <div style={{ background: live.has_spike ? "#ef444410" : "#ffffff06", border: `1px solid ${live.has_spike ? "#ef444430" : "#ffffff0a"}`, borderRadius: 9, padding: "7px 8px" }}>
                <div style={{ color: "#475569", fontSize: 7, marginBottom: 3 }}>Temporal Drift</div>
                {live.has_spike ? <><div style={{ color: "#ef4444", fontSize: 11, fontWeight: 700 }}>⚠ SPIKE</div><div style={{ color: "#ef4444", fontSize: 7 }}>+{live.drift_score.toFixed(0)}pts</div></>
                  : <><div style={{ color: "#10b981", fontSize: 11, fontWeight: 700 }}>✓ Stable</div><div style={{ color: "#334155", fontSize: 7 }}>No spike</div></>}
              </div>
              <div style={{ background: plagRisk >= 60 ? "#ef444410" : plagRisk >= 35 ? "#f59e0b10" : "#ffffff06", border: `1px solid ${pc}30`, borderRadius: 9, padding: "7px 8px" }}>
                <div style={{ color: "#475569", fontSize: 7, marginBottom: 3 }}>Script Risk</div>
                <div style={{ color: pc, fontSize: 13, fontWeight: 700 }}>{plagRisk.toFixed(0)}%</div>
                <div style={{ color: "#334155", fontSize: 7 }}>{plagRisk >= 60 ? "High" : plagRisk >= 35 ? "Moderate" : "Clean"}</div>
                <Bar value={plagRisk} color={pc} />
              </div>
            </div>}

            {/* Flags */}
            {live && live.flags.length > 0 && <div style={{ margin: "0 14px 10px" }}>
              <button onClick={() => setShowFlags(!showFlags)} style={{ background: "#ef444415", border: "1px solid #ef444430", color: "#f87171", borderRadius: 7, padding: "5px 10px", width: "100%", cursor: "pointer", fontSize: 9, fontWeight: 700, display: "flex", justifyContent: "space-between" }}>
                <span>⚑ {live.flags.length} Flag{live.flags.length > 1 ? "s" : ""}</span><span>{showFlags ? "▲" : "▼"}</span>
              </button>
              {showFlags && <div className="sh-scroll" style={{ maxHeight: 110, overflowY: "auto", marginTop: 4 }}>
                {live.flags.map((f, i) => <div key={i} style={{ background: "#ef444408", border: "1px solid #ef444420", borderRadius: 7, padding: "5px 8px", marginBottom: 3, color: "#fca5a5", fontSize: 8, lineHeight: 1.5 }}>⚑ {f}</div>)}
              </div>}
            </div>}


            </div>
          )}
        </GlassCard>
      </div>
      </>
    )
  }

  // ─── PHASE: REPORT ────────────────────────────────────────────────────────
  const last = sessionLog[sessionLog.length - 1] ?? live
  const fScore = sessionLog.length ? (sessionLog.reduce((a, b) => a + b.score, 0) / sessionLog.length) : (last?.score ?? 0)
  let fVerdict = last?.verdict ?? "NEEDS REVIEW"
  if (sessionLog.length > 0) {
    if (fScore < 40) fVerdict = "HIGHLY SUSPICIOUS"
    else if (fScore < 60) fVerdict = "SUSPICIOUS"
    else if (fScore < 80) fVerdict = "NEEDS REVIEW"
    else fVerdict = "GENUINE"
  }
  const vs2 = vStyle(fVerdict)
  const fColor = fScore >= 80 ? "#10b981" : fScore >= 60 ? "#f59e0b" : fScore >= 40 ? "#f97316" : "#ef4444"
  const avgScore = Math.round(fScore)
  const allFlags = Array.from(new Set(sessionLog.flatMap(s => s.flags)))
  const pc2 = plagRisk >= 60 ? "#ef4444" : plagRisk >= 35 ? "#f59e0b" : "#10b981"
  const ts = new Date().toLocaleString()

  const dlReport = () => {
    const flagged = sessionLog.filter(s => s.flags && s.flags.length > 0)
    const html = `<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>SachhAI Report — ${candidateName}</title>
<style>
body{font-family:'Segoe UI',sans-serif;background:#06080f;color:#e2e8f0;padding:40px;max-width:820px;margin:0 auto}
h1{font-size:2rem;font-weight:800;margin-bottom:4px;color:#f1f5f9}
h2{font-size:1rem;font-weight:700;color:#94a3b8;margin:24px 0 10px;text-transform:uppercase;letter-spacing:1px}
.meta{color:#64748b;font-size:.82rem;margin-bottom:24px}
.score{font-size:4.5rem;font-weight:900;color:${fColor};line-height:1}
.verdict{display:inline-block;padding:4px 18px;border-radius:99px;background:${vs2.txt}20;border:1px solid ${vs2.txt}40;color:${vs2.txt};font-size:.82rem;font-weight:700;letter-spacing:1.2px;margin:10px 0}
.summary{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:14px 16px;margin:16px 0;font-size:.88rem;line-height:1.75;color:#cbd5e1}
.moment{background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.25);border-radius:10px;padding:14px 16px;margin-bottom:12px}
.moment-hdr{display:flex;justify-content:space-between;color:#ef4444;font-weight:700;font-size:.85rem;margin-bottom:8px}
.flag{padding:6px 0 6px 12px;border-left:2px solid rgba(239,68,68,.4);color:#fca5a5;font-size:.82rem;line-height:1.6;margin-bottom:4px}
.clear{background:rgba(16,185,129,.07);border:1px solid rgba(16,185,129,.3);border-radius:10px;padding:20px;text-align:center;color:#10b981;font-size:1rem;font-weight:700}
.q{padding:8px 12px;border-radius:8px;background:rgba(99,102,241,.07);border:1px solid rgba(99,102,241,.2);color:#c7d2fe;margin-bottom:6px;font-size:.82rem;line-height:1.5}
.spike{background:rgba(239,68,68,.07);border:1px solid rgba(239,68,68,.3);border-radius:10px;padding:12px 16px;margin-bottom:16px;color:#f87171;font-size:.85rem}
.muted{color:#64748b;font-size:.78rem}
@media print{body{background:white;color:#111}.muted{color:#555}}
</style></head><body>
<h1>SachhAI AI-Assistance Report</h1>
<div class="meta">
  <strong>Candidate:</strong> ${candidateName} &nbsp;|&nbsp;
  <strong>Role:</strong> ${role || "N/A"} &nbsp;|&nbsp;
  <strong>Interviewer:</strong> ${authDisplayName || authUser}<br/>
  <strong>Date:</strong> ${ts} &nbsp;|&nbsp;
  <strong>Duration:</strong> ${fmt(elapsed)} &nbsp;|&nbsp;
  <strong>Words spoken:</strong> ${last?.total_words ?? 0}
  ${savedId ? `&nbsp;|&nbsp;<strong>Session ID:</strong> ${savedId}` : ""}
</div>
<div class="score">${fScore.toFixed(1)}</div>
<div class="verdict">${fVerdict}</div>
<p class="muted">Session average: ${avgScore}/100</p>
<h2>Key Metrics</h2>
<div class="grid2">
  <div class="tile"><div class="tile-label">LSDI Score</div><div class="tile-val">${last?.lsdi?.toFixed(1) ?? "—"}</div></div>
  <div class="tile"><div class="tile-label">Style Shift</div><div class="tile-val">${last?.style_shift ?? "—"}</div></div>
  <div class="tile"><div class="tile-label">Formality</div><div class="tile-val">${last?.formality?.toFixed(0) ?? "—"}/100</div></div>
  <div class="tile"><div class="tile-label">Vocabulary</div><div class="tile-val">${last?.vocabulary?.toFixed(0) ?? "—"}/100</div></div>
  <div class="tile"><div class="tile-label">Grammar</div><div class="tile-val">${last?.grammar?.toFixed(0) ?? "—"}/100</div></div>
  <div class="tile"><div class="tile-label">Lexical Div</div><div class="tile-val">${last ? ((last.lexical_diversity || 0) * 100).toFixed(0) : 0}%</div></div>
  <div class="tile"><div class="tile-label">Transitions</div><div class="tile-val">${last ? ((last.transition_density || 0) * 1000).toFixed(1) : 0}</div></div>
  <div class="tile"><div class="tile-label">ML AI-Prob</div><div class="tile-val">${last?.ml_prob !== null && last?.ml_prob !== undefined ? (last.ml_prob * 100).toFixed(0) + "%" : "N/A"}</div></div>
  <div class="tile"><div class="tile-label">Strong Signals</div><div class="tile-val">${last?.strong_signals ?? "—"}/6</div></div>
  <div class="tile"><div class="tile-label">Temporal Drift</div><div class="tile-val">${last?.has_spike ? "⚠ ⚠ SPIKE DETECTED" : "✓ Stable"}</div></div>
</div>
<div class="plag">
  <strong style="color:${pc2}">Script/Plagiarism Risk: ${plagRisk.toFixed(0)}%</strong><br>
  <span class="muted">${plagVerdict}</span>
  ${plagSignals.map(s => `<div class="muted" style="margin-top:4px">• ${s}</div>`).join("")}
</div>
<h2>Detected Flags (${allFlags.length})</h2>
${allFlags.length ? allFlags.map(f => `<div class="flag">⚑ ${f}</div>`).join("") : "<p class='muted'>No flags detected.</p>"}
<h2>Suggested Follow-up Questions</h2>
${questions.length ? questions.map((q, i) => `<div class="q">${i + 1}. ${q}</div>`).join("") : "<p class='muted'>No questions generated yet.</p>"}
<h2>Temporal Drift Analysis</h2>
<div style="background:${last?.has_spike ? "rgba(239,68,68,.07)" : "rgba(16,185,129,.07)"};border:1px solid ${last?.has_spike ? "rgba(239,68,68,.3)" : "rgba(16,185,129,.3)"};border-radius:10px;padding:12px 16px;margin-bottom:16px">
  <strong style="color:${last?.has_spike ? "#ef4444" : "#10b981"}">${last?.has_spike ? "⚠ ⚠ SPIKE DETECTED — Sudden style change" : "✓ No spike — Stable throughout"}</strong><br/>
  ${last?.drift_score ? `<span class="muted">Drift score: ${(last.drift_score || 0).toFixed(1)} pts</span><br/>` : ''}  ${last?.session_drift != null ? `<span class="muted">Session drift (early→late): ${(last.session_drift || 0) > 0 ? "" : "" + (last.session_drift || 0).toFixed(1)} pts</span><br/>` : ''}  <span class="muted">Analysis mode: ${last?.analysis_mode || "heuristic"}${last?.ml_prob != null ? " | ML AI-assist prob: " + (last.ml_prob * 100).toFixed(0) + "%" : " | ML model not available"}</span>
</div>
<h2>Analysis Summary</h2>
<p style="line-height:1.75;font-size:.88rem">${last?.summary ?? ""}</p>
<hr style="border-color:rgba(255,255,255,.08);margin:28px 0"/>
<p class="muted">Generated by SachhAI · <a href="${API}/interview" style="color:#2563eb">${API}/interview</a></p>
</body></html>`
    const blob = new Blob([html], { type: "text/html" })
    const a = document.createElement("a")
    a.href = URL.createObjectURL(blob)
    a.download = `SachhAI_${candidateName.replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.html`
    a.click()
  }

  return (
    <div className="sh-root sh-fadein" style={{ position: "fixed", top: 72, right: 14, zIndex: 9999, width: 360, fontFamily: "'Inter',sans-serif" }}>
      <GlassCard bdr={vs2.bdr} glow={vs2.glow} bg={vs2.bg}>
        {/* Header */}
        <div style={S.hdr}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Logo />
            <div>
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 12 }}>Report · {candidateName}</div>
              <div style={{ color: "#94a3b8", fontSize: 9 }}>{fmt(elapsed)} · {last?.total_words ?? 0} words · {authDisplayName || authUser}</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <a href={`${API}/dashboard`} target="_blank" rel="noreferrer" style={{ color: "#d97706", fontSize: 9, textDecoration: "none", fontWeight: 700 }}>Dashboard →</a>
            <button onClick={closeOverlay} style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)", color: "#94a3b8", borderRadius: 5, padding: "2px 6px", fontSize: 10, cursor: "pointer", fontWeight: 700 }}>X</button>
          </div>
        </div>

        <div style={{ ...S.body, maxHeight: "80vh", overflowY: "auto" }} className="sh-scroll">

          {/* ── Final verdict ── */}
          <div style={{ textAlign: "center", marginBottom: 14, padding: "14px", background: "rgba(255,255,255,0.02)", borderRadius: 12, border: `1px solid ${GLASS_BDR}` }}>
            <div style={{ color: "#94a3b8", fontSize: 8, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 4 }}>Final Verdict</div>
            <div style={{ fontSize: 48, fontWeight: 800, color: fColor, lineHeight: 1, letterSpacing: -2 }}>{fScore.toFixed(1)}</div>
            <div style={{ marginTop: 8 }}><Pill text={fVerdict} bg={`${vs2.txt}18`} border={`${vs2.txt}40`} color={vs2.txt} /></div>
            <div style={{ color: "#cbd5e1", fontSize: 8, marginTop: 6 }}>{last?.summary ?? ""}</div>
          </div>

          {/* ── Post-Session Analysis Panel ── */}
          {last && (
            <div style={{ marginBottom: 14, background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 12, padding: "12px 14px" }}>
              <div style={{ color: "#fbbf24", fontSize: 8, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 10 }}>
                📊 Post-Session Linguistic Analysis
              </div>

              {/* Key metrics row */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 10 }}>
                {[
                  { label: "LSDI Score",   value: last.lsdi?.toFixed(1) ?? "—",    color: (last.lsdi ?? 0) > 60 ? "#ef4444" : "#10b981" },
                  { label: "Style Shift",  value: last.style_shift ?? "—",          color: last.style_shift === "LOW" ? "#10b981" : last.style_shift === "MODERATE" ? "#f59e0b" : "#ef4444" },
                  { label: "Strong Signals",value: `${last.strong_signals ?? 0}`,   color: (last.strong_signals ?? 0) >= 4 ? "#ef4444" : "#94a3b8" },
                  { label: "Plagiarism Risk",value: `${plagRisk.toFixed(0)}%`,      color: plagRisk >= 60 ? "#ef4444" : plagRisk >= 35 ? "#f59e0b" : "#10b981" },
                  { label: "Confidence",   value: last.confidence_v2?.label ?? "—",color: "#94a3b8" },
                  { label: "Mode",         value: last.analysis_mode ?? "heuristic",color: "#64748b" },
                ].map(({ label, value, color }) => (
                  <div key={label} style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 8, padding: "7px 9px" }}>
                    <div style={{ color: "#475569", fontSize: 7, marginBottom: 2 }}>{label}</div>
                    <div style={{ color, fontSize: 11, fontWeight: 700 }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* 11 Linguistic features — personal vs technical deltas */}
              <div style={{ color: "#334155", fontSize: 7, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", marginBottom: 6 }}>11 Linguistic Features (Personal → Technical)</div>
              {[
                { label: "Formality",       p: profile?.formality_score,        t: last?.formality,          hi: true  },
                { label: "Vocabulary",      p: profile?.vocabulary_level,       t: last?.vocabulary,         hi: true  },
                { label: "Flesch-Kincaid",  p: profile?.flesch_kincaid,         t: last?.flesch_kincaid,     hi: true  },
                { label: "Gunning Fog",     p: profile?.gunning_fog,            t: last?.gunning_fog,        hi: true  },
                { label: "Grammar",         p: profile?.grammar_score,          t: last?.grammar,            hi: false },
                { label: "Filler Words",    p: profile?.filler_ratio ? +(profile.filler_ratio*100).toFixed(1) : 0, t: last?.filler_ratio ? +(last.filler_ratio*100).toFixed(1) : 0, hi: false },
                { label: "Burstiness",      p: profile?.sentence_burstiness,    t: last?.sentence_burstiness, hi: false },
                { label: "Avg Sent Len",    p: profile?.avg_sentence_len,       t: last?.avg_sent_len,       hi: true  },
                { label: "Transitions",     p: profile?.transition_density ? +(profile.transition_density*100).toFixed(2) : 0, t: last?.transition_density ? +(last.transition_density*100).toFixed(2) : 0, hi: true },
                { label: "AI Boilerplate",  p: 0,                               t: last?.ai_boilerplate,     hi: true  },
                { label: "Pronouns",        p: profile?.personal_pronoun_ratio ? +(profile.personal_pronoun_ratio*100).toFixed(1) : 0, t: last?.pronouns ? +(last.pronouns*100).toFixed(1) : 0, hi: false },
              ].map(({ label, p, t, hi }) => {
                const pv = p ?? 0
                const tv = t ?? 0
                const delta = tv - pv
                const suspicious = hi ? delta > 12 : delta < -0.05
                const clr = suspicious ? "#f87171" : "#10b981"
                return (
                  <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <span style={{ color: "#64748b", fontSize: 7.5, minWidth: 90 }}>{label}</span>
                    <span style={{ color: "#475569", fontSize: 7.5 }}>{typeof pv === 'number' ? pv.toFixed(1) : pv}</span>
                    <span style={{ color: "#334155", fontSize: 7 }}>→</span>
                    <span style={{ color: "#cbd5e1", fontSize: 7.5, fontWeight: 600 }}>{typeof tv === 'number' ? tv.toFixed(1) : tv}</span>
                    <span style={{ color: clr, fontSize: 7.5, fontWeight: 700, minWidth: 38, textAlign: "right" }}>{delta > 0 ? "+" : ""}{typeof delta === 'number' ? delta.toFixed(1) : delta}</span>
                  </div>
                )
              })}

              {/* Temporal drift */}
              <div style={{ marginTop: 10, padding: "8px 10px", borderRadius: 8, background: last?.has_spike ? "#ef444410" : "#10b98110", border: `1px solid ${last?.has_spike ? "#ef444430" : "#10b98130"}` }}>
                <span style={{ color: last?.has_spike ? "#f87171" : "#6ee7b7", fontSize: 8, fontWeight: 700 }}>
                  {last?.has_spike ? `⏱ Mid-session spike +${(last.drift_score || 0).toFixed(0)}pts` : "✓ Consistent throughout session"}
                </span>
                {last?.session_drift != null && (
                  <span style={{ color: "#475569", fontSize: 7, marginLeft: 8 }}>
                    Session drift: {(last.session_drift || 0) > 0 ? "+" : ""}{(last.session_drift || 0).toFixed(1)}pts
                  </span>
                )}
              </div>
            </div>
          )}

          {/* ── Flagged answers ONLY ── */}
          {(() => {
            const flaggedSnapshots = sessionLog.filter(s => s.flags && s.flags.length > 0)
            if (flaggedSnapshots.length === 0) {
              return (
                <div style={{ textAlign: "center", padding: "20px 14px", background: "#10b98110", border: "1px solid #10b98140", borderRadius: 10, marginBottom: 12 }}>
                  <div style={{ fontSize: 22 }}>✅</div>
                  <div style={{ color: "#10b981", fontWeight: 700, fontSize: 11, marginTop: 6 }}>No AI Assistance Detected</div>
                  <div style={{ color: "#94a3b8", fontSize: 8, marginTop: 4 }}>No flags triggered during the interview.</div>
                </div>
              )
            }
            return (
              <div style={{ marginBottom: 12 }}>
                <div style={{ color: "#ef4444", fontSize: 8, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 8 }}>
                  ⚑ {flaggedSnapshots.length} Flagged Moment{flaggedSnapshots.length > 1 ? "s" : ""}
                </div>
                {flaggedSnapshots.map((snap, i) => (
                  <div key={i} style={{ background: "#ef444408", border: "1px solid #ef444430", borderRadius: 10, padding: "10px 12px", marginBottom: 8 }}>
                    {/* Moment header */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <span style={{ color: "#ef4444", fontSize: 9, fontWeight: 700 }}>Moment {i + 1}</span>
                      <span style={{ color: "#f87171", fontSize: 9, fontWeight: 700 }}>Auth: {snap.score.toFixed(0)} · LSDI: {snap.lsdi.toFixed(0)}</span>
                    </div>
                    {/* Flags */}
                    {snap.flags.map((f, fi) => (
                      <div key={fi} style={{ color: "#fca5a5", fontSize: 8, lineHeight: 1.6, marginBottom: 3, paddingLeft: 8, borderLeft: "2px solid #ef444440" }}>
                        {f}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )
          })()}

          {/* ── Follow-up questions ── */}
          {questions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ color: "#d97706", fontSize: 8, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 6 }}>
                💡 💡 Suggested Follow-ups
              </div>
              {questions.map((q, i) => (
                <div key={i} style={{ background: "rgba(0,245,255,0.05)", border: "1px solid rgba(0,245,255,0.2)", borderRadius: 8, padding: "6px 10px", marginBottom: 4, color: "#e2e8f0", fontSize: 8, lineHeight: 1.6 }}>
                  {i + 1}. {q}
                </div>
              ))}
            </div>
          )}

          {/* ── Temporal spike (only show if it fired) ── */}
          {last?.has_spike && (
            <div style={{ marginBottom: 12, padding: "9px 12px", borderRadius: 9, background: "#ef444410", border: "1px solid #ef444440" }}>
              <div style={{ color: "#ef4444", fontWeight: 700, fontSize: 9, marginBottom: 3 }}>⏱ Mid-Answer Style Spike Detected</div>
              <div style={{ color: "#fca5a5", fontSize: 8 }}>
                Complexity spiked +{last.drift_score.toFixed(0)}pts — candidate likely started naturally then switched to AI text.
              </div>
            </div>
          )}

          {/* ── Actions ── */}
          <button onClick={dlReport} style={S.btn("linear-gradient(to right,#d97706,#059669)")}>⬇ Download Report</button>
          <button onClick={() => { setPhase("info"); setLive(null); setSessionLog([]); setQuestions([]); setPlagRisk(0); setElapsed(0); setSavedId(""); setCandidateName(""); setCredResults([]); setShowCred(false); setCredQuestion("") }} style={{ ...S.btn("rgba(255,255,255,0.05)", 4), fontSize: 10, border: `1px solid ${GLASS_BDR}` }}>↺ New Session</button>
        </div>
      </GlassCard>
    </div>
  )
}

