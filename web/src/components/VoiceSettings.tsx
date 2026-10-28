import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AudioLines,
  Check,
  ChevronDown,
  Gauge,
  Globe,
  Play,
  RefreshCw,
  Square,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import {
  VOICE_ACCENTS,
  ensureVoices,
  getAccentMeta,
  getAvailableVoices,
  isSpeechSupported,
  listVoicesForAccent,
  onVoicesChanged,
  pickVoiceForAccent,
  saveVoicePreferences,
  speakText,
  stopAnySpeaking,
  type VoiceAccentId,
  type VoicePreferences,
} from '../utils/voiceManager';
import type { AgentStatus } from '../types';

interface VoiceSettingsProps {
  preferences: VoicePreferences;
  onChange: (preferences: VoicePreferences) => void;
  voiceEnabled?: boolean;
  onVoiceEnabledChange?: (enabled: boolean) => void;
  agentStatus?: AgentStatus;
  onStatusChange?: (status: AgentStatus) => void;
  disabled?: boolean;
  align?: 'left' | 'right';
  placement?: 'top' | 'bottom';
  className?: string;
}

function normalizeLang(lang: string): string {
  return (lang || '').replace(/_/g, '-').toLowerCase();
}

function VoiceToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label="Voice replies"
      onClick={onToggle}
      className={`relative h-5 w-9 shrink-0 rounded-full border transition-all cursor-pointer ${
        enabled
          ? 'border-cyan-300/70 bg-cyan-400 shadow-[0_0_12px_rgba(0,240,255,0.35)]'
          : 'border-slate-700 bg-slate-800 hover:border-slate-500'
      }`}
    >
      <span
        className={`absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full transition-all ${
          enabled ? 'left-[18px] bg-slate-950' : 'left-[3px] bg-slate-400'
        }`}
      />
    </button>
  );
}

