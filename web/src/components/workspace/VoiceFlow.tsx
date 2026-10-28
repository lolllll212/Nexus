import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Mic, MicOff, AudioLines } from 'lucide-react';
import { nexusJson } from '../../api';
import { getVoicePreferences } from '../../utils/voiceManager';

/* ────────────────────────────────────────────────────────────────────────────
 * WHISPER FLOW — the voice input for the NEXUS cockpit.
 *
 * Two stacked engines, one button:
 *   1. Web Speech Recognition (when the browser exposes it) — live interim
 *      transcription streamed into the console as you speak.
 *   2. MediaRecorder fallback — the mic is captured as a real audio blob and
 *      POSTed to the backend transcriber (POST /api/audio/stt, multipart
 *      upload, Whisper-1 engine).
 *
 * In both modes a Web Audio AnalyserNode reads the live microphone level, and
 * the WhisperFlowBand canvas paints amplitude-reactive flowing ribbons + wisp
 * particles — the "whisper flow" — so the animation literally breathes with
 * your voice.
 * ──────────────────────────────────────────────────────────────────────────── */

/* Minimal local typings for the Web Speech API (not in the DOM lib). */
interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
  length: number;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: SpeechRecognitionEventLike) => void) | null;
  onerror: ((ev: { error?: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type VoiceState = 'idle' | 'listening' | 'starting' | 'denied' | 'unsupported';

interface UseVoiceInputOptions {
  /** Live interim transcript (partial words as they are recognised). */
  onInterim?: (text: string) => void;
  /** A finalised phrase. */
  onFinal?: (text: string) => void;
  /** BCP-47 recognition language. Defaults to the saved Nexus accent (en-IN). */
  language?: string;
}

export function useVoiceInput({ onInterim, onFinal, language }: UseVoiceInputOptions = {}) {
  const [state, setState] = useState<VoiceState>('idle');
  const [note, setNote] = useState('');
  /** Live mic level 0..1 — kept in a ref (read by the canvas rAF loop). */
  const levelRef = useRef(0);
  const [usingRecorder, setUsingRecorder] = useState(false);

  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const transcriptionControllerRef = useRef<AbortController | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const intentRef = useRef<'idle' | 'listening'>('idle');
  const callbacksRef = useRef({ onInterim, onFinal });
  callbacksRef.current = { onInterim, onFinal };

  const teardownAudio = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    analyserRef.current = null;
    if (audioCtxRef.current && audioCtxRef.current.state !== 'closed') {
      audioCtxRef.current.close().catch(() => undefined);
    }
    audioCtxRef.current = null;
    levelRef.current = 0;
  }, []);

  const stop = useCallback(() => {
    intentRef.current = 'idle';
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop(); // onstop uploads the blob → onFinal
    }
    recorderRef.current = null;
    teardownAudio();
    setState('idle');
    setNote('');
  }, [teardownAudio]);

  const start = useCallback(async () => {
    if (intentRef.current === 'listening') return;
    transcriptionControllerRef.current?.abort();
    intentRef.current = 'listening';
    setState('starting');
    setNote('');

    /* 1 ── Microphone + analyser (drives the whisper flow) */
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      intentRef.current = 'idle';
      setState('denied');
      setNote('Microphone unavailable — type or attach media instead');
      window.setTimeout(() => setState((s) => (s === 'denied' ? 'idle' : s)), 3200);
      return;
    }
    streamRef.current = stream;

    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.75;
      source.connect(analyser);
      analyserRef.current = analyser;

      const buf = new Uint8Array(analyser.fftSize);
      let smoothed = 0;
      const tick = () => {
        const a = analyserRef.current;
        if (!a) return;
        a.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buf.length);
        smoothed = smoothed * 0.82 + Math.min(1, rms * 3.2) * 0.18;
        levelRef.current = smoothed;
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      /* Analyser is decorative — voice can still work without it. */
    }

    /* 2 ── Live transcription (Web Speech) with recorder fallback */
    const Ctor = getSpeechRecognition();
    if (Ctor) {
      try {
        const rec = new Ctor();
        rec.lang = language || getVoicePreferences().accent || 'en-IN';
        rec.continuous = true;
        rec.interimResults = true;
        rec.onresult = (ev) => {
          let interim = '';
          for (let i = ev.resultIndex; i < ev.results.length; i++) {
            const r = ev.results[i];
            const text = r[0].transcript;
            if (r.isFinal && text.trim()) callbacksRef.current.onFinal?.(text.trim());
            else interim += text;
          }
          callbacksRef.current.onInterim?.(interim.trim());
        };
        rec.onerror = (ev) => {
          if (ev.error === 'not-allowed' || ev.error === 'service-not-allowed') {
            intentRef.current = 'idle';
            setState('denied');
            setNote('Speech recognition blocked — attach an audio file instead');
            window.setTimeout(() => setState((s) => (s === 'denied' ? 'idle' : s)), 3200);
          }
        };
        rec.onend = () => {
          // Chrome auto-stops after silence — restart while the user intends to listen.
          if (intentRef.current === 'listening') {
            try {
              rec.start();
            } catch {
              /* already starting */
            }
          }
        };
        rec.start();
        recognitionRef.current = rec;
        setState('listening');
        setUsingRecorder(false);
        return;
      } catch {
        /* fall through to the recorder path */
      }
    }

    /* Recorder fallback: capture a real blob, transcribe server-side. */
    try {
      const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: mime || 'audio/webm' });
        chunksRef.current = [];
        if (blob.size < 1200) return; // too short to be speech
        const controller = new AbortController();
        transcriptionControllerRef.current = controller;
        try {
          const fd = new FormData();
          fd.append('audio_file', blob, 'whisper-flow.webm');
          const stt = await nexusJson<{ text: string; engine?: string }>('/api/audio/stt', {
            method: 'POST',
            body: fd,
            signal: controller.signal,
          });
          if (!controller.signal.aborted && stt.text?.trim()) callbacksRef.current.onFinal?.(stt.text.trim());
        } catch (error) {
          if (!controller.signal.aborted && !(error instanceof Error && error.name === 'AbortError')) {
            setNote('Transcription failed — the audio route did not respond');
          }
        } finally {
          if (transcriptionControllerRef.current === controller) transcriptionControllerRef.current = null;
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setState('listening');
      setUsingRecorder(true);
    } catch {
      teardownAudio();
      intentRef.current = 'idle';
      setState('unsupported');
      setNote('Voice capture unsupported in this browser — type or attach media');
      window.setTimeout(() => setState((s) => (s === 'unsupported' ? 'idle' : s)), 3200);
    }
  }, [language, teardownAudio]);

  /* Unmount hygiene. */
  useEffect(() => {
    return () => {
      intentRef.current = 'idle';
      transcriptionControllerRef.current?.abort();
      try {
        recognitionRef.current?.abort();
      } catch {
        /* noop */
      }
      try {
        if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop();
      } catch {
        /* noop */
      }
      teardownAudio();
    };
  }, [teardownAudio]);

  return { state, note, levelRef, usingRecorder, start, stop };
}

