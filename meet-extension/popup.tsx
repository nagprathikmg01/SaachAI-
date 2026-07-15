import { useState, useEffect } from "react"
import "./style.css"

const API = "https://naagazz-interview-checker.hf.space"

export default function IndexPopup() {
  const [enabled, setEnabled] = useState(true)
  const [audioMode, setAudioMode] = useState("candidate") // "candidate" | "both"
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  // ── Load persisted toggle state on mount ──────────────────────────────────
  useEffect(() => {
    chrome.storage.local.get(["sachhAI_enabled", "sachhAI_audioMode"], (r) => {
      if (r.sachhAI_enabled !== undefined) setEnabled(r.sachhAI_enabled)
      if (r.sachhAI_audioMode !== undefined) setAudioMode(r.sachhAI_audioMode)
    })
  }, [])

  // ── Ping backend health on mount ──────────────────────────────────────────
  useEffect(() => {
    fetch(`${API}/health`, { signal: AbortSignal.timeout(6000) })
      .then((r) => setBackendOk(r.ok))
      .catch(() => setBackendOk(false))
  }, [])

  // ── Toggle handlers: persist + notify active Meet tab ─────────────────────
  const notifyMeetTabs = (changes: any) => {
    chrome.tabs.query({ url: "https://meet.google.com/*" }, (tabs) => {
      tabs.forEach((tab) => {
        if (tab.id) {
          chrome.tabs.sendMessage(tab.id, { type: "SACHHÁI_CONFIG_UPDATE", ...changes }).catch(() => {})
        }
      })
    })
  }

  const handleToggle = () => {
    const next = !enabled
    setEnabled(next)
    chrome.storage.local.set({ sachhAI_enabled: next })
    notifyMeetTabs({ enabled: next })
  }

  const handleAudioMode = (mode: string) => {
    setAudioMode(mode)
    chrome.storage.local.set({ sachhAI_audioMode: mode })
    notifyMeetTabs({ audioMode: mode })
  }

  return (
    <div className="w-80 p-0 text-white font-sans overflow-hidden relative shadow-2xl">
      {/* Background radial gradient mimicking --bg-deep to --bg-dark to --bg-mid */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#1a0a2e,#04060f_40%,#0d1b2a_100%)] z-0" />

      {/* Glow Orbs */}
      <div className="absolute -top-10 -left-10 w-32 h-32 bg-[#7c3aed] rounded-full blur-[80px] opacity-40 z-0" />
      <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-[#00f5ff] rounded-full blur-[80px] opacity-20 z-0" />

      <div className="relative z-10 p-5 pb-4">
        {/* Header */}
        <div className="flex items-center gap-3 mb-5 border-b border-[rgba(255,255,255,0.08)] pb-4">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-[#7c3aed] to-[#00f5ff] p-[1px]">
            <div className="w-full h-full bg-[#04060f] rounded-xl flex items-center justify-center">
              <svg width="20" height="20" viewBox="0 0 34 34" fill="none" xmlns="http://www.w3.org/2000/svg">
                <ellipse cx="17" cy="16" rx="9" ry="6" stroke="#00f5ff" strokeWidth="1.8" fill="none"/>
                <circle cx="17" cy="16" r="3" fill="#7c3aed"/>
                <polyline points="11,24 14,27 22,20" stroke="#00f5ff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              </svg>
            </div>
          </div>
          <div>
            <h1 className="text-[1.1rem] font-bold text-white tracking-wide">SachhAI</h1>
            <p className="text-[0.75rem] text-[#94a3b8]">Authenticity Engine</p>
          </div>
        </div>

        <div className="space-y-3">
          {/* Main Overlay Toggle */}
          <div className="bg-[rgba(255,255,255,0.03)] backdrop-blur-md rounded-xl p-4 border border-[rgba(255,255,255,0.08)] hover:border-[#00f5ff]/30 transition-colors">
            <div className="flex justify-between items-center mb-1.5">
              <span className="text-sm font-medium text-[#e2e8f0]">Live Analysis</span>
              <button
                onClick={handleToggle}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${enabled ? "bg-[#10b981]" : "bg-[#334155]"}`}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm transition-transform ${enabled ? "translate-x-4.5" : "translate-x-1"}`} />
              </button>
            </div>
            <p className="text-[0.7rem] text-[#94a3b8] leading-relaxed">
              {enabled ? "Monitoring active. Dashboard will populate in Meet." : "Engine paused. Turn on to resume analysis."}
            </p>
          </div>

          {/* Audio Source Selector */}
          <div className="bg-[rgba(255,255,255,0.03)] backdrop-blur-md rounded-xl p-4 border border-[rgba(255,255,255,0.08)]">
            <span className="text-sm font-medium text-[#e2e8f0] block mb-2">Capture Mode</span>
            <div className="flex bg-[#04060f]/50 p-1 rounded-lg border border-[rgba(255,255,255,0.05)]">
              <button
                onClick={() => handleAudioMode("candidate")}
                className={`flex-1 text-[0.75rem] py-1.5 rounded-md transition-all ${audioMode === "candidate" ? "bg-[rgba(0,245,255,0.15)] text-[#00f5ff] font-medium shadow-sm" : "text-[#94a3b8] hover:text-white"}`}
              >
                Candidate Only
              </button>
              <button
                onClick={() => handleAudioMode("both")}
                className={`flex-1 text-[0.75rem] py-1.5 rounded-md transition-all ${audioMode === "both" ? "bg-[rgba(124,58,237,0.15)] text-[#7c3aed] font-medium shadow-sm" : "text-[#94a3b8] hover:text-white"}`}
              >
                Both Voices
              </button>
            </div>
            <p className="text-[0.65rem] text-[#94a3b8] mt-2 leading-tight">
              {audioMode === "candidate" ? "Best accuracy. Isolates interviewee's speech via Meet CC." : "Mixed mode. Evaluates both speakers simultaneously."}
            </p>
          </div>

          {/* Backend Status */}
          <div
            className={`p-3 rounded-xl border text-[0.75rem] flex gap-2.5 items-start bg-[rgba(255,255,255,0.02)] backdrop-blur-sm transition-colors ${
              backendOk === null
                ? "border-[rgba(255,255,255,0.1)] text-[#94a3b8]"
                : backendOk
                ? "border-[#10b981]/30 text-[#10b981]"
                : "border-red-500/30 text-red-400"
            }`}
          >
            <span className="mt-[2px] text-sm shrink-0">
              {backendOk === null ? "🔄" : backendOk ? "⚡" : "⚠️"}
            </span>
            <span className="leading-snug">
              {backendOk === null
                ? "Connecting to SachhAI cloud engine..."
                : backendOk
                ? "Cloud engine online. Connected to HF Space."
                : "Cloud backend offline. Analysis unavailable."}
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-5 pt-4 border-t border-[rgba(255,255,255,0.08)] flex justify-between items-center">
          <span className="text-[0.65rem] text-[#64748b] tracking-wider uppercase">v2.0 Glass</span>
          <a
            href={`${API}/interview`}
            target="_blank"
            rel="noreferrer"
            className="text-[0.75rem] font-medium text-[#00f5ff] hover:text-white transition-colors flex items-center gap-1"
          >
            Open Portal
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
          </a>
        </div>
      </div>
    </div>
  )
}