export const VoiceSettings: React.FC<VoiceSettingsProps> = ({
  preferences,
  onChange,
  voiceEnabled = true,
  onVoiceEnabledChange,
  agentStatus = 'idle',
  onStatusChange,
  disabled = false,
  align = 'right',
  placement = 'bottom',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>(() => getAvailableVoices());
  const [isLoadingVoices, setIsLoadingVoices] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const supported = isSpeechSupported();
  const accentMeta = getAccentMeta(preferences.accent);

  const accentVoices = useMemo(
    () => listVoicesForAccent(preferences.accent, voices),
    [preferences.accent, voices],
  );
  const selectedVoice = useMemo(
    () => pickVoiceForAccent(preferences.accent, preferences.voiceURI, voices),
    [preferences.accent, preferences.voiceURI, voices],
  );
  const exactAccentVoiceCount = useMemo(
    () =>
      voices.filter((voice) => normalizeLang(voice.lang) === preferences.accent.toLowerCase()).length,
    [preferences.accent, voices],
  );
  const savedVoiceAvailable = Boolean(
    preferences.voiceURI && voices.some((voice) => voice.voiceURI === preferences.voiceURI),
  );

  const refreshVoices = useCallback(async () => {
    setIsLoadingVoices(true);
    try {
      const loaded = await ensureVoices(2000);
      setVoices(loaded);
    } finally {
      setIsLoadingVoices(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setVoices(getAvailableVoices());
    void ensureVoices().then((loaded) => {
      if (!cancelled) setVoices(loaded);
    });
    const unsubscribe = onVoicesChanged((loaded) => {
      if (!cancelled) setVoices(loaded);
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isOpen) return undefined;
    void refreshVoices();

    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, refreshVoices]);

  useEffect(() => {
    if (agentStatus !== 'speaking') setIsTesting(false);
  }, [agentStatus]);

  const updatePreferences = (patch: Partial<VoicePreferences>) => {
    const next = saveVoicePreferences({ ...preferences, ...patch });
    onChange(next);
  };

  const handleAccentChange = (accent: VoiceAccentId) => {
    if (isTesting) {
      stopAnySpeaking();
      setIsTesting(false);
      onStatusChange?.('idle');
    }
    // Reset the explicit voice so the best browser voice for the new accent wins.
    updatePreferences({ accent, voiceURI: null });
  };

  const handleTestVoice = () => {
    if (isTesting) {
      stopAnySpeaking();
      setIsTesting(false);
      onStatusChange?.('idle');
      return;
    }

    setIsTesting(true);
    const started = speakText(accentMeta.sample, {
      accent: preferences.accent,
      voiceURI: preferences.voiceURI,
      rate: preferences.rate,
      pitch: preferences.pitch,
      onStatusChange,
      onFinish: () => setIsTesting(false),
    });
    if (!started) setIsTesting(false);
  };

  const headerIcon = !voiceEnabled ? (
    <VolumeX className="h-3.5 w-3.5" />
  ) : agentStatus === 'speaking' ? (
    <AudioLines className="h-3.5 w-3.5 animate-pulse" />
  ) : (
    <Volume2 className="h-3.5 w-3.5" />
  );

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title={`Voice settings — ${accentMeta.label}`}
        className={`relative flex h-8 items-center justify-center gap-1.5 rounded-xl border px-2 font-mono transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
          isOpen
            ? 'border-cyan-300/70 bg-cyan-500/15 text-cyan-100 shadow-[0_0_14px_rgba(0,240,255,0.18)]'
            : voiceEnabled
              ? 'border-slate-800 bg-slate-950/70 text-slate-400 hover:border-cyan-400/50 hover:text-cyan-200'
              : 'border-slate-800 bg-slate-950/70 text-slate-600 hover:text-slate-300'
        }`}
      >
        {headerIcon}
        <span className="text-[8px] font-black uppercase tracking-wider">{accentMeta.shortLabel}</span>
        <span className="sr-only">Voice settings</span>
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-label="Voice settings"
          className={`absolute z-50 flex max-h-[min(680px,calc(100dvh-7rem))] w-[340px] max-w-[88vw] flex-col overflow-hidden rounded-2xl border border-cyan-400/30 bg-[#050914]/98 font-mono shadow-[0_24px_60px_rgba(0,0,0,0.85),0_0_28px_rgba(0,240,255,0.14)] backdrop-blur-2xl ${
            placement === 'top' ? 'bottom-[calc(100%+8px)]' : 'top-[calc(100%+8px)]'
          } ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          <div className="shrink-0 border-b border-slate-800 px-3.5 py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.22em] text-cyan-200">
                  <Volume2 className="h-3.5 w-3.5 text-cyan-400" />
                  Voice output
                </div>
                <p className="mt-1 text-[9px] leading-relaxed text-slate-500">
                  Accent-first browser speech. Indian English is selected by default.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                title="Close voice settings"
                className="rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2">
              <div>
                <div className="text-[9px] font-black text-slate-100">Voice replies</div>
                <div className="text-[8px] text-slate-500">Read final answers aloud automatically</div>
              </div>
              <VoiceToggle
                enabled={voiceEnabled}
                onToggle={() => onVoiceEnabledChange?.(!voiceEnabled)}
              />
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3">
            {!supported ? (
              <div className="rounded-xl border border-amber-400/30 bg-amber-950/30 px-3 py-3 text-[9px] leading-relaxed text-amber-100">
                This browser does not expose the Web Speech API, so voice output is unavailable here.
                Try Chrome or Edge for the widest selection of natural voices.
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                    <Globe className="h-3 w-3" />
                    Accent
                  </div>
                  <button
                    type="button"
                    onClick={() => void refreshVoices()}
                    disabled={isLoadingVoices}
                    className="flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider text-slate-500 transition-colors hover:text-cyan-200 disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`h-3 w-3 ${isLoadingVoices ? 'animate-spin' : ''}`} />
                    Refresh voices
                  </button>
                </div>

                <div className="mt-2 grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Voice accent">
                  {VOICE_ACCENTS.map((accent) => {
                    const selected = accent.id === preferences.accent;
                    return (
                      <button
                        key={accent.id}
                        type="button"
                        role="radio"
                        aria-checked={selected}
                        onClick={() => handleAccentChange(accent.id)}
                        title={accent.description}
                        className={`rounded-xl border px-2 py-2 text-left transition-all cursor-pointer ${
                          selected
                            ? 'border-cyan-300/70 bg-cyan-500/15 text-cyan-50 shadow-[0_0_14px_rgba(0,240,255,0.12)]'
                            : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-[9px] font-black uppercase">{accent.shortLabel}</span>
                          {selected && <Check className="h-3 w-3 text-cyan-300" />}
                        </div>
                        <div className="mt-1 text-[7.5px] font-bold leading-tight">
                          {accent.label.replace(' English', '')}
                        </div>
                      </button>
                    );
                  })}
                </div>

                <p className="mt-2 text-[8.5px] leading-relaxed text-slate-500">{accentMeta.description}</p>

                <label
                  htmlFor="nexus-voice-select"
                  className="mt-4 block text-[8px] font-black uppercase tracking-[0.22em] text-slate-500"
                >
                  Browser voice
                </label>
                <div className="relative mt-2">
                  <select
                    id="nexus-voice-select"
                    value={savedVoiceAvailable ? preferences.voiceURI || '' : ''}
                    onChange={(event) =>
                      updatePreferences({ voiceURI: event.target.value || null })
                    }
                    disabled={disabled || accentVoices.length === 0}
                    className="w-full appearance-none truncate rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 pr-8 text-[10px] font-bold text-slate-100 outline-none transition-colors focus:border-cyan-400/70 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">
                      Best available{selectedVoice ? ` — ${selectedVoice.name}` : ` — ${preferences.accent}`}
                    </option>
                    {accentVoices.map((voice, index) => (
                      <option key={`${voice.voiceURI}-${index}`} value={voice.voiceURI}>
                        {voice.name} ({voice.lang})
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
                </div>

                {voices.length === 0 ? (
                  <p className="mt-2 rounded-lg border border-slate-800 bg-slate-950/70 px-2.5 py-2 text-[8.5px] leading-relaxed text-slate-500">
                    {isLoadingVoices
                      ? 'Loading the voices installed in this browser…'
                      : 'No voices were reported by this browser yet. Refresh voices or try the test—some browsers load them after the first interaction.'}
                  </p>
                ) : exactAccentVoiceCount === 0 ? (
                  <p className="mt-2 rounded-lg border border-amber-400/25 bg-amber-950/25 px-2.5 py-2 text-[8.5px] leading-relaxed text-amber-100/80">
                    No exact {preferences.accent} voice is installed in this browser, so NEXUS will use the closest English voice.
                    For the best Indian English quality, use a browser/OS with an en-IN natural voice installed.
                  </p>
                ) : selectedVoice ? (
                  <p className="mt-2 truncate text-[8.5px] text-slate-500">
                    Using <span className="font-bold text-cyan-100">{selectedVoice.name}</span>
                    <span className="text-slate-600">
                      {' '}· {selectedVoice.lang} · {selectedVoice.localService ? 'on-device' : 'system/online'}
                    </span>
                  </p>
                ) : null}

                <div className="mt-4 space-y-3">
                  <div>
                    <div className="flex items-center justify-between text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                      <span className="flex items-center gap-1.5">
                        <Gauge className="h-3 w-3" /> Speed
                      </span>
                      <span className="text-cyan-200">{preferences.rate.toFixed(2)}×</span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="1.5"
                      step="0.05"
                      value={preferences.rate}
                      onChange={(event) => updatePreferences({ rate: Number(event.target.value) })}
                      aria-label="Speech speed"
                      className="mt-2 w-full accent-cyan-400"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-[8px] font-black uppercase tracking-[0.22em] text-slate-500">
                      <span className="flex items-center gap-1.5">
                        <AudioLines className="h-3 w-3" /> Pitch
                      </span>
                      <span className="text-cyan-200">{preferences.pitch.toFixed(2)}×</span>
                    </div>
                    <input
                      type="range"
                      min="0.5"
                      max="1.5"
                      step="0.05"
                      value={preferences.pitch}
                      onChange={(event) => updatePreferences({ pitch: Number(event.target.value) })}
                      aria-label="Speech pitch"
                      className="mt-2 w-full accent-cyan-400"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleTestVoice}
                  disabled={disabled}
                  className={`mt-4 flex w-full items-center justify-center gap-2 rounded-xl border px-3 py-2.5 text-[10px] font-black uppercase tracking-[0.18em] transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
                    isTesting
                      ? 'border-amber-300/70 bg-amber-500/15 text-amber-100'
                      : 'border-cyan-300/70 bg-cyan-400 text-slate-950 shadow-[0_0_18px_rgba(0,240,255,0.22)] hover:bg-cyan-300'
                  }`}
                >
                  {isTesting ? <Square className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                  {isTesting ? 'Stop test' : `Test ${accentMeta.shortLabel} voice`}
                </button>
              </>
            )}
          </div>

          <div className="shrink-0 border-t border-slate-800 bg-slate-950/70 px-3.5 py-2 text-[8px] leading-relaxed text-slate-500">
            Voice quality and available accents depend on voices installed in your browser and operating system.
          </div>
        </div>
      )}
    </div>
  );
};