/* ────────────────────────────────────────────────────────────────────────────
 * WhisperFlowBand — canvas ribbon flow, amplitude-reactive.
 * Several translucent sine ribbons drift left→right; their amplitude and glow
 * breathe with the live mic level, and soft wisp particles ride the current.
 * ──────────────────────────────────────────────────────────────────────────── */

interface WhisperFlowBandProps {
  levelRef: React.RefObject<number>;
  active: boolean;
  height?: number;
}

interface Wisp {
  x: number;
  y: number;
  r: number;
  speed: number;
  phase: number;
  hue: number;
}

const RIBBONS = [
  { color: '34, 211, 238', freq: 0.011, speed: 1.15, amp: 9, width: 2.1, alpha: 0.5 }, // cyan
  { color: '139, 92, 246', freq: 0.014, speed: -0.85, amp: 12, width: 1.7, alpha: 0.42 }, // violet
  { color: '226, 232, 240', freq: 0.019, speed: 0.62, amp: 6, width: 1.1, alpha: 0.3 }, // frost
  { color: '34, 211, 238', freq: 0.008, speed: -0.45, amp: 15, width: 1.3, alpha: 0.22 }, // deep cyan
];

export const WhisperFlowBand: React.FC<WhisperFlowBandProps> = ({ levelRef, active, height = 58 }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wispsRef = useRef<Wisp[]>([]);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !active) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let t = 0;
    let level = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    if (wispsRef.current.length === 0) {
      wispsRef.current = Array.from({ length: 26 }, () => ({
        x: Math.random(),
        y: 0.18 + Math.random() * 0.64,
        r: 0.7 + Math.random() * 1.9,
        speed: 0.0011 + Math.random() * 0.0032,
        phase: Math.random() * Math.PI * 2,
        hue: Math.random(),
      }));
    }

    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      const mid = h / 2;
      const target = levelRef.current ?? 0;
      level = level * 0.9 + target * 0.1; // ease toward the mic level

      ctx.clearRect(0, 0, w, h);
      t += 0.016;

      /* Soft vertical breath wash behind the ribbons. */
      const wash = ctx.createLinearGradient(0, 0, 0, h);
      wash.addColorStop(0, `rgba(34, 211, 238, ${0.035 + level * 0.05})`);
      wash.addColorStop(0.5, `rgba(139, 92, 246, ${0.03 + level * 0.06})`);
      wash.addColorStop(1, `rgba(34, 211, 238, ${0.02 + level * 0.03})`);
      ctx.fillStyle = wash;
      ctx.fillRect(0, 0, w, h);

      /* Flowing ribbons — amplitude breathes with the voice. */
      RIBBONS.forEach((rb, idx) => {
        ctx.beginPath();
        const ampNow = rb.amp * (0.32 + level * 2.1);
        for (let x = -8; x <= w + 8; x += 5) {
          const y =
            mid +
            Math.sin(x * rb.freq + t * rb.speed * 2.1 + idx * 1.7) * ampNow +
            Math.sin(x * rb.freq * 2.3 - t * rb.speed * 1.3) * ampNow * 0.35;
          if (x === -8) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        const stroke = ctx.createLinearGradient(0, 0, w, 0);
        stroke.addColorStop(0, `rgba(${rb.color}, 0)`);
        stroke.addColorStop(0.22, `rgba(${rb.color}, ${rb.alpha * (0.45 + level * 0.9)})`);
        stroke.addColorStop(0.78, `rgba(${rb.color}, ${rb.alpha * (0.45 + level * 0.9)})`);
        stroke.addColorStop(1, `rgba(${rb.color}, 0)`);
        ctx.strokeStyle = stroke;
        ctx.lineWidth = rb.width * (0.85 + level * 0.7);
        ctx.shadowColor = `rgba(${rb.color}, ${0.35 + level * 0.5})`;
        ctx.shadowBlur = 6 + level * 14;
        ctx.stroke();
        ctx.shadowBlur = 0;
      });

      /* Wisp particles riding the current. */
      wispsRef.current.forEach((p) => {
        p.x += p.speed * (0.45 + level * 2.4);
        if (p.x > 1.05) {
          p.x = -0.05;
          p.y = 0.18 + Math.random() * 0.64;
        }
        const px = p.x * w;
        const py = p.y * h + Math.sin(t * 1.6 + p.phase) * (5 + level * 16);
        const alpha = (0.14 + level * 0.6) * (0.5 + 0.5 * Math.sin(t * 2 + p.phase));
        const color = p.hue > 0.62 ? '139, 92, 246' : p.hue > 0.3 ? '34, 211, 238' : '226, 232, 240';
        ctx.beginPath();
        ctx.arc(px, py, p.r * (0.85 + level * 0.9), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${color}, ${Math.max(0, alpha)})`;
        ctx.shadowColor = `rgba(${color}, ${Math.max(0, alpha)})`;
        ctx.shadowBlur = 5 + level * 9;
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      rafRef.current = requestAnimationFrame(draw);
    };
    rafRef.current = requestAnimationFrame(draw);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      ro.disconnect();
    };
  }, [active, levelRef]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="block w-full rounded-2xl bg-white/[0.03] border border-white/[0.06]"
      style={{ height }}
    />
  );
};

/* ────────────────────────────────────────────────────────────────────────────
 * MicButton — toggles voice capture. While listening, halo rings expand with
 * the live mic level (driven by direct DOM writes from the level loop — no
 * re-render churn).
 * ──────────────────────────────────────────────────────────────────────────── */

interface MicButtonProps {
  state: VoiceState;
  levelRef: React.RefObject<number>;
  disabled?: boolean;
  onStart: () => void;
  onStop: () => void;
  title?: string;
}

export const MicButton: React.FC<MicButtonProps> = ({ state, levelRef, disabled, onStart, onStop, title }) => {
  const ringA = useRef<HTMLSpanElement | null>(null);
  const ringB = useRef<HTMLSpanElement | null>(null);
  const listening = state === 'listening' || state === 'starting';

  useEffect(() => {
    if (!listening) return;
    let raf = 0;
    const loop = () => {
      const l = levelRef.current ?? 0;
      if (ringA.current) {
        ringA.current.style.transform = `scale(${1 + l * 0.85})`;
        ringA.current.style.opacity = String(0.5 + l * 0.4);
      }
      if (ringB.current) {
        ringB.current.style.transform = `scale(${1 + l * 1.5})`;
        ringB.current.style.opacity = String(0.28 + l * 0.35);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [listening, levelRef]);

  const denied = state === 'denied' || state === 'unsupported';

  return (
    <div className="relative shrink-0 pb-0.5">
      {/* Amplitude-reactive halo rings */}
      {listening && (
        <>
          <span
            ref={ringA}
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full border border-cyan-300/70 will-change-transform"
            style={{ transition: 'opacity 90ms linear' }}
          />
          <span
            ref={ringB}
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-9 h-9 rounded-full border border-violet-400/50 will-change-transform"
            style={{ transition: 'opacity 90ms linear' }}
          />
        </>
      )}
      <button
        type="button"
        onClick={() => (listening ? onStop() : onStart())}
        disabled={disabled && !listening}
        aria-label={listening ? 'Stop voice input' : 'Start voice input — whisper flow'}
        aria-pressed={listening}
        title={title ?? 'Voice input — whisper flow (Web Speech with server-side Whisper fallback)'}
        className={`relative z-10 w-9 h-9 rounded-full flex items-center justify-center transition-all cursor-pointer ${
          listening
            ? 'bg-gradient-to-br from-cyan-300 to-violet-400 text-slate-900 shadow-[0_0_22px_rgba(34,211,238,0.55)] animate-[nxs-orb-live_1.6s_ease-in-out_infinite]'
            : denied
              ? 'bg-rose-400/15 text-rose-300 border border-rose-300/40'
              : 'bg-white/[0.07] text-slate-300 border border-white/15 hover:bg-white/[0.14] hover:text-cyan-200 hover:border-cyan-300/40'
        } disabled:opacity-50 disabled:cursor-not-allowed`}
      >
        {denied ? <MicOff className="w-4 h-4" strokeWidth={1.9} /> : <Mic className="w-4 h-4" strokeWidth={1.9} />}
      </button>
    </div>
  );
};

/** Small badge shown while the recorder fallback is running. */
export const RecorderBadge: React.FC = () => (
  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-violet-400/15 border border-violet-300/30 text-violet-200 text-[10px] font-semibold tracking-wide">
    <AudioLines className="w-3 h-3" strokeWidth={2} />
    recording · POST /api/audio/stt on stop
  </span>
);
