# Manual Test Checklist: Google Meet Caption & Overlay Integration

This checklist defines the validation protocol for verifying the real-time Google Meet Caption scraping and the floating UI overlay inject. Since Google Meet requires active audio feeds and Google account sessions, these E2E operations must be performed manually.

---

## 1. Extension Injected State
- [ ] **Inject Script Check**:
  - Open a Google Meet session (e.g. `meet.google.com/abc-defg-hij`).
  - Right-click the page, click **Inspect**, and switch to the **Console** tab.
  - Verify that the message `[SachhAI] Real-Time CC Engine v3 injected` or similar is printed to the console on load.
- [ ] **Verify Captions Prerequisite**:
  - Make sure closed captions are enabled in Google Meet (click the **CC** button in the bottom meet control bar).
  - *Note*: Google Meet overlay depends on Meet's native live closed captions. Verify that captions are appearing at the bottom of the screen when speakers are talking.

---

## 2. Floating UI Overlay Injection
- [ ] **Overlay Rendered**:
  - Check that a dark glassmorphic overlay appears in the top-right or bottom-right corner of the Meet window.
  - Verify it has the ID `sai-ol-v3`.
- [ ] **Calibration Phase UI**:
  - Verify that when the meet starts and you haven't spoken the baseline yet, the overlay displays:
    - Verdict: `CALIBRATING`
    - Score: `—`
    - Status message: `Listening for captions...`
- [ ] **Movable/Draggable Behavior**:
  - Click and drag the overlay to a different region of the screen.
  - Verify that it moves smoothly and snaps to the new position without glitching or resetting.

---

## 3. Real-Time Scraping & Backend Communication
- [ ] **Baseline Capture**:
  - Turn on mic and speak a personal introduction baseline (at least 30 words, e.g., describing your background, name, hobbies).
  - Verify that:
    - The overlay word counter increases.
    - A websocket message of type `baseline` is sent (check Chrome Developer Tools -> Network -> WS connection to `/voice/meet-analyze`).
    - The overlay phase message transitions from `CALIBRATING` to `BASELINE RECORDED` or similar once the word limit is hit.
- [ ] **Speech Deduplication & Filter**:
  - Speak repetitive filler phrases back-to-back (e.g. "so um like, so um like").
  - Open the Console and verify that the extension filters duplicate lines out and does not flood the backend with redundant WS transcripts.
  - Verify that non-speech elements (like Meet UI button clicks, links, or times) are correctly filtered out by the speech heuristic (`looksLikeSpeech`).

---

## 4. Live Verdict Transitions
- [ ] **Natural Response Verification**:
  - Speak naturally, keeping your conversational style matching your baseline (same filler density, short sentences, active voice).
  - Verify that the overlay displays:
    - Verdict: `GENUINE` or `LOW RISK` (green/teal badges).
    - Authenticity Score remains high (e.g., `85+`).
- [ ] **Assisted/AI Response Verification**:
  - Paste or read a highly formal, complex AI-generated technical answer (long words, zero filler words, passive voice, formal connectors).
  - Verify that the overlay displays:
    - Verdict transitions to `SUSPICIOUS` or `HIGH RISK` (orange/red badges).
    - Authenticity Score drops.
    - Behavior flags appear indicating why it was flagged (e.g., `Vocabulary Spike`, `Filler Word Drop`).
- [ ] **Short Answer Guardrail**:
  - Speak a very brief sentence (e.g. "I use Python.").
  - Verify that the overlay verdict remains neutral or caps at `NEEDS REVIEW` (yellow badge) with a status label: `Answer too short`.
