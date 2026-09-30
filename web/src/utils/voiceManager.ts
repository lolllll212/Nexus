import { AgentStatus } from '../types';

let currentUtterance: SpeechSynthesisUtterance | null = null;

/**
 * Cancel and stop any active browser speech synthesis immediately.
 */
export function stopAnySpeaking(): void {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (_) {}
    currentUtterance = null;
  }
}

/**
 * Speak text out loud with lifecycle callbacks ensuring agentStatus is 'speaking'
 * throughout utterance duration, and returns to 'idle' on end/error.
 */
export function speakWithStatus(
  text: string,
  onStatusChange?: (status: AgentStatus) => void,
  onFinish?: () => void
): boolean {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) {
    if (onStatusChange) onStatusChange('idle');
    if (onFinish) onFinish();
    return false;
  }

  // Cancel any ongoing speech first
  stopAnySpeaking();

  const cleanText = text.replace(/[*_#`~[\]]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!cleanText) {
    if (onStatusChange) onStatusChange('idle');
    if (onFinish) onFinish();
    return false;
  }

  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.rate = 1.02;
  utterance.pitch = 0.96;

  // Pick crisp British/English voice if available
  const voices = window.speechSynthesis.getVoices();
  const preferredVoice =
    voices.find((v) => /daniel|oliver|arthur|george/i.test(v.name) && v.lang.includes('en-GB')) ||
    voices.find((v) => v.lang.includes('en-GB')) ||
    voices.find((v) => v.lang.includes('en'));
  if (preferredVoice) utterance.voice = preferredVoice;

  if (onStatusChange) onStatusChange('speaking');

  const handleFinish = () => {
    currentUtterance = null;
    if (onStatusChange) onStatusChange('idle');
    if (onFinish) onFinish();
  };

  utterance.onstart = () => {
    if (onStatusChange) onStatusChange('speaking');
  };
  utterance.onend = handleFinish;
  utterance.onerror = handleFinish;

  currentUtterance = utterance;
  try {
    window.speechSynthesis.speak(utterance);
    return true;
  } catch (err) {
    console.warn('Speech synthesis failed:', err);
    handleFinish();
    return false;
  }
}
