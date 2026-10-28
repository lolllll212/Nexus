import type { AgentStatus } from '../types';

/**
 * NEXUS voice output (browser Web Speech API).
 *
 * Indian English (`en-IN`) is the default accent. The manager scores every
 * voice installed in the visitor's browser against the selected accent,
 * preferring well-known natural/neural voices for that locale. Speech is
 * cleaned of markdown/tool syntax and split into short sentence chunks,
 * which avoids the common Chrome bug where very long utterances stop early.
 */

export type VoiceAccentId = 'en-IN' | 'en-GB' | 'en-US' | 'en-AU' | 'en-CA' | 'en-IE';

export interface VoiceAccent {
  id: VoiceAccentId;
  label: string;
  shortLabel: string;
  description: string;
  sample: string;
}

export const VOICE_ACCENTS: VoiceAccent[] = [
  {
    id: 'en-IN',
    label: 'Indian English',
    shortLabel: 'IN',
    description: 'Clear Indian English — the NEXUS default voice.',
    sample: "Namaste, I'm NEXUS. I'm ready to help you research, write code, and turn ideas into finished work.",
  },
  {
    id: 'en-GB',
    label: 'British English',
    shortLabel: 'GB',
    description: 'Crisp British delivery with a polished, formal tone.',
    sample: "Hello, I'm NEXUS. I can help you research, write code, and turn ideas into finished work.",
  },
  {
    id: 'en-US',
    label: 'American English',
    shortLabel: 'US',
    description: 'Natural American English, friendly and direct.',
    sample: "Hi, I'm NEXUS. I can help you research, write code, and turn ideas into finished work.",
  },
  {
    id: 'en-AU',
    label: 'Australian English',
    shortLabel: 'AU',
    description: 'Relaxed Australian English with clear pronunciation.',
    sample: "G'day, I'm NEXUS. I can help you research, write code, and turn ideas into finished work.",
  },
  {
    id: 'en-CA',
    label: 'Canadian English',
    shortLabel: 'CA',
    description: 'Neutral Canadian English, warm and easy to follow.',
    sample: "Hello, I'm NEXUS. I can help you research, write code, and turn ideas into finished work.",
  },
  {
    id: 'en-IE',
    label: 'Irish English',
    shortLabel: 'IE',
    description: 'Soft Irish English with a melodic cadence.',
    sample: "Hello, I'm NEXUS. I can help you research, write code, and turn ideas into finished work.",
  },
];

export const DEFAULT_VOICE_ACCENT: VoiceAccentId = 'en-IN';

export interface VoicePreferences {
  accent: VoiceAccentId;
  voiceURI: string | null;
  rate: number;
  pitch: number;
}

export const DEFAULT_VOICE_PREFERENCES: VoicePreferences = {
  accent: DEFAULT_VOICE_ACCENT,
  voiceURI: null,
  rate: 1,
  pitch: 1,
};

const VOICE_PREFS_KEY = 'nexus_voice_prefs';
const MAX_SPEECH_CHUNK_CHARS = 180;

/** High-quality voices commonly exposed by Edge, Chrome, Windows and macOS. */
const PREFERRED_VOICE_NAMES: Record<VoiceAccentId, RegExp> = {
  'en-IN': /neerja|PrabhatPriya|kajal|rishi|veena|ananya|aarti|aarav/i,
  'en-GB': /sonia|ryan|daniel|george|arthur|libby|maisie|oliver|thomas|alfie/i,
  'en-US': /aria|jenny|guy|emma|davis|andrew|amelia|christopher|ava|brian/i,
  'en-AU': /natasha|william|anaya|ken|clara|lee\.?anne/i,
  'en-CA': /clara|liam/i,
  'en-IE': /connor|emily/i,
};

let currentUtterance: SpeechSynthesisUtterance | null = null;
let speechGeneration = 0;
let resumeTimer: number | null = null;

function clamp(value: number, min: number, max: number, fallback: number): number {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}

function isVoiceAccentId(value: unknown): value is VoiceAccentId {
  return typeof value === 'string' && VOICE_ACCENTS.some((accent) => accent.id === value);
}

export function getAccentMeta(accent: VoiceAccentId): VoiceAccent {
  return VOICE_ACCENTS.find((item) => item.id === accent) || VOICE_ACCENTS[0];
}

