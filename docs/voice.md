# NEXUS Voice Architecture (Input + Output)

NEXUS speaks and listens entirely in the browser using the **Web Speech API** —
no cloud speech service, no audio streaming to a server. The backend never
touches audio; it only produces text, which the frontend vocalizes locally.

## Voice input (speech → text)

- Engine: `SpeechRecognition` / `webkitSpeechRecognition` (Chrome, Edge).
- Files: `frontend/shared/voice.js` (shared helpers), `frontend/chat.html`
  (standalone console), `frontend/index.html` + `frontend/holo.html`
  (command dock inside the Cognitive OS).
- **chat.html mode — continuous conversation**: recognition runs with
  `continuous = true`; when the engine ends a session (silence or internal
  timeout) the page quietly restarts it while the mic is armed, so listening
  never cuts off mid-thought. Transcripts accumulate across engine restarts
  (`finalBase` + interim results). Click the mic once to arm, again to disarm;
  the words stay in the composer either way.
- **Dock mode (index/holo) — voice commands with auto-dispatch**: speech is
  buffered and dispatched automatically after a natural pause
  (`FINISH_MS = 1500` ms of silence). The transcript is routed through
  `sendChat()`, and keyword routes (`checkVoiceRoutes`) intercept spoken
  commands like "open research" or "dream mode" before they reach the cortex.
- Mic states: the mic button pulses red while armed; the composer capsule
  gains a `.listening` cyan pulse in chat.html; the dock gem shows LISTENING.

## Voice output (text → speech)

- Engine: `speechSynthesis` with a **natural-voice preference chain** —
  Windows Natural/Online voices (Aria, Guy, Emma, Jenny) first, then Google
  en-US, then any English voice (`frontend/shared/voice.js → pickVoice()`).
- **Speech-safe text**: raw answers contain markdown, tables, and code, which
  sound terrible spoken aloud. `speakable()` strips code blocks, bold/italic
  markers, links (→ "a link"), table pipes, and collapses whitespace before
  anything is vocalized. The same sanitized text feeds the on-screen captions.
- **The chain-of-thought is never spoken** — reasoning arrives in a separate
  field from the answer (the backend `_call_llm` returns
  `(answer, reasoning)`), the answer is vocalized, and the reasoning renders
  as the faint collapsible "Thinking process" card only.
- Voice-out toggle: the speaker button in chat.html gates all speech; the
  docks mute via the `mute=1` URL parameter.

## React chat voice output (accent-first)

The main React app (`web/`) has its own canonical speech manager,
`web/src/utils/voiceManager.ts`, shared by the conversational chat, the
Voice Cortex, and the Jarvis console:

- **Default accent: Indian English (`en-IN`)** — e.g. Microsoft Neerja /
  Prabhat where available. British (`en-GB`), US (`en-US`), Australian
  (`en-AU`), Canadian (`en-CA`), and Irish (`en-IE`) English are selectable in
  the voice settings popover (chat header and top bar). If the browser has no
  exact-accent voice installed, the closest English voice is scored and used,
  and the UI says so — voice quality is whatever the browser/OS ships.
- Preferences (accent, specific voice, rate 0.5–1.5×, pitch 0.5–1.5×) persist
  in `localStorage` under `nexus_voice_prefs`. The settings popover includes a
  **Test voice** button and a master **Voice replies** switch (the same
  capability toggle as the chat's capabilities panel).
- When voice replies are on, the assistant's **actual final answer** is read
  aloud — never the Extended Thinking trace, tool calls, code blocks, or
  markdown syntax. `speakable()` strips those and the text is chunked to
  ~180 characters so long Chromium utterances don't stall.
- Every assistant message has a **Listen / Stop** button for replay, and the
  composer shows a global Stop while anything is speaking.

## Common failure modes (and their fixes in this repo)

- **Mic cuts off after ~1.5 s**: caused by `continuous = false` plus a fatal
  `onend`. Fixed with continuous listening + silent auto-restart.
- **Robotic/unclear voice**: fixed by natural-voice picking + markdown
  stripping + rate 0.98 / pitch 1.0.
- **Mic blocked**: the browser requires microphone permission for the page —
  allow it in site settings; the UI surfaces this as a red error strip.