export function getVoicePreferences(): VoicePreferences {
  if (typeof window === 'undefined') return { ...DEFAULT_VOICE_PREFERENCES };
  try {
    const raw = window.localStorage.getItem(VOICE_PREFS_KEY);
    if (!raw) return { ...DEFAULT_VOICE_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<VoicePreferences>;
    return {
      accent: isVoiceAccentId(parsed.accent) ? parsed.accent : DEFAULT_VOICE_ACCENT,
      voiceURI: typeof parsed.voiceURI === 'string' && parsed.voiceURI ? parsed.voiceURI : null,
      rate: clamp(Number(parsed.rate), 0.5, 1.5, DEFAULT_VOICE_PREFERENCES.rate),
      pitch: clamp(Number(parsed.pitch), 0.5, 1.5, DEFAULT_VOICE_PREFERENCES.pitch),
    };
  } catch {
    return { ...DEFAULT_VOICE_PREFERENCES };
  }
}

export function saveVoicePreferences(patch: Partial<VoicePreferences>): VoicePreferences {
  const next: VoicePreferences = {
    ...getVoicePreferences(),
    ...patch,
    rate: clamp(Number(patch.rate ?? getVoicePreferences().rate), 0.5, 1.5, 1),
    pitch: clamp(Number(patch.pitch ?? getVoicePreferences().pitch), 0.5, 1.5, 1),
  };
  if (!isVoiceAccentId(next.accent)) next.accent = DEFAULT_VOICE_ACCENT;
  try {
    window.localStorage.setItem(VOICE_PREFS_KEY, JSON.stringify(next));
  } catch {
    // Private browsing / storage restrictions should never break speech.
  }
  return next;
}

export function isSpeechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function getAvailableVoices(): SpeechSynthesisVoice[] {
  if (!isSpeechSupported()) return [];
  try {
    return window.speechSynthesis.getVoices() || [];
  } catch {
    return [];
  }
}

/** Resolve once the browser has loaded its voice list (or after a timeout). */
export function ensureVoices(timeoutMs = 1500): Promise<SpeechSynthesisVoice[]> {
  if (!isSpeechSupported()) return Promise.resolve([]);
  const existing = getAvailableVoices();
  if (existing.length > 0) return Promise.resolve(existing);

  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      window.speechSynthesis.onvoiceschanged = previousHandler;
      resolve(getAvailableVoices());
    };
    const previousHandler = window.speechSynthesis.onvoiceschanged;
    window.speechSynthesis.onvoiceschanged = () => {
      if (typeof previousHandler === 'function') {
        previousHandler.call(window.speechSynthesis, new Event('voiceschanged'));
      }
      if (getAvailableVoices().length > 0) finish();
    };
    window.setTimeout(finish, timeoutMs);
  });
}

export function onVoicesChanged(callback: (voices: SpeechSynthesisVoice[]) => void): () => void {
  if (!isSpeechSupported()) return () => {};
  const handler = () => callback(getAvailableVoices());
  window.speechSynthesis.addEventListener?.('voiceschanged', handler);
  // Some browsers only reliably support the property handler; ensureVoices in
  // components covers first load, while this keeps an open picker fresh.
  return () => window.speechSynthesis.removeEventListener?.('voiceschanged', handler);
}

function normalizeLang(lang: string | undefined): string {
  return (lang || '').replace(/_/g, '-').toLowerCase();
}

export function scoreVoiceForAccent(voice: SpeechSynthesisVoice, accent: VoiceAccentId): number {
  const lang = normalizeLang(voice.lang);
  const target = accent.toLowerCase();
  const name = voice.name || '';
  let score = 100;

  if (lang === target) score -= 65;
  else if (lang.startsWith('en')) score -= 25;
  else score += 100;

  if (PREFERRED_VOICE_NAMES[accent].test(name)) score -= 35;
  if (/natural|neural|online|premium|enhanced/i.test(name)) score -= 18;
  if (/google/i.test(name)) score -= 8;
  if (/microsoft/i.test(name)) score -= 4;
  if (voice.default) score -= 2;
  return score;
}

export function listVoicesForAccent(
  accent: VoiceAccentId,
  voices: SpeechSynthesisVoice[] = getAvailableVoices(),
): SpeechSynthesisVoice[] {
  const englishVoices = voices.filter((voice) => normalizeLang(voice.lang).startsWith('en'));
  const candidates = englishVoices.length > 0 ? englishVoices : voices;
  return [...candidates].sort((a, b) => scoreVoiceForAccent(a, accent) - scoreVoiceForAccent(b, accent));
}

export function pickVoiceForAccent(
  accent: VoiceAccentId,
  preferredVoiceURI?: string | null,
  voices: SpeechSynthesisVoice[] = getAvailableVoices(),
): SpeechSynthesisVoice | null {
  if (preferredVoiceURI) {
    const exact = voices.find((voice) => voice.voiceURI === preferredVoiceURI);
    if (exact) return exact;
  }
  return listVoicesForAccent(accent, voices)[0] || null;
}

/** Convert markdown/tool-flavoured assistant text into pleasant spoken prose. */
export function speakable(text: string): string {
  if (!text) return '';

  let cleaned = String(text);
  const finalAnswer = cleaned.match(/final\s+answer\s*:/i);
  if (finalAnswer?.index !== undefined) {
    cleaned = cleaned.slice(finalAnswer.index + finalAnswer[0].length);
  }

  cleaned = cleaned
    .replace(/```[\s\S]*?(```|$)/g, ' Code block available in the chat. ')
    .replace(/TOOL_CALL\s*:.*$/gim, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' image ')
    .replace(/\[([^\]]+)\]\((?:[^)]+)\)/g, '$1')
    .replace(/https?:\/\/\S+/gi, 'a link');

  const lines = cleaned.split(/\r?\n/).map((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed
        .slice(1, -1)
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean);
      if (cells.length && cells.every((cell) => /^:?-{3,}:?$/.test(cell))) return '';
      return cells.join(', ');
    }
    return trimmed
      .replace(/^#{1,6}\s+/, '')
      .replace(/^>\s?/, '')
      .replace(/^[-*+]\s+/, '')
      .replace(/^\d+[.)]\s+/, '');
  });

  return lines
    .join(' ')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    .replace(/~~([^~]+)~~/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/[#>*~|]/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;:!?])/g, '$1')
    .trim();
}

function splitIntoSentences(text: string): string[] {
  const sentences: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (!/[.!?…]/.test(char)) continue;
    // Do not split decimal numbers such as 3.5 or version numbers.
    if (char === '.' && /\d/.test(text[i - 1] || '') && /\d/.test(text[i + 1] || '')) continue;
    let end = i + 1;
    while (end < text.length && /["')\]]/.test(text[end])) end += 1;
    if (end < text.length && !/\s/.test(text[end])) continue;
    const sentence = text.slice(start, end).trim();
    if (sentence) sentences.push(sentence);
    start = end;
  }
  const tail = text.slice(start).trim();
  if (tail) sentences.push(tail);
  return sentences;
}

/** Split long responses into browser-friendly utterance chunks. */
export function chunkSpeechText(text: string, maxChars = MAX_SPEECH_CHUNK_CHARS): string[] {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (!clean) return [];

  const chunks: string[] = [];
  let current = '';

  const flush = () => {
    if (current.trim()) chunks.push(current.trim());
    current = '';
  };

  for (const sentence of splitIntoSentences(clean)) {
    if (sentence.length <= maxChars) {
      if (current && `${current} ${sentence}`.length > maxChars) flush();
      current = current ? `${current} ${sentence}` : sentence;
      continue;
    }

    flush();
    let remaining = sentence;
    while (remaining.length > maxChars) {
      let breakAt = remaining.lastIndexOf(' ', maxChars);
      if (breakAt < Math.floor(maxChars * 0.55)) breakAt = maxChars;
      chunks.push(remaining.slice(0, breakAt).trim());
      remaining = remaining.slice(breakAt).trim();
    }
    current = remaining;
  }
  flush();
  return chunks;
}

function clearResumeTimer(): void {
  if (resumeTimer !== null && typeof window !== 'undefined') {
    window.clearInterval(resumeTimer);
    resumeTimer = null;
  }
}

/** Cancel and stop any active browser speech synthesis immediately. */
export function stopAnySpeaking(): void {
  speechGeneration += 1;
  clearResumeTimer();
  currentUtterance = null;
  if (isSpeechSupported()) {
    try {
      window.speechSynthesis.cancel();
    } catch {
      // Ignore browser-specific cancellation errors.
    }
  }
}

export function isCurrentlySpeaking(): boolean {
  return isSpeechSupported() && (window.speechSynthesis.speaking || window.speechSynthesis.pending);
}

export interface SpeakOptions {
  accent?: VoiceAccentId;
  voiceURI?: string | null;
  rate?: number;
  pitch?: number;
  onStatusChange?: (status: AgentStatus) => void;
  onFinish?: () => void;
}

export function speakText(text: string, options: SpeakOptions = {}): boolean {
  const prefs = getVoicePreferences();
  const accent = options.accent && isVoiceAccentId(options.accent) ? options.accent : prefs.accent;
  const voiceURI = options.voiceURI !== undefined ? options.voiceURI : prefs.voiceURI;
  const rate = clamp(Number(options.rate ?? prefs.rate), 0.5, 1.5, 1);
  const pitch = clamp(Number(options.pitch ?? prefs.pitch), 0.5, 1.5, 1);
  const { onStatusChange, onFinish } = options;

  if (!isSpeechSupported()) {
    onStatusChange?.('idle');
    onFinish?.();
    return false;
  }

  const chunks = chunkSpeechText(speakable(text));
  if (chunks.length === 0) {
    onStatusChange?.('idle');
    onFinish?.();
    return false;
  }

  const generation = ++speechGeneration;
  clearResumeTimer();
  try {
    window.speechSynthesis.cancel();
  } catch {
    // Continue; creating a new utterance may still work.
  }

  let finished = false;
  const finish = () => {
    if (finished || generation !== speechGeneration) return;
    finished = true;
    clearResumeTimer();
    currentUtterance = null;
    onStatusChange?.('idle');
    onFinish?.();
  };

  onStatusChange?.('speaking');

  void ensureVoices().then((voices) => {
    if (generation !== speechGeneration) return;
    const voice = pickVoiceForAccent(accent, voiceURI, voices);

    // Chromium can stall on long speech sessions. Our chunks are short, but
    // a gentle pause/resume watchdog keeps multi-paragraph replies moving.
    clearResumeTimer();
    resumeTimer = window.setInterval(() => {
      if (generation !== speechGeneration) {
        clearResumeTimer();
        return;
      }
      try {
        if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        } else if (window.speechSynthesis.paused) {
          window.speechSynthesis.resume();
        }
      } catch {
        // The utterance end/error handlers remain the source of truth.
      }
    }, 10000);

    const speakChunk = (index: number) => {
      if (generation !== speechGeneration) return;
      if (index >= chunks.length) {
        finish();
        return;
      }

      const utterance = new SpeechSynthesisUtterance(chunks[index]);
      utterance.rate = rate;
      utterance.pitch = pitch;
      utterance.lang = voice?.lang || accent;
      if (voice) utterance.voice = voice;

      utterance.onstart = () => {
        if (generation === speechGeneration) onStatusChange?.('speaking');
      };
      utterance.onend = () => speakChunk(index + 1);
      utterance.onerror = (event) => {
        const error = (event as SpeechSynthesisErrorEvent).error;
        if (generation !== speechGeneration || error === 'interrupted' || error === 'canceled') return;
        // A bad chunk/voice should not silently strand the whole reply.
        if (index + 1 < chunks.length) speakChunk(index + 1);
        else finish();
      };

      currentUtterance = utterance;
      try {
        window.speechSynthesis.speak(utterance);
      } catch (err) {
        console.warn('Speech synthesis failed:', err);
        finish();
      }
    };

    speakChunk(0);
  });

  return true;
}

/**
 * Backward-compatible speech helper used by App, JarvisModal and VoiceCortex.
 * Existing callers automatically receive the saved en-IN-by-default accent.
 */
export function speakWithStatus(
  text: string,
  onStatusChange?: (status: AgentStatus) => void,
  onFinish?: () => void,
  options: Omit<SpeakOptions, 'onStatusChange' | 'onFinish'> = {},
): boolean {
  return speakText(text, { ...options, onStatusChange, onFinish });
}
